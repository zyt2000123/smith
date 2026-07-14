import assert from "node:assert/strict";
import test from "node:test";
import type { Key } from "ink";

import { NodeBridge } from "./bridge.js";
import {
  handleApprovalInput,
  handleEscape,
  handleQueuedEdit,
  handleSkillsNavigation,
  handleSkillsSelection,
  handleSlashNavigation,
  type ShellInputOptions,
} from "./input.js";
import { createAppStore } from "./store.js";

function escapeKey(): Key {
  return { escape: true } as Key;
}

function shiftLeftKey(): Key {
  return { leftArrow: true, shift: true } as Key;
}

function returnKey(): Key {
  return { return: true } as Key;
}

function inputOptions(bridge: NodeBridge, store: ReturnType<typeof createAppStore>): ShellInputOptions {
  return {
    mode: "chat",
    setupFlow: "initial",
    busy: true,
    compressing: false,
    viewMode: "compact",
    slashMenuOpen: false,
    slashItems: [],
    slashIndex: 0,
    skills: [],
    skillsIndex: 0,
    panel: "chat",
    pendingSkill: null,
    configConfigured: true,
    exit: () => {},
    bridge,
    getState: store.getState,
    suppressRef: { current: null },
  };
}

test("slash and skills navigation scrolls through the full lists", () => {
  const store = createAppStore();
  const options = inputOptions({} as NodeBridge, store);
  options.slashMenuOpen = true;
  options.slashItems = Array.from({ length: 10 }, (_, index) => ({
    id: `item-${index}`,
    kind: "command" as const,
    title: `/item-${index}`,
    command: `/item-${index}`,
    description: "",
    category: "Commands",
  }));
  options.slashIndex = 8;

  assert.equal(handleSlashNavigation({ downArrow: true } as Key, options), true);
  assert.equal(store.getState().slashIndex, 9);

  options.slashMenuOpen = false;
  options.panel = "skills";
  options.skills = Array.from({ length: 6 }, (_, index) => ({
    name: `skill-${index}`,
    description: "",
    source: "builtin",
    version: "0.1.0",
    argument_hint: "",
  }));
  options.skillsIndex = 4;

  assert.equal(handleSkillsNavigation({ pageUp: true } as Key, options), true);
  assert.equal(store.getState().skillsIndex, 0);
});

test("enter arms the selected skill and returns to chat", () => {
  const store = createAppStore();
  const options = inputOptions(new NodeBridge(store), store);
  options.busy = false;
  options.panel = "skills";
  options.skills = [
    {
      name: "research",
      description: "Research a topic.",
      source: "builtin",
      version: "0.1.0",
      argument_hint: "",
    },
  ];
  options.skillsIndex = 0;
  store.getState().set({ panel: "skills", inputValue: "" });

  assert.equal(handleSkillsSelection(returnKey(), options), true);
  assert.equal(store.getState().panel, "chat");
  assert.equal(store.getState().pendingSkill?.name, "research");
  assert.equal(store.getState().statusLine, "Skill research armed.");
});

test("approval options move with arrows and Enter resolves the selected option", async () => {
  const store = createAppStore();
  const decisions: boolean[] = [];
  const bridge = {
    resolveApproval: async (approved: boolean) => {
      decisions.push(approved);
    },
  } as unknown as NodeBridge;
  const options = inputOptions(bridge, store);
  store.getState().set({
    pendingApproval: {
      runId: "run-1",
      approvalId: "approval-1",
      tool: "shell",
      level: "execute",
      reason: "Approval required",
      arguments: { command: "npm test" },
    },
  });

  assert.equal(handleApprovalInput({ downArrow: true } as Key, options), true);
  assert.equal(store.getState().approvalIndex, 1);
  assert.equal(handleApprovalInput(returnKey(), options), true);
  await Promise.resolve();
  assert.deepEqual(decisions, [false]);

  assert.equal(handleApprovalInput({ upArrow: true } as Key, options), true);
  assert.equal(store.getState().approvalIndex, 0);
  assert.equal(handleApprovalInput(returnKey(), options), true);
  await Promise.resolve();
  assert.deepEqual(decisions, [false, true]);
});

test("Escape cancels the pending approval instead of consuming queued input", () => {
  const store = createAppStore();
  let cancelled = false;
  const bridge = {
    cancelRequest: () => {
      cancelled = true;
      return true;
    },
  } as unknown as NodeBridge;
  const options = inputOptions(bridge, store);
  store.getState().set({
    pendingApproval: {
      runId: "run-1",
      approvalId: "approval-1",
      tool: "shell",
      level: "execute",
      reason: "Approval required",
      arguments: { command: "npm test" },
    },
  });

  assert.equal(handleApprovalInput(escapeKey(), options), true);
  assert.equal(cancelled, true);
});

test("escape removes queued messages from newest to oldest before cancelling", () => {
  const store = createAppStore();
  const bridge = new NodeBridge(store);
  bridge.enqueueMessage("first");
  bridge.enqueueMessage("second");
  bridge.enqueueMessage("third");
  const options = inputOptions(bridge, store);

  assert.equal(handleEscape(escapeKey(), options), true);
  assert.equal(handleEscape(escapeKey(), options), true);
  assert.equal(handleEscape(escapeKey(), options), true);
  assert.deepEqual(store.getState().queuedMessages, []);
});

test("escape cancels the running request once the queue is empty", () => {
  const store = createAppStore();
  let cancelled = false;
  const bridge = {
    removeLatestQueuedMessage: () => null,
    cancelRequest: () => {
      cancelled = true;
      return true;
    },
  } as unknown as NodeBridge;
  const options = inputOptions(bridge, store);

  assert.equal(handleEscape(escapeKey(), options), true);
  assert.equal(cancelled, true);
});

test("escape closes the slash palette without cancelling the task", () => {
  const store = createAppStore();
  let cancelled = false;
  const bridge = {
    removeLatestQueuedMessage: () => null,
    cancelRequest: () => {
      cancelled = true;
      return true;
    },
  } as unknown as NodeBridge;
  const options = inputOptions(bridge, store);
  options.busy = true;
  options.slashMenuOpen = true;
  store.getState().set({ inputValue: "/sk", slashIndex: 3 });

  assert.equal(handleEscape(escapeKey(), options), true);
  assert.equal(store.getState().inputValue, "");
  assert.equal(store.getState().slashIndex, 0);
  assert.equal(cancelled, false);

  options.slashMenuOpen = false;
  assert.equal(handleEscape(escapeKey(), options), true);
  assert.equal(cancelled, true);
});

test("escape returns from a non-chat panel to the chat panel", () => {
  const store = createAppStore();
  const options = inputOptions(new NodeBridge(store), store);
  options.busy = false;
  options.panel = "skills";
  const pendingSkill = {
    name: "research",
    description: "Research a topic.",
    source: "builtin",
    version: "0.1.0",
    argument_hint: "",
  };
  options.pendingSkill = pendingSkill;
  store.getState().set({ panel: "skills", inputValue: "", pendingSkill });

  assert.equal(handleEscape(escapeKey(), options), true);
  assert.equal(store.getState().panel, "chat");
  assert.equal(store.getState().statusLine, "Back.");
  assert.equal(store.getState().pendingSkill?.name, "research");
});

test("escape clears a chat draft and armed skill", () => {
  const store = createAppStore();
  const options = inputOptions(new NodeBridge(store), store);
  options.busy = false;
  const pendingSkill = {
    name: "research",
    description: "Research a topic.",
    source: "builtin",
    version: "0.1.0",
    argument_hint: "",
  };
  options.pendingSkill = pendingSkill;
  store.getState().set({ inputValue: "draft", pendingSkill });

  assert.equal(handleEscape(escapeKey(), options), true);
  assert.equal(store.getState().inputValue, "");
  assert.equal(store.getState().pendingSkill, null);
  assert.equal(store.getState().statusLine, "Cleared.");
});

test("escape stays inert on the base chat panel", () => {
  const store = createAppStore();
  const options = inputOptions(new NodeBridge(store), store);
  options.busy = false;
  store.getState().set({ panel: "chat" });

  assert.equal(handleEscape(escapeKey(), options), false);
  assert.equal(store.getState().panel, "chat");
});

test("shift-left edits the newest queued message back into the input", () => {
  const store = createAppStore();
  const bridge = new NodeBridge(store);
  bridge.enqueueMessage("first");
  bridge.enqueueMessage("last message");
  const options = inputOptions(bridge, store);

  assert.equal(handleQueuedEdit(shiftLeftKey(), options), true);
  assert.equal(store.getState().inputValue, "last message");
  assert.deepEqual(
    store.getState().queuedMessages.map((item) => item.text),
    ["first"],
  );
});
