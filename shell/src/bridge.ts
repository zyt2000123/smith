/**
 * NodeBridge — all backend communication goes through here.
 * UI components never call api.ts directly; they call bridge methods.
 */

import type { StoreApi } from "zustand/vanilla";

import { createToolActivity } from "./activity.js";
import {
  createSession,
  ensureAgentProfile,
  getLlmConfig,
  type LlmConfigInput,
  listMessages,
  listSessions,
  listSkills,
  type Session,
  type StreamEvent,
  type StreamTerminalStatus,
  setLlmConfig,
  streamMessage,
} from "./api.js";
import { ensureLocalServer } from "./dev-server.js";
import { createSetupDraft } from "./setup.js";
import type { AppStore } from "./store.js";
import { clearTerminal } from "./term.js";
import { restoreTranscript } from "./transcript-state.js";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

// 逐 token 流式下每个 text_delta 触发一次 Ink 全量重绘；按 40ms 合帧。
function createTextBatcher(emit: (text: string) => void) {
  let pending = "";
  let timer: ReturnType<typeof setTimeout> | null = null;

  const flush = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    if (!pending) return;
    const batched = pending;
    pending = "";
    emit(batched);
  };

  return {
    push(text: string): void {
      pending += text;
      if (!timer) timer = setTimeout(flush, 40);
    },
    flush,
    discard(): void {
      if (timer) clearTimeout(timer);
      timer = null;
      pending = "";
    },
  };
}

function createProvisionalBatcher(emit: (provisionId: string, text: string) => void) {
  const pending = new Map<string, string>();
  let timer: ReturnType<typeof setTimeout> | null = null;

  const flush = (provisionId?: string) => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }

    if (provisionId !== undefined) {
      const text = pending.get(provisionId);
      if (!text) return;
      pending.delete(provisionId);
      emit(provisionId, text);
      return;
    }

    for (const [id, text] of pending) {
      emit(id, text);
    }
    pending.clear();
  };

  return {
    push(provisionId: string, text: string): void {
      if (!provisionId || !text) return;
      pending.set(provisionId, `${pending.get(provisionId) ?? ""}${text}`);
      if (!timer) timer = setTimeout(flush, 40);
    },
    flush,
    discard(): void {
      if (timer) clearTimeout(timer);
      timer = null;
      pending.clear();
    },
  };
}

type TextBatcher = ReturnType<typeof createTextBatcher>;
type ProvisionalBatcher = ReturnType<typeof createProvisionalBatcher>;

function applyBatchedStreamEvent(
  event: StreamEvent,
  messageBatcher: TextBatcher,
  provisionalBatcher: ProvisionalBatcher,
  applyEvent: (event: StreamEvent) => void,
): StreamTerminalStatus | null {
  if (event.type === "message") {
    provisionalBatcher.flush();
    messageBatcher.push(event.text);
    return null;
  }

  if (event.type === "provisional_text_delta") {
    messageBatcher.flush();
    provisionalBatcher.push(event.provisionId, event.text);
    return null;
  }

  messageBatcher.flush();
  if (event.type === "provisional_commit" || event.type === "provisional_retract") {
    provisionalBatcher.flush(event.provisionId);
  } else {
    provisionalBatcher.flush();
  }
  applyEvent(event);
  return event.type === "done" ? event.status : null;
}

export class NodeBridge {
  private activeRequest: AbortController | null = null;

  constructor(private store: StoreApi<AppStore>) {}

  private get s() {
    return this.store.getState();
  }

  cancelRequest(): boolean {
    const controller = this.activeRequest;
    if (!controller || controller.signal.aborted) return false;

    controller.abort();
    this.s.closeTurn();
    this.s.set({ busy: false, statusLine: "Cancelled." });
    return true;
  }

  async boot(): Promise<void> {
    try {
      const server = await ensureLocalServer();
      this.s.set({
        baseUrl: server.baseUrl,
        statusLine: server.note ?? (server.started ? "Local server started." : "Connected to local server."),
      });

      const config = await getLlmConfig(server.baseUrl);
      this.s.set({ config });
      if (!config.configured) {
        const setupDraft = createSetupDraft(config);
        this.s.set({
          mode: "setup",
          setupFlow: "initial",
          setupDraft,
          setupIndex: 0,
          inputValue: setupDraft.provider,
          statusLine: "Run the initial setup to wake Smith up.",
        });
        return;
      }

      await this.hydrateShell(server.baseUrl);
    } catch (error) {
      const message = errorMessage(error);
      this.s.set({
        mode: "chat",
        panel: "welcome",
        statusLine: `Boot failed: ${message}`,
        welcomeNotice: { text: message, tone: "error" },
      });
    }
  }

  async hydrateShell(baseUrl: string, bootNotes: string[] = []): Promise<void> {
    const config = this.s.config;
    if (!config) throw new Error("LLM configuration is unavailable.");

    const agent = await ensureAgentProfile(baseUrl);
    const warnings: string[] = [];
    const [sessions, skills] = await Promise.all([
      listSessions(baseUrl).catch((error: unknown) => {
        warnings.push(`Sessions unavailable: ${errorMessage(error)}`);
        return [];
      }),
      listSkills(baseUrl).catch((error: unknown) => {
        warnings.push(`Skills unavailable: ${errorMessage(error)}`);
        return [];
      }),
    ]);

    this.s.hydrate({ agent, sessions, skills, config, notices: [...bootNotes, ...warnings] });
  }

  async saveConfig(input: LlmConfigInput): Promise<void> {
    const { baseUrl } = this.s;
    this.s.set({ busy: true, statusLine: "Saving configuration…" });
    try {
      const saved = await setLlmConfig(baseUrl, input);
      this.s.set({ config: saved });
      if (!saved.configured) {
        this.s.set({
          mode: "setup",
          setupIndex: 0,
          statusLine: "Interactive LLM route still needs an API key, base URL, and model.",
        });
        return;
      }
      await this.hydrateShell(baseUrl);
    } catch (error) {
      this.s.set({ statusLine: `Save failed: ${errorMessage(error)}` });
    } finally {
      this.s.set({ busy: false });
    }
  }

  async refreshSkills(): Promise<void> {
    const { baseUrl, agent } = this.s;
    if (baseUrl && agent) this.s.set({ skills: await listSkills(baseUrl) });
  }

  async resumeSession(session: Session): Promise<void> {
    const { baseUrl } = this.s;
    try {
      const messages = await listMessages(baseUrl, session.id);
      const transcript = restoreTranscript(messages);
      clearTerminal();
      this.s.set({
        currentSession: session,
        transcript,
        transcriptEpoch: this.s.transcriptEpoch + 1,
        turnCount: transcript.filter((entry) => entry.kind === "turn").length,
        toolActivity: createToolActivity(),
        tokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
        panel: "chat",
        statusLine: `Resumed ${session.id} (${messages.length} messages).`,
      });
    } catch {
      this.s.set({ currentSession: session, panel: "chat" });
      this.s.pushSystemLine(`Resumed ${session.id} (history unavailable).`);
    }
  }

  async sendMessage(text: string, skillName?: string): Promise<void> {
    const ready = this.getReadySession();
    if (!ready) return;

    const controller = this.startRequest();
    // 回显先于建会话的网络往返：失败时该轮也留在转录里，由 reportRequestError 收尾。
    this.s.pushTurn(text);
    try {
      const session = await this.getOrCreateSession(ready.baseUrl, ready.currentSession, text);
      await this.streamResponse(ready.baseUrl, session, text, skillName, controller.signal);
      this.s.closeTurn();
      await this.refreshSessions(ready.baseUrl, session, ready.currentSession === null);
    } catch (error) {
      if (!controller.signal.aborted) this.reportRequestError(error);
    } finally {
      this.finishRequest(controller);
    }
  }

  private getReadySession(): { baseUrl: string; currentSession: Session | null } | null {
    const { baseUrl, agent, currentSession } = this.s;
    if (baseUrl && agent) return { baseUrl, currentSession };

    this.s.set({ statusLine: "Shell is not ready yet." });
    return null;
  }

  private startRequest(): AbortController {
    this.activeRequest?.abort();
    const controller = new AbortController();
    this.activeRequest = controller;
    this.s.set({ busy: true, panel: "chat", statusLine: "Processing…" });
    return controller;
  }

  private finishRequest(controller: AbortController): void {
    if (this.activeRequest !== controller) return;

    this.activeRequest = null;
    this.s.set({ busy: false });
  }

  private async getOrCreateSession(baseUrl: string, currentSession: Session | null, text: string): Promise<Session> {
    if (currentSession) return currentSession;

    const title = text.trim().split(/\n+/)[0]?.slice(0, 40) || "Smith Session";
    const session = await createSession(baseUrl, title);
    this.s.set({ currentSession: session });
    return session;
  }

  private async streamResponse(
    baseUrl: string,
    session: Session,
    text: string,
    skillName: string | undefined,
    signal: AbortSignal,
  ): Promise<void> {
    let terminalStatus: StreamTerminalStatus | null = null;
    const messageBatcher = createTextBatcher((batched) => this.s.applyEvent({ type: "message", text: batched }));
    const provisionalBatcher = createProvisionalBatcher((provisionId, batched) =>
      this.s.applyEvent({ type: "provisional_text_delta", provisionId, text: batched }),
    );

    try {
      for await (const event of streamMessage(baseUrl, session.id, text, { skillName, signal })) {
        const status = applyBatchedStreamEvent(event, messageBatcher, provisionalBatcher, (next) =>
          this.s.applyEvent(next),
        );
        if (status) terminalStatus = status;
      }
    } finally {
      // 取消后该轮已被 closeTurn 定格，迟到的文本不再写入。
      if (signal.aborted) {
        messageBatcher.discard();
        provisionalBatcher.discard();
      } else {
        messageBatcher.flush();
        provisionalBatcher.flush();
      }
    }

    if (!terminalStatus) throw new Error("SSE stream ended before completion.");
    if (terminalStatus === "completed") {
      this.s.set({ statusLine: "Ready. Type the next task or /help." });
      return;
    }

    const message =
      terminalStatus === "incomplete"
        ? "Model output limit reached; the answer may be incomplete."
        : "Agent execution failed; see the transcript and server log for details.";
    this.s.pushSystemLine(`[warning] ${message}`, "error");
    this.s.set({ statusLine: message });
  }

  private async refreshSessions(baseUrl: string, session: Session, selectSession: boolean): Promise<void> {
    try {
      const sessions = await listSessions(baseUrl);
      this.s.set({ sessions });
      if (!selectSession) return;

      const currentSession = sessions.find((item) => item.id === session.id);
      if (currentSession) this.s.set({ currentSession });
    } catch (error) {
      this.s.pushSystemLine(`Session list unavailable: ${errorMessage(error)}`);
    }
  }

  private reportRequestError(error: unknown): void {
    const message = errorMessage(error);
    this.s.closeTurn();
    this.s.pushSystemLine(`[error] ${message}`, "error");
    this.s.set({ statusLine: `Request failed: ${message}` });
  }
}
