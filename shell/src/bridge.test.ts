import assert from "node:assert/strict";
import test from "node:test";

import { NodeBridge } from "./bridge.js";
import { MAX_QUEUED_MESSAGES } from "./queue.js";
import { createAppStore } from "./store.js";

test("request errors keep details in the transcript without duplicating them in the status line", () => {
  const store = createAppStore();
  const bridge = new NodeBridge(store);
  const reportRequestError = (
    bridge as unknown as {
      reportRequestError: (error: unknown) => void;
    }
  ).reportRequestError.bind(bridge);

  reportRequestError(new Error("Request timed out after 120000ms."));

  const state = store.getState();
  const lastEntry = state.transcript.at(-1);
  assert.equal(lastEntry?.kind, "system");
  assert.equal(lastEntry?.kind === "system" && lastEntry.text, "[error] Request timed out after 120000ms.");
  assert.equal(state.statusLine, "Request failed. See the transcript for details.");
});

test("frontend message queue is capped and supports removal and clearing", () => {
  const store = createAppStore();
  const bridge = new NodeBridge(store);

  assert.equal(bridge.enqueueMessage("first"), true);
  assert.equal(bridge.enqueueMessage("second"), true);
  assert.equal(bridge.enqueueMessage("third"), true);
  assert.equal(bridge.enqueueMessage("fourth"), false);
  assert.equal(store.getState().queuedMessages.length, MAX_QUEUED_MESSAGES);

  const removed = bridge.removeQueuedMessage(1);
  assert.equal(removed?.text, "second");
  assert.deepEqual(
    store.getState().queuedMessages.map((item) => item.text),
    ["first", "third"],
  );

  assert.equal(bridge.removeLatestQueuedMessage()?.text, "third");
  assert.deepEqual(
    store.getState().queuedMessages.map((item) => item.text),
    ["first"],
  );
});

test("finishing a request starts the next queued message in FIFO order", async () => {
  const store = createAppStore();
  const bridge = new NodeBridge(store);
  bridge.enqueueMessage("second");
  bridge.enqueueMessage("third");

  const activeController = new AbortController();
  const started: string[] = [];
  const internal = bridge as unknown as {
    activeRequest: AbortController | null;
    finishRequest: (controller: AbortController) => void;
    sendMessage: (text: string, skillName?: string) => Promise<boolean>;
  };
  internal.activeRequest = activeController;
  internal.sendMessage = async (text) => {
    started.push(text);
    return true;
  };

  internal.finishRequest(activeController);
  await Promise.resolve();

  assert.deepEqual(started, ["second"]);
  assert.deepEqual(
    store.getState().queuedMessages.map((item) => item.text),
    ["third"],
  );
});
