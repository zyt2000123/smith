/**
 * Zustand store — all shell state in one place.
 * Components read via useAppStore(selector), never own useState for app state.
 */

import { createStore } from "zustand/vanilla";
import { applyToolActivity, createToolActivity, type ToolActivity } from "./activity.js";
import type {
  AgentProfile,
  ContextUsage,
  LlmConfig,
  McpServer,
  PendingApproval,
  Session,
  SkillSummary,
  StreamEvent,
  TokenStats,
  TokenUsage,
} from "./api.js";
import { CONTEXT_DISPLAY_WINDOW } from "./api.js";
import { createEmptyConversation } from "./conversation.js";
import { HISTORY_LIMIT } from "./history.js";
import type { QueuedMessage } from "./queue.js";
import type { TokenTab } from "./token-stats.js";
import {
  applyStreamEvent,
  closeLatestTurn,
  createSystemEntry,
  createTurnEntry,
  limitTranscript,
  type TranscriptEntry,
  type TranscriptViewMode,
} from "./transcript-state.js";

export type Panel = "welcome" | "chat" | "sessions" | "skills" | "mcp" | "tokens";
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
  models: string;
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
  mcpServers: McpServer[];
  currentSession: Session | null;
  selectedModelProfile: string | null;
  transcript: TranscriptEntry[];
  /** Bumped whenever the transcript is replaced wholesale — remounts <Static>. */
  transcriptEpoch: number;
  turnCount: number;
  toolActivity: ToolActivity;
  /** Token usage accumulated across the current user message and its agent work. */
  turnTokenUsage: TokenUsage;
  tokenUsage: TokenUsage;
  contextUsage: ContextUsage;
  tokenStats: TokenStats | null;
  tokenTab: TokenTab;
  viewMode: TranscriptViewMode;
  pendingSkill: SkillSummary | null;
  queuedMessages: QueuedMessage[];
  busy: boolean;
  compressing: boolean;
  runStartedAt: number | null;
  pendingApproval: PendingApproval | null;
  approvalIndex: number;
  approvalResolving: boolean;
  inputValue: string;
  inputHistory: string[];
  historyIndex: number;
  statusLine: string;
  setupDraft: SetupDraft;
  setupFlow: SetupFlow;
  setupIndex: number;
  slashIndex: number;
  skillsIndex: number;
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
  startFreshSession: () => void;
  hydrate: (opts: {
    agent: AgentProfile;
    sessions: Session[];
    skills: SkillSummary[];
    mcpServers: McpServer[];
    config: LlmConfig;
    notices?: string[];
  }) => void;
};

export type AppStore = AppState & AppActions;

export const TRANSCRIPT_LIMIT = 200;

type HydrateOptions = {
  agent: AgentProfile;
  sessions: Session[];
  skills: SkillSummary[];
  mcpServers: McpServer[];
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
    mcpServers: options.mcpServers,
    config: options.config,
    mode: "chat",
    panel: state.transcript.length > 0 ? "chat" : "welcome",
    inputValue: "",
    welcomeNotice: notices.length > 0 ? { text: notices.join("\n"), tone: hasWarnings ? "error" : "info" } : null,
    statusLine: hasWarnings ? "Ready, with warnings. Type / for commands." : "Ready. Type / for commands and skills.",
  };
}

function applyStreamState(state: AppState, event: StreamEvent): Partial<AppState> {
  if (event.type === "token_usage") {
    return {
      toolActivity: applyToolActivity(state.toolActivity, event),
      turnTokenUsage: {
        input_tokens: state.turnTokenUsage.input_tokens + event.input_tokens,
        output_tokens: state.turnTokenUsage.output_tokens + event.output_tokens,
        total_tokens: state.turnTokenUsage.total_tokens + event.total_tokens,
      },
      tokenUsage: {
        input_tokens: state.tokenUsage.input_tokens + event.input_tokens,
        output_tokens: state.tokenUsage.output_tokens + event.output_tokens,
        total_tokens: state.tokenUsage.total_tokens + event.total_tokens,
      },
    };
  }

  if (event.type === "context_usage") {
    return {
      contextUsage: event,
      toolActivity: applyToolActivity(state.toolActivity, event),
      transcript: applyStreamEvent(state.transcript, event),
    };
  }

  if (event.type === "compression") {
    return {
      compressing: event.active,
      toolActivity: applyToolActivity(state.toolActivity, event),
      transcript: applyStreamEvent(state.transcript, event),
    };
  }

  if (event.type === "done") {
    return {
      pendingApproval: null,
      approvalResolving: false,
      toolActivity: applyToolActivity(state.toolActivity, event),
      transcript: applyStreamEvent(state.transcript, event),
    };
  }

  if (event.type === "approval_required") {
    return {
      pendingApproval: event,
      approvalIndex: 0,
      approvalResolving: false,
      statusLine: "Approval required. Review the request and choose Allow or Deny.",
      toolActivity: applyToolActivity(state.toolActivity, event),
      transcript: applyStreamEvent(state.transcript, event),
    };
  }

  return {
    toolActivity: applyToolActivity(state.toolActivity, event),
    transcript: applyStreamEvent(state.transcript, event),
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
    mcpServers: [],
    currentSession: null,
    selectedModelProfile: null,
    transcript: [],
    transcriptEpoch: 0,
    turnCount: 0,
    toolActivity: createToolActivity(),
    turnTokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
    tokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
    contextUsage: {
      context_tokens: 0,
      context_window: CONTEXT_DISPLAY_WINDOW,
      context_percent: 0,
      estimated: true,
    },
    tokenStats: null,
    tokenTab: "stats",
    viewMode: "compact",
    pendingSkill: null,
    queuedMessages: [],
    busy: false,
    compressing: false,
    runStartedAt: null,
    pendingApproval: null,
    approvalIndex: 0,
    approvalResolving: false,
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
      models: "",
      interactive_api_key: "",
      gate_api_key: "",
      background_api_key: "",
      timeout_profiles: "",
    },
    setupFlow: "initial",
    setupIndex: 0,
    slashIndex: 0,
    skillsIndex: 0,
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
      set((s) => ({ transcript: limitTranscript([...s.transcript, createSystemEntry(text, tone)], TRANSCRIPT_LIMIT) })),
    pushTurn: (userText) =>
      set((s) => ({
        transcript: limitTranscript([...s.transcript, createTurnEntry(userText)], TRANSCRIPT_LIMIT),
        turnCount: s.turnCount + 1,
        turnTokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
      })),
    applyEvent: (event) => set((state) => applyStreamState(state, event)),
    closeTurn: () => set((s) => ({ transcript: closeLatestTurn(s.transcript) })),

    resetChat: () =>
      set((s) => ({
        ...createEmptyConversation("welcome", "Fresh shell ready."),
        pendingApproval: null,
        approvalIndex: 0,
        approvalResolving: false,
        transcriptEpoch: s.transcriptEpoch + 1,
      })),
    clearChat: () =>
      set((s) => ({
        ...createEmptyConversation("chat", "Conversation cleared. Next message starts a fresh session."),
        pendingApproval: null,
        approvalIndex: 0,
        approvalResolving: false,
        transcriptEpoch: s.transcriptEpoch + 1,
      })),
    startFreshSession: () =>
      set((s) => ({
        ...createEmptyConversation("chat", "Fresh session ready."),
        pendingApproval: null,
        approvalIndex: 0,
        approvalResolving: false,
        transcriptEpoch: s.transcriptEpoch + 1,
      })),

    hydrate: (options) => {
      // 不清空 transcript/currentSession：mid-session /config 保存也走这里，进行中的会话要保留
      set((state) => hydrateShellState(state, options));
    },
  }));
}
