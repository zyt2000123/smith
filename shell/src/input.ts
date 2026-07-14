import { type Key, useInput } from "ink";
import type { MutableRefObject } from "react";

import type { SkillSummary } from "./api.js";
import type { NodeBridge } from "./bridge.js";
import type { SlashItem } from "./commands.js";
import {
  type ListNavigation,
  moveListIndex,
  SKILLS_PANEL_VISIBLE_ITEMS,
  SLASH_MENU_VISIBLE_ITEMS,
} from "./list-navigation.js";
import { advanceModelPicker, moveModelPicker } from "./model-picker.js";
import { fieldValue, isEditableSetupField, nextSetupIndex, setSetupField, setupFieldAt } from "./setup.js";
import type { AppStore, Mode, Panel } from "./store.js";
import { TOKEN_TABS } from "./token-stats.js";
import type { TranscriptViewMode } from "./transcript-state.js";

export type ShellInputOptions = {
  mode: Mode;
  setupFlow: AppStore["setupFlow"];
  busy: boolean;
  compressing: boolean;
  inputLocked: boolean;
  viewMode: TranscriptViewMode;
  slashMenuOpen: boolean;
  slashItems: SlashItem[];
  slashIndex: number;
  skills: SkillSummary[];
  skillsIndex: number;
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
  const field = setupFieldAt(state.setupIndex, state.setupFlow);
  const draft = isEditableSetupField(field)
    ? setSetupField(state.setupDraft, field, state.inputValue)
    : state.setupDraft;
  const index = nextSetupIndex(state.setupIndex, direction, true, state.setupFlow);
  const nextField = setupFieldAt(index, state.setupFlow);
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

export function handleCtrlC(input: string, key: Key, options: ShellInputOptions): boolean {
  if (!key.ctrl || input !== "c") return false;

  if (options.compressing || options.inputLocked) return true;
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

function navigationFromKey(key: Key): ListNavigation | null {
  if (key.upArrow) return "up";
  if (key.downArrow) return "down";
  if (key.pageUp) return "pageUp";
  if (key.pageDown) return "pageDown";
  if (key.home) return "home";
  if (key.end) return "end";
  return null;
}

export function handleSlashNavigation(key: Key, options: ShellInputOptions): boolean {
  if (!options.slashMenuOpen || options.slashItems.length === 0) return false;

  const state = options.getState();
  if (key.tab) {
    const selected = options.slashItems[options.slashIndex];
    if (selected) state.set({ inputValue: selected.command });
    return true;
  }
  const navigation = navigationFromKey(key);
  if (navigation) {
    state.set({
      slashIndex: moveListIndex(options.slashIndex, options.slashItems.length, navigation, SLASH_MENU_VISIBLE_ITEMS),
    });
    return true;
  }
  return false;
}

export function handleSkillsNavigation(key: Key, options: ShellInputOptions): boolean {
  if (options.slashMenuOpen || options.panel !== "skills" || options.skills.length === 0) return false;

  const navigation = navigationFromKey(key);
  if (!navigation) return false;

  options.getState().set({
    skillsIndex: moveListIndex(options.skillsIndex, options.skills.length, navigation, SKILLS_PANEL_VISIBLE_ITEMS),
  });
  return true;
}

export function handleSkillsSelection(key: Key, options: ShellInputOptions): boolean {
  if (!key.return || options.slashMenuOpen || options.panel !== "skills" || options.skills.length === 0) return false;

  const state = options.getState();
  if (state.inputValue.trim()) return false;

  const selected = options.skills[options.skillsIndex];
  if (!selected) return false;

  state.set({
    panel: "chat",
    inputValue: "",
    pendingSkill: selected,
    statusLine: "",
  });
  return true;
}

function handleTokenNavigation(key: Key, options: ShellInputOptions): boolean {
  if (options.panel !== "tokens" || options.slashMenuOpen) return false;
  if (!key.leftArrow && !key.rightArrow) return false;

  const state = options.getState();
  const current = TOKEN_TABS.indexOf(state.tokenTab);
  const direction = key.leftArrow ? -1 : 1;
  const next = (current + direction + TOKEN_TABS.length) % TOKEN_TABS.length;
  state.set({ tokenTab: TOKEN_TABS[next] });
  return true;
}

export function handleApprovalInput(key: Key, options: ShellInputOptions): boolean {
  const state = options.getState();
  if (!state.pendingApproval) return false;

  if (key.tab) return true;

  if (key.upArrow || key.leftArrow || key.downArrow || key.rightArrow) {
    if (state.approvalResolving) return true;
    const direction = key.upArrow || key.leftArrow ? -1 : 1;
    state.set({ approvalIndex: (state.approvalIndex + direction + 2) % 2 });
    return true;
  }

  if (key.escape) {
    if (!state.approvalResolving) options.bridge.cancelRequest();
    return true;
  }
  if (!key.return) return false;
  if (!state.approvalResolving) void options.bridge.resolveApproval(state.approvalIndex === 0);
  return true;
}

export function handleModelPickerInput(key: Key, options: ShellInputOptions): boolean {
  const state = options.getState();
  const picker = state.modelPicker;
  if (!picker) return false;

  if (key.tab) return true;
  if (key.escape) {
    state.set({ modelPicker: null, statusLine: "Model change cancelled." });
    return true;
  }

  const navigation = navigationFromKey(key);
  if (navigation) {
    state.set({ modelPicker: moveModelPicker(picker, navigation) });
    return true;
  }
  if (!key.return) return false;

  const next = advanceModelPicker(picker);
  if (next.selection) {
    void options.bridge.applyDiscoveredModel(next.selection.model, next.selection.target);
    return true;
  }
  state.set({
    modelPicker: next.picker,
    statusLine: next.picker ? "Choose where to configure this model." : "Model change cancelled.",
  });
  return true;
}

export function handleEscape(key: Key, options: ShellInputOptions): boolean {
  if (!key.escape) return false;

  const state = options.getState();
  if (options.slashMenuOpen) {
    state.set({ inputValue: "", slashIndex: 0 });
    return true;
  }
  if (options.panel !== "chat") {
    state.set({ panel: "chat", inputValue: "", statusLine: "Back." });
    return true;
  }
  if (options.pendingSkill || state.inputValue) {
    state.set({ pendingSkill: null, inputValue: "", statusLine: "Cleared." });
    return true;
  }
  if (options.bridge.removeLatestQueuedMessage()) return true;
  if (options.busy && options.bridge.cancelRequest()) return true;
  return false;
}

export function handleQueuedEdit(key: Key, options: ShellInputOptions): boolean {
  if (!key.shift || !key.leftArrow) return false;

  const queued = options.bridge.removeLatestQueuedMessage();
  if (!queued) return false;

  const state = options.getState();
  const skill = queued.skillName ? state.skills.find((item) => item.name === queued.skillName) : undefined;
  state.set({ inputValue: queued.text, ...(skill ? { pendingSkill: skill } : {}) });
  return true;
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

  const panels: Panel[] = ["welcome", "sessions", "skills", "mcp", "tokens", "chat"];
  const index = panels.indexOf(options.panel);
  options.getState().set({ panel: panels[(index + 1) % panels.length] });
}

function routeInput(input: string, key: Key, options: ShellInputOptions): void {
  if (handleCtrlC(input, key, options)) return;
  if (options.compressing || options.inputLocked) return;
  if (options.mode === "setup") {
    handleSetupInput(key, options);
    return;
  }
  if (handleModelPickerInput(key, options)) return;
  if (handleApprovalInput(key, options)) return;
  if (handleViewToggle(input, key, options)) return;
  if (handleQueuedEdit(key, options)) return;
  if (handleSlashNavigation(key, options)) return;
  if (handleSkillsSelection(key, options)) return;
  if (handleSkillsNavigation(key, options)) return;
  if (handleTokenNavigation(key, options)) return;
  if (handleEscape(key, options)) return;
  if (handleHistoryNavigation(key, options)) return;
  cyclePanel(key, options);
}

export function useShellInput(options: ShellInputOptions): void {
  useInput((input, key) => {
    routeInput(input, key, options);
  });
}
