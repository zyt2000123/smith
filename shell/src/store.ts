/**
 * Zustand store — all shell state in one place.
 * Components read via useAppStore(selector), never own useState for app state.
 */

import { createStore } from "zustand/vanilla";
import type { AgentProfile, LlmConfig, PluginManifest, Session, SkillSummary, StreamEvent, TokenUsage } from "./api.js";
import {
  applyStreamEvent,
  closeLatestTurn,
  createSystemEntry,
  createTurnEntry,
  type TranscriptEntry,
  type TranscriptViewMode,
} from "./transcript.js";

export type Panel = "welcome" | "chat" | "sessions" | "plugins" | "skills";
export type Mode = "boot" | "setup" | "chat";

export type SetupDraft = {
  provider: string;
  base_url: string;
  model: string;
  api_key: string;
};

export type AppState = {
  mode: Mode;
  panel: Panel;
  baseUrl: string;
  config: LlmConfig | null;
  agent: AgentProfile | null;
  sessions: Session[];
  plugins: PluginManifest[];
  skills: SkillSummary[];
  currentSession: Session | null;
  transcript: TranscriptEntry[];
  tokenUsage: TokenUsage;
  viewMode: TranscriptViewMode;
  pendingSkill: SkillSummary | null;
  busy: boolean;
  inputValue: string;
  inputHistory: string[];
  historyIndex: number;
  statusLine: string;
  setupDraft: SetupDraft;
  setupIndex: number;
  slashIndex: number;
  welcomeNotice: { text: string; tone: "info" | "error" } | null;
};

export type AppActions = {
  set: (partial: Partial<AppState>) => void;
  pushSystemLine: (text: string, tone?: "info" | "error") => void;
  pushHistory: (text: string) => void;
  pushTurn: (userText: string) => void;
  applyEvent: (event: StreamEvent) => void;
  closeTurn: () => void;
  resetChat: () => void;
  hydrate: (opts: {
    agent: AgentProfile;
    sessions: Session[];
    plugins: PluginManifest[];
    skills: SkillSummary[];
    config: LlmConfig;
    notices?: string[];
  }) => void;
};

export type AppStore = AppState & AppActions;

export function createAppStore() {
  return createStore<AppStore>((set) => ({
    mode: "boot",
    panel: "welcome",
    baseUrl: "",
    config: null,
    agent: null,
    sessions: [],
    plugins: [],
    skills: [],
    currentSession: null,
    transcript: [],
    tokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
    viewMode: "compact",
    pendingSkill: null,
    busy: false,
    inputValue: "",
    inputHistory: [],
    historyIndex: -1,
    statusLine: "Booting Smith…",
    setupDraft: { provider: "openai", base_url: "https://api.openai.com/v1", model: "gpt-4.1-mini", api_key: "" },
    setupIndex: 0,
    slashIndex: 0,
    welcomeNotice: null,

    set: (partial) => set(partial),

    pushHistory: (text) => set((s) => ({ inputHistory: [...s.inputHistory, text], historyIndex: -1 })),
    pushSystemLine: (text, tone = "info") =>
      set((s) => ({ transcript: [...s.transcript, createSystemEntry(text, tone)] })),
    pushTurn: (userText) => set((s) => ({ transcript: [...s.transcript, createTurnEntry(userText)] })),
    applyEvent: (event) =>
      set((s) =>
        event.type === "token_usage"
          ? {
              tokenUsage: {
                input_tokens: s.tokenUsage.input_tokens + event.input_tokens,
                output_tokens: s.tokenUsage.output_tokens + event.output_tokens,
                total_tokens: s.tokenUsage.total_tokens + event.total_tokens,
              },
            }
          : { transcript: applyStreamEvent(s.transcript, event) },
      ),
    closeTurn: () => set((s) => ({ transcript: closeLatestTurn(s.transcript) })),

    resetChat: () =>
      set({
        currentSession: null,
        transcript: [],
        tokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
        pendingSkill: null,
        welcomeNotice: null,
        panel: "welcome",
        statusLine: "Fresh shell ready.",
      }),

    hydrate: ({ agent, sessions, plugins, skills, config, notices = [] }) => {
      const hasWarnings = notices.some((n) => n.includes("unavailable") || n.includes("could not"));
      // 不清空 transcript/currentSession：mid-session /config 保存也走这里，进行中的会话要保留
      set((s) => ({
        agent,
        sessions,
        plugins,
        skills,
        config,
        mode: "chat",
        panel: s.transcript.length > 0 ? "chat" : "welcome",
        inputValue: "",
        welcomeNotice: notices.length > 0 ? { text: notices.join("\n"), tone: hasWarnings ? "error" : "info" } : null,
        statusLine: hasWarnings
          ? "Ready, with warnings. Type / for commands."
          : "Ready. Type / for commands and skills.",
      }));
    },
  }));
}
