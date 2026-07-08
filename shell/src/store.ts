/**
 * Zustand store — all shell state in one place.
 * Components read via useAppStore(selector), never own useState for app state.
 */

import { createStore } from "zustand/vanilla";
import type { Employee, LlmConfig, PluginManifest, Session, SkillSummary, StreamEvent } from "./api.js";
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
  agent: Employee | null;
  sessions: Session[];
  plugins: PluginManifest[];
  skills: SkillSummary[];
  currentSession: Session | null;
  transcript: TranscriptEntry[];
  viewMode: TranscriptViewMode;
  pendingSkill: SkillSummary | null;
  busy: boolean;
  inputValue: string;
  statusLine: string;
  setupDraft: SetupDraft;
  setupIndex: number;
  slashIndex: number;
  welcomeNotice: { text: string; tone: "info" | "error" } | null;
};

export type AppActions = {
  set: (partial: Partial<AppState>) => void;
  pushSystemLine: (text: string, tone?: "info" | "error") => void;
  pushTurn: (userText: string) => void;
  applyEvent: (event: StreamEvent) => void;
  closeTurn: () => void;
  resetChat: () => void;
  hydrate: (opts: {
    agent: Employee;
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
    viewMode: "compact",
    pendingSkill: null,
    busy: false,
    inputValue: "",
    statusLine: "Booting Smith…",
    setupDraft: { provider: "openai", base_url: "https://api.openai.com/v1", model: "gpt-4.1-mini", api_key: "" },
    setupIndex: 0,
    slashIndex: 0,
    welcomeNotice: null,

    set: (partial) => set(partial),

    pushSystemLine: (text, tone = "info") =>
      set((s) => ({ transcript: [...s.transcript, createSystemEntry(text, tone)] })),
    pushTurn: (userText) => set((s) => ({ transcript: [...s.transcript, createTurnEntry(userText)] })),
    applyEvent: (event) => set((s) => ({ transcript: applyStreamEvent(s.transcript, event) })),
    closeTurn: () => set((s) => ({ transcript: closeLatestTurn(s.transcript) })),

    resetChat: () =>
      set({
        currentSession: null,
        transcript: [],
        pendingSkill: null,
        welcomeNotice: null,
        panel: "welcome",
        statusLine: "Fresh shell ready.",
      }),

    hydrate: ({ agent, sessions, plugins, skills, config, notices = [] }) => {
      const hasWarnings = notices.some((n) => n.includes("unavailable") || n.includes("could not"));
      set({
        agent,
        sessions,
        plugins,
        skills,
        config,
        mode: "chat",
        panel: "welcome",
        transcript: [],
        currentSession: null,
        pendingSkill: null,
        inputValue: "",
        welcomeNotice: notices.length > 0 ? { text: notices.join("\n"), tone: hasWarnings ? "error" : "info" } : null,
        statusLine: hasWarnings
          ? "Ready, with warnings. Type / for commands."
          : "Ready. Type / for commands and skills.",
      });
    },
  }));
}
