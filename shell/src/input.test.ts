import assert from "node:assert/strict";
import test from "node:test";
import type { Key } from "ink";

import { NodeBridge } from "./bridge.js";
import { handleEscape, handleQueuedEdit, type ShellInputOptions } from "./input.js";
import { createAppStore } from "./store.js";

function escapeKey(): Key {
  return { escape: true } as Key;
}

function shiftLeftKey(): Key {
  return { leftArrow: true, shift: true } as Key;
}

function inputOptions(bridge: NodeBridge, store: ReturnType<typeof createAppStore>): ShellInputOptions {
  return {
    mode: "chat",
    setupFlow: "initial",
    busy: true,
    viewMode: "compact",
    slashMenuOpen: false,
    slashItems: [],
    slashIndex: 0,
    panel: "chat",
    pendingSkill: null,
    configConfigured: true,
    exit: () => {},
    bridge,
    getState: store.getState,
    suppressRef: { current: null },
  };
}

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
