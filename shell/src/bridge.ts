/**
 * NodeBridge — all backend communication goes through here.
 * UI components never call api.ts directly; they call bridge methods.
 */

import type { StoreApi } from "zustand/vanilla";
import {
  createSession,
  disablePlugin,
  enablePlugin,
  ensureAgentProfile,
  getLlmConfig,
  type LlmConfigInput,
  listMessages,
  listPlugins,
  listSessions,
  listSkills,
  setLlmConfig,
  streamMessage,
} from "./api.js";
import { ensureLocalServer } from "./dev-server.js";
import type { AppStore } from "./store.js";
import { createTurnEntry } from "./transcript.js";

export class NodeBridge {
  private abortController: AbortController | null = null;

  constructor(private store: StoreApi<AppStore>) {}

  cancelRequest(): void {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
      this.s.closeTurn();
      this.s.set({ busy: false, statusLine: "Cancelled." });
    }
  }

  private get s() {
    return this.store.getState();
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
        this.s.set({
          mode: "setup",
          setupIndex: 0,
          inputValue: "openai",
          statusLine: "Run the initial setup to wake Smith up.",
        });
        return;
      }

      await this.hydrateShell(server.baseUrl);
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.s.set({
        mode: "chat",
        panel: "welcome",
        statusLine: `Boot failed: ${msg}`,
        welcomeNotice: { text: msg, tone: "error" },
      });
    }
  }

  async hydrateShell(baseUrl: string, bootNotes: string[] = []): Promise<void> {
    const agent = await ensureAgentProfile(baseUrl);
    const warnings: string[] = [];
    const [sessions, plugins, skills] = await Promise.all([
      listSessions(baseUrl).catch((e: unknown) => {
        warnings.push(`Sessions unavailable: ${e instanceof Error ? e.message : e}`);
        return [];
      }),
      listPlugins(baseUrl),
      listSkills(baseUrl).catch((e: unknown) => {
        warnings.push(`Skills unavailable: ${e instanceof Error ? e.message : e}`);
        return [];
      }),
    ]);

    const config = this.s.config!;
    this.s.hydrate({ agent, sessions, plugins, skills, config, notices: [...bootNotes, ...warnings] });
  }

  async saveConfig(input: LlmConfigInput): Promise<void> {
    const { baseUrl } = this.s;
    this.s.set({ busy: true, statusLine: "Saving configuration…" });
    try {
      const saved = await setLlmConfig(baseUrl, input);
      this.s.set({ config: saved });
      await this.hydrateShell(baseUrl);
    } catch (error) {
      this.s.set({ statusLine: `Save failed: ${error instanceof Error ? error.message : error}` });
    } finally {
      this.s.set({ busy: false });
    }
  }

  async refreshPlugins(): Promise<void> {
    const { baseUrl } = this.s;
    if (baseUrl) this.s.set({ plugins: await listPlugins(baseUrl) });
  }

  async refreshSkills(): Promise<void> {
    const { baseUrl, agent } = this.s;
    if (baseUrl && agent) this.s.set({ skills: await listSkills(baseUrl) });
  }

  async togglePlugin(name: string, enable: boolean): Promise<void> {
    const { baseUrl } = this.s;
    if (enable) await enablePlugin(baseUrl, name);
    else await disablePlugin(baseUrl, name);
    await this.refreshPlugins();
    this.s.set({ panel: "plugins", statusLine: `${enable ? "Enabled" : "Disabled"} plugin ${name}.` });
  }

  async resumeSession(session: import("./api.js").Session): Promise<void> {
    const { baseUrl } = this.s;
    try {
      const msgs = await listMessages(baseUrl, session.id);
      const entries = [];
      for (let i = 0; i < msgs.length; i++) {
        const msg = msgs[i]!;
        if (msg.role === "user") {
          const turn = createTurnEntry(msg.content);
          const next = msgs[i + 1];
          if (next?.role === "assistant") {
            turn.assistantText = next.content;
            turn.streaming = false;
            i++;
          } else {
            turn.streaming = false;
          }
          entries.push(turn);
        }
      }
      this.s.set({
        currentSession: session,
        transcript: entries,
        tokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
        panel: "chat",
        statusLine: `Resumed ${session.id} (${msgs.length} messages).`,
      });
    } catch {
      this.s.set({ currentSession: session, panel: "chat" });
      this.s.pushSystemLine(`Resumed ${session.id} (history unavailable).`);
    }
  }

  async sendMessage(text: string, skillName?: string): Promise<void> {
    const { baseUrl, agent, currentSession } = this.s;
    if (!baseUrl || !agent) {
      this.s.set({ statusLine: "Shell is not ready yet." });
      return;
    }

    this.s.set({ busy: true, panel: "chat", statusLine: "Processing…" });
    this.abortController = new AbortController();
    const { signal } = this.abortController;
    let session = currentSession;
    try {
      if (!session) {
        const title = text.trim().split(/\n+/)[0]?.slice(0, 40) || "Smith Session";
        session = await createSession(baseUrl, title);
        this.s.set({ currentSession: session });
      }

      this.s.pushTurn(text);
      for await (const event of streamMessage(baseUrl, session.id, text, { skillName, signal })) {
        this.s.applyEvent(event);
        if (event.type === "done") this.s.set({ statusLine: "Ready. Type the next task or /help." });
      }
      this.s.closeTurn();

      const updated = await listSessions(baseUrl);
      this.s.set({ sessions: updated });
      if (!currentSession) {
        const matched = updated.find((s) => s.id === session!.id);
        if (matched) this.s.set({ currentSession: matched });
      }
    } catch (error) {
      // User-initiated cancel: cancelRequest already closed the turn and set the status line.
      if (signal.aborted) return;
      this.s.closeTurn();
      this.s.pushSystemLine(`[error] ${error instanceof Error ? error.message : error}`, "error");
      this.s.set({ statusLine: `Request failed: ${error instanceof Error ? error.message : error}` });
    } finally {
      this.abortController = null;
      this.s.set({ busy: false });
    }
  }
}
