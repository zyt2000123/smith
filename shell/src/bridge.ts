/**
 * NodeBridge — all backend communication goes through here.
 * UI components never call api.ts directly; they call bridge methods.
 */

import type { StoreApi } from "zustand/vanilla";

import { createToolActivity } from "./activity.js";
import {
  compressSession,
  createSession,
  deleteSession,
  ensureAgentProfile,
  getLlmConfig,
  getTokenStats,
  type LlmConfigInput,
  listMcpServers,
  listMessages,
  listSessions,
  listSkills,
  resolveRunApproval,
  type Session,
  type StreamEvent,
  type StreamTerminalStatus,
  setLlmConfig,
  streamMessage,
  updateSessionModel,
} from "./api.js";
import { ensureLocalServer } from "./dev-server.js";
import { MAX_QUEUED_MESSAGES, type QueuedMessage } from "./queue.js";
import { createSetupDraft } from "./setup.js";
import { type AppStore, TRANSCRIPT_LIMIT } from "./store.js";
import { clearTerminal } from "./term.js";
import { limitTranscript, removeApprovalNotice, restoreTranscript } from "./transcript-state.js";

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

  enqueueMessage(text: string, skillName?: string): boolean {
    const normalized = text.trim();
    if (!normalized) return false;

    const queuedMessages = this.s.queuedMessages;
    if (queuedMessages.length >= MAX_QUEUED_MESSAGES) {
      this.s.set({ statusLine: `Queue is full (${MAX_QUEUED_MESSAGES}). Press Esc to remove the newest message.` });
      return false;
    }

    const item: QueuedMessage = {
      id: `queue-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      text: normalized,
      ...(skillName ? { skillName } : {}),
    };
    this.s.set({
      queuedMessages: [...queuedMessages, item],
      statusLine: `Queued ${queuedMessages.length + 1}/${MAX_QUEUED_MESSAGES}.`,
    });
    return true;
  }

  removeQueuedMessage(index: number): QueuedMessage | null {
    const queuedMessages = this.s.queuedMessages;
    const removed = queuedMessages[index];
    if (!removed) return null;

    this.s.set({ queuedMessages: queuedMessages.filter((_item, itemIndex) => itemIndex !== index) });
    return removed;
  }

  removeLatestQueuedMessage(): QueuedMessage | null {
    return this.removeQueuedMessage(this.s.queuedMessages.length - 1);
  }

  cancelRequest(): boolean {
    const controller = this.activeRequest;
    if (!controller || controller.signal.aborted) return false;

    controller.abort();
    this.s.closeTurn();
    const pendingApproval = this.s.pendingApproval;
    this.s.set({
      pendingApproval: null,
      approvalResolving: false,
      busy: false,
      runStartedAt: null,
      statusLine: "Cancelled.",
      ...(pendingApproval ? { transcript: removeApprovalNotice(this.s.transcript, pendingApproval.approvalId) } : {}),
    });
    return true;
  }

  async resolveApproval(approved: boolean): Promise<void> {
    const pending = this.s.pendingApproval;
    if (!pending) {
      this.s.set({ statusLine: "No approval is waiting." });
      return;
    }
    if (this.s.approvalResolving) return;

    this.s.set({
      approvalResolving: true,
      statusLine: approved ? "Allowing the requested action…" : "Denying the requested action…",
    });
    try {
      await resolveRunApproval(this.s.baseUrl, pending.runId, pending.approvalId, approved);
      this.s.set({
        pendingApproval: null,
        transcript: removeApprovalNotice(this.s.transcript, pending.approvalId),
        statusLine: approved ? "Approval granted. Continuing…" : "Approval denied. Continuing safely…",
      });
    } catch (error) {
      this.s.set({ statusLine: `Approval update failed: ${errorMessage(error)}` });
    } finally {
      this.s.set({ approvalResolving: false });
    }
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

    this.s.hydrate({
      agent,
      sessions,
      skills,
      mcpServers: this.s.mcpServers,
      config,
      notices: [...bootNotes, ...warnings],
    });
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

  async refreshMcpServers(): Promise<void> {
    const { baseUrl, agent } = this.s;
    if (!baseUrl || !agent) return;
    try {
      this.s.set({ mcpServers: await listMcpServers(baseUrl) });
    } catch (error) {
      this.s.pushSystemLine(`MCP unavailable: ${errorMessage(error)}`, "error");
    }
  }

  async openTokenStats(): Promise<void> {
    const { baseUrl } = this.s;
    if (!baseUrl) {
      this.s.set({ statusLine: "Shell is not ready yet." });
      return;
    }
    this.s.set({ panel: "tokens", tokenStats: null, statusLine: "Loading token statistics…" });
    try {
      const tokenStats = await getTokenStats(baseUrl);
      this.s.set({ tokenStats, panel: "tokens", statusLine: "Token statistics ready." });
    } catch (error) {
      this.s.pushSystemLine(`Token statistics unavailable: ${errorMessage(error)}`, "error");
      this.s.set({ panel: "chat", statusLine: "Token statistics unavailable." });
    }
  }

  async selectModel(modelProfile: string | null): Promise<void> {
    const { baseUrl, config, currentSession } = this.s;
    if (modelProfile !== null && !config?.models?.[modelProfile]) {
      this.s.set({ statusLine: `Unknown model profile: ${modelProfile}` });
      return;
    }
    try {
      const session = currentSession ? await updateSessionModel(baseUrl, currentSession.id, modelProfile) : null;
      this.s.set({
        selectedModelProfile: modelProfile,
        ...(session ? { currentSession: session } : {}),
        statusLine: modelProfile ? `Model selected: ${modelProfile}.` : "Default model selected.",
      });
    } catch (error) {
      this.s.set({ statusLine: `Model selection failed: ${errorMessage(error)}` });
    }
  }

  async compressCurrentSession(): Promise<void> {
    const { baseUrl, currentSession, busy } = this.s;
    if (busy) {
      this.s.set({ statusLine: "Wait for the current task to finish before compressing." });
      return;
    }
    if (!currentSession) {
      this.s.set({ statusLine: "No active session to compress." });
      return;
    }
    this.s.set({ busy: true, compressing: true, panel: "chat", statusLine: "Automatically compressing context" });
    try {
      const result = await compressSession(baseUrl, currentSession.id);
      this.s.pushSystemLine(`Context compressed: ${result.message_count} messages summarized.`);
      this.s.set({ statusLine: "Context compressed. The next request will use the saved summary." });
    } catch (error) {
      this.s.pushSystemLine(`Context compression failed: ${errorMessage(error)}`, "error");
      this.s.set({ statusLine: "Context compression failed." });
    } finally {
      this.s.set({ busy: false, compressing: false });
    }
  }

  startNewSession(): boolean {
    if (this.activeRequest) {
      this.s.set({ statusLine: "Cancel the current task before starting a new session." });
      return false;
    }

    clearTerminal();
    this.s.startFreshSession();
    return true;
  }

  async clearCurrentSession(): Promise<boolean> {
    if (this.activeRequest) {
      this.s.set({ statusLine: "Cancel the current task before clearing the session." });
      return false;
    }

    const { baseUrl, currentSession } = this.s;
    if (currentSession) {
      try {
        await deleteSession(baseUrl, currentSession.id);
      } catch (error) {
        this.s.pushSystemLine(`Session deletion failed: ${errorMessage(error)}`, "error");
        this.s.set({ statusLine: "Session was not cleared because deletion failed." });
        return false;
      }
      this.s.set({ sessions: this.s.sessions.filter((session) => session.id !== currentSession.id) });
    }

    clearTerminal();
    this.s.startFreshSession();
    return true;
  }

  async resumeSession(session: Session): Promise<void> {
    const { baseUrl } = this.s;
    try {
      const messages = await listMessages(baseUrl, session.id);
      const transcript = limitTranscript(restoreTranscript(messages), TRANSCRIPT_LIMIT);
      clearTerminal();
      this.s.set({
        currentSession: session,
        selectedModelProfile: session.model_profile ?? null,
        transcript,
        transcriptEpoch: this.s.transcriptEpoch + 1,
        turnCount: transcript.filter((entry) => entry.kind === "turn").length,
        toolActivity: createToolActivity(),
        turnTokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
        tokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
        contextUsage: {
          context_tokens: 0,
          context_window: 256_000,
          context_percent: 0,
          estimated: true,
        },
        queuedMessages: [],
        panel: "chat",
        statusLine: `Resumed ${session.id} (${messages.length} messages).`,
      });
    } catch {
      this.s.set({ currentSession: session, panel: "chat", queuedMessages: [] });
      this.s.pushSystemLine(`Resumed ${session.id} (history unavailable).`);
    }
  }

  async sendMessage(text: string, skillName?: string): Promise<boolean> {
    if (this.activeRequest) return this.enqueueMessage(text, skillName);

    const ready = this.getReadySession();
    if (!ready) return false;

    const controller = this.startRequest();
    // 回显先于建会话的网络往返：失败时该轮也留在转录里，由 reportRequestError 收尾。
    this.s.pushTurn(text);
    try {
      const session = await this.getOrCreateSession(ready.baseUrl, ready.currentSession, text, controller.signal);
      if (controller.signal.aborted) return true;
      await this.streamResponse(ready.baseUrl, session, text, skillName, controller.signal);
      if (controller.signal.aborted) return true;
      this.s.closeTurn();
      await this.refreshSessions(ready.baseUrl, session, ready.currentSession === null, controller.signal);
    } catch (error) {
      if (!controller.signal.aborted) this.reportRequestError(error);
    } finally {
      this.finishRequest(controller);
    }
    return true;
  }

  private getReadySession(): { baseUrl: string; currentSession: Session | null } | null {
    const { baseUrl, agent, currentSession } = this.s;
    if (baseUrl && agent) return { baseUrl, currentSession };

    this.s.set({ statusLine: "Shell is not ready yet." });
    return null;
  }

  private startRequest(): AbortController {
    const controller = new AbortController();
    this.activeRequest = controller;
    this.s.set({ busy: true, compressing: false, runStartedAt: Date.now(), panel: "chat", statusLine: "Processing…" });
    return controller;
  }

  private finishRequest(controller: AbortController): void {
    if (this.activeRequest !== controller) return;

    this.activeRequest = null;
    const next = this.takeQueuedMessage();
    if (next) {
      this.s.set({ pendingApproval: null, approvalResolving: false });
      void this.sendMessage(next.text, next.skillName).then((accepted) => {
        if (!accepted) this.enqueueMessage(next.text, next.skillName);
      });
      return;
    }
    this.s.set({
      pendingApproval: null,
      approvalResolving: false,
      busy: false,
      compressing: false,
      runStartedAt: null,
    });
  }

  private takeQueuedMessage(): QueuedMessage | null {
    const next = this.s.queuedMessages[0];
    if (!next) return null;

    this.s.set({ queuedMessages: this.s.queuedMessages.slice(1) });
    return next;
  }

  private async getOrCreateSession(
    baseUrl: string,
    currentSession: Session | null,
    text: string,
    signal: AbortSignal,
  ): Promise<Session> {
    if (currentSession) return currentSession;

    const title = text.trim().split(/\n+/)[0]?.slice(0, 40) || "Smith Session";
    const session = await createSession(baseUrl, title, this.s.selectedModelProfile, { signal });
    if (signal.aborted) {
      throw signal.reason ?? new DOMException("The request was aborted.", "AbortError");
    }
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
      for await (const event of streamMessage(baseUrl, session.id, text, {
        skillName,
        workingDir: process.env.SMITH_PROJECT_CWD?.trim() || process.cwd(),
        signal,
      })) {
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

  private async refreshSessions(
    baseUrl: string,
    session: Session,
    selectSession: boolean,
    signal: AbortSignal,
  ): Promise<void> {
    try {
      const sessions = await listSessions(baseUrl, { signal });
      if (signal.aborted) return;
      this.s.set({ sessions });
      if (!selectSession) return;

      const currentSession = sessions.find((item) => item.id === session.id);
      if (currentSession) this.s.set({ currentSession });
    } catch (error) {
      if (signal.aborted) return;
      this.s.pushSystemLine(`Session list unavailable: ${errorMessage(error)}`);
    }
  }

  private reportRequestError(error: unknown): void {
    const message = errorMessage(error);
    this.s.closeTurn();
    this.s.pushSystemLine(`[error] ${message}`, "error");
    this.s.set({ statusLine: "Request failed. See the transcript for details." });
  }
}
