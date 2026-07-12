import { type Key, useInput } from "ink";
import type { MutableRefObject } from "react";

import type { SkillSummary } from "./api.js";
import type { NodeBridge } from "./bridge.js";
import type { SlashItem } from "./commands.js";
import { fieldValue, isEditableSetupField, nextSetupIndex, setSetupField, setupFieldAt } from "./setup.js";
import type { AppStore, Mode, Panel } from "./store.js";
import type { TranscriptViewMode } from "./transcript-state.js";

export type ShellInputOptions = {
  mode: Mode;
  busy: boolean;
  viewMode: TranscriptViewMode;
  slashMenuOpen: boolean;
  slashItems: SlashItem[];
  slashIndex: number;
  panel: Panel;
  pendingSkill: SkillSummary | null;
  configConfigured: boolean;
  exit: () => void;
  bridge: NodeBridge;
  getState: () => AppStore;
  suppressRef: MutableRefObject<string | null>;
};

function moveSetupSelection(options: ShellInputOptions, direction: 1 | -1): void {
  const state = options.getState();
  const field = setupFieldAt(state.setupIndex);
  const draft = isEditableSetupField(field)
    ? setSetupField(state.setupDraft, field, state.inputValue)
    : state.setupDraft;
  const index = nextSetupIndex(state.setupIndex, direction, true);
  const nextField = setupFieldAt(index);
  state.set({
    setupDraft: draft,
    setupIndex: index,
    inputValue: nextField === "save" ? "" : fieldValue(draft, nextField),
  });
}

function handleSetupInput(key: Key, options: ShellInputOptions): void {
  if (key.tab || key.downArrow) {
    moveSetupSelection(options, 1);
    return;
  }
  if (key.upArrow) {
    moveSetupSelection(options, -1);
    return;
  }
  if (key.escape && options.configConfigured) {
    options.getState().set({ mode: "chat", panel: "welcome", inputValue: "", statusLine: "Back." });
  }
}

function handleCtrlC(input: string, key: Key, options: ShellInputOptions): boolean {
  if (!key.ctrl || input !== "c") return false;

  if (options.busy && options.bridge.cancelRequest()) return true;

  options.exit();
  return true;
}

function handleViewToggle(input: string, key: Key, options: ShellInputOptions): boolean {
  if (!key.ctrl || input !== "o") return false;

  options.suppressRef.current = input;
  const viewMode = options.viewMode === "compact" ? "transcript" : "compact";
  options.getState().set({ viewMode, statusLine: `${viewMode} view.` });
  queueMicrotask(() => {
    const state = options.getState();
    if (state.inputValue.endsWith(input)) state.set({ inputValue: state.inputValue.slice(0, -input.length) });
  });
  return true;
}

function handleSlashNavigation(key: Key, options: ShellInputOptions): boolean {
  if (!options.slashMenuOpen || options.slashItems.length === 0) return false;

  const state = options.getState();
  if (key.tab) {
    const selected = options.slashItems[options.slashIndex];
    if (selected) state.set({ inputValue: selected.command });
    return true;
  }
  if (key.downArrow) {
    state.set({ slashIndex: (options.slashIndex + 1) % options.slashItems.length });
    return true;
  }
  if (key.upArrow) {
    state.set({ slashIndex: (options.slashIndex - 1 + options.slashItems.length) % options.slashItems.length });
    return true;
  }
  return false;
}

function handleEscape(key: Key, options: ShellInputOptions): boolean {
  if (!key.escape) return false;

  if (options.busy && options.bridge.cancelRequest()) return true;
  if (options.slashMenuOpen) {
    options.getState().set({ inputValue: "", slashIndex: 0 });
    return true;
  }
  if (options.pendingSkill) {
    options.getState().set({ pendingSkill: null, statusLine: "Cleared." });
    return true;
  }
  return false;
}

function handleHistoryNavigation(key: Key, options: ShellInputOptions): boolean {
  if (options.slashMenuOpen || (!key.upArrow && !key.downArrow)) return false;

  const state = options.getState();
  if (state.inputHistory.length === 0) return false;

  if (key.upArrow) {
    const index = state.historyIndex === -1 ? state.inputHistory.length - 1 : Math.max(0, state.historyIndex - 1);
    state.set({ historyIndex: index, inputValue: state.inputHistory[index] || "" });
    return true;
  }

  const index = state.historyIndex === -1 ? -1 : state.historyIndex + 1;
  if (index >= state.inputHistory.length) {
    state.set({ historyIndex: -1, inputValue: "" });
  } else {
    state.set({ historyIndex: index, inputValue: index === -1 ? "" : state.inputHistory[index] || "" });
  }
  return true;
}

function cyclePanel(key: Key, options: ShellInputOptions): void {
  if (!key.tab || options.slashMenuOpen) return;

  const panels: Panel[] = ["welcome", "sessions", "skills", "chat"];
  const index = panels.indexOf(options.panel);
  options.getState().set({ panel: panels[(index + 1) % panels.length] });
}

function routeInput(input: string, key: Key, options: ShellInputOptions): void {
  if (handleCtrlC(input, key, options)) return;
  if (options.mode === "setup") {
    handleSetupInput(key, options);
    return;
  }
  if (handleViewToggle(input, key, options)) return;
  if (handleSlashNavigation(key, options)) return;
  if (handleEscape(key, options)) return;
  if (handleHistoryNavigation(key, options)) return;
  cyclePanel(key, options);
}

export function useShellInput(options: ShellInputOptions): void {
  useInput((input, key) => {
    routeInput(input, key, options);
  });
}
