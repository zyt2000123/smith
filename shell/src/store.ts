/**
 * Zustand store — all shell state in one place.
 * Components read via useAppStore(selector), never own useState for app state.
 */

import { createStore } from "zustand/vanilla";
import { applyToolActivity, createToolActivity, type ToolActivity } from "./activity.js";
import type { AgentProfile, LlmConfig, Session, SkillSummary, StreamEvent, TokenUsage } from "./api.js";
import { createEmptyConversation } from "./conversation.js";
import { HISTORY_LIMIT } from "./history.js";
import {
  applyStreamEvent,
  closeLatestTurn,
  createSystemEntry,
  createTurnEntry,
  type TranscriptEntry,
  type TranscriptViewMode,
} from "./transcript-state.js";

export type Panel = "welcome" | "chat" | "sessions" | "skills";
export type Mode = "boot" | "setup" | "chat";
export type SetupFlow = "initial" | "advanced";

export type SetupDraft = {
  provider: string;
  base_url: string;
  api_key: string;
  model: string;
  review_model: string;
  max_output_tokens: string;
  routes: string;
  interactive_api_key: string;
  gate_api_key: string;
  background_api_key: string;
  timeout_profiles: string;
};

export type AppState = {
  mode: Mode;
  panel: Panel;
  baseUrl: string;
  config: LlmConfig | null;
  agent: AgentProfile | null;
  sessions: Session[];
  skills: SkillSummary[];
  currentSession: Session | null;
  transcript: TranscriptEntry[];
  /** Bumped whenever the transcript is replaced wholesale — remounts <Static>. */
  transcriptEpoch: number;
  turnCount: number;
  toolActivity: ToolActivity;
  tokenUsage: TokenUsage;
  viewMode: TranscriptViewMode;
  pendingSkill: SkillSummary | null;
  busy: boolean;
  inputValue: string;
  inputHistory: string[];
  historyIndex: number;
  statusLine: string;
  setupDraft: SetupDraft;
  setupFlow: SetupFlow;
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
  clearChat: () => void;
  hydrate: (opts: {
    agent: AgentProfile;
    sessions: Session[];
    skills: SkillSummary[];
    config: LlmConfig;
    notices?: string[];
  }) => void;
};

export type AppStore = AppState & AppActions;

type HydrateOptions = {
  agent: AgentProfile;
  sessions: Session[];
  skills: SkillSummary[];
  config: LlmConfig;
  notices?: string[];
};

function hydrateShellState(state: AppState, options: HydrateOptions): Partial<AppState> {
  const notices = options.notices ?? [];
  const hasWarnings = notices.some((notice) => notice.includes("unavailable") || notice.includes("could not"));
  return {
    agent: options.agent,
    sessions: options.sessions,
    skills: options.skills,
    config: options.config,
    mode: "chat",
    panel: state.transcript.length > 0 ? "chat" : "welcome",
    inputValue: "",
    welcomeNotice: notices.length > 0 ? { text: notices.join("\n"), tone: hasWarnings ? "error" : "info" } : null,
    statusLine: hasWarnings ? "Ready, with warnings. Type / for commands." : "Ready. Type / for commands and skills.",
  };
}

export function createAppStore(initialHistory: string[] = []) {
  return createStore<AppStore>((set) => ({
    mode: "boot",
    panel: "welcome",
    baseUrl: "",
    config: null,
    agent: null,
    sessions: [],
    skills: [],
    currentSession: null,
    transcript: [],
    transcriptEpoch: 0,
    turnCount: 0,
    toolActivity: createToolActivity(),
    tokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
    viewMode: "compact",
    pendingSkill: null,
    busy: false,
    inputValue: "",
    inputHistory: initialHistory,
    historyIndex: -1,
    statusLine: "Booting Smith…",
    setupDraft: {
      provider: "openai",
      base_url: "https://api.openai.com/v1",
      api_key: "",
      model: "gpt-4.1-mini",
      review_model: "",
      max_output_tokens: "",
      routes: "",
      interactive_api_key: "",
      gate_api_key: "",
      background_api_key: "",
      timeout_profiles: "",
    },
    setupFlow: "initial",
    setupIndex: 0,
    slashIndex: 0,
    welcomeNotice: null,

    set: (partial) => set(partial),

    pushHistory: (text) =>
      set((s) => ({
        inputHistory:
          s.inputHistory[s.inputHistory.length - 1] === text
            ? s.inputHistory
            : [...s.inputHistory, text].slice(-HISTORY_LIMIT),
        historyIndex: -1,
      })),
    pushSystemLine: (text, tone = "info") =>
      set((s) => ({ transcript: [...s.transcript, createSystemEntry(text, tone)] })),
    pushTurn: (userText) =>
      set((s) => ({
        transcript: [...s.transcript, createTurnEntry(userText)],
        turnCount: s.turnCount + 1,
      })),
    applyEvent: (event) =>
      set((s) =>
        event.type === "token_usage"
          ? {
              toolActivity: applyToolActivity(s.toolActivity, event),
              tokenUsage: {
                input_tokens: s.tokenUsage.input_tokens + event.input_tokens,
                output_tokens: s.tokenUsage.output_tokens + event.output_tokens,
                total_tokens: s.tokenUsage.total_tokens + event.total_tokens,
              },
            }
          : {
              toolActivity: applyToolActivity(s.toolActivity, event),
              transcript: applyStreamEvent(s.transcript, event),
            },
      ),
    closeTurn: () => set((s) => ({ transcript: closeLatestTurn(s.transcript) })),

    resetChat: () =>
      set((s) => ({
        ...createEmptyConversation("welcome", "Fresh shell ready."),
        transcriptEpoch: s.transcriptEpoch + 1,
      })),
    clearChat: () =>
      set((s) => ({
        ...createEmptyConversation("chat", "Conversation cleared. Next message starts a fresh session."),
        transcriptEpoch: s.transcriptEpoch + 1,
      })),

    hydrate: (options) => {
      // 不清空 transcript/currentSession：mid-session /config 保存也走这里，进行中的会话要保留
      set((state) => hydrateShellState(state, options));
    },
  }));
}
