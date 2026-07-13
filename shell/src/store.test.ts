import assert from "node:assert/strict";
import test from "node:test";

import { createAppStore, TRANSCRIPT_LIMIT } from "./store.js";

test("transcript history is bounded for long-running shell sessions", () => {
  const store = createAppStore();

  for (let index = 0; index < TRANSCRIPT_LIMIT + 20; index += 1) {
    store.getState().pushSystemLine(`line-${index}`);
  }

  const transcript = store.getState().transcript;
  assert.equal(transcript.length, TRANSCRIPT_LIMIT);
  assert.equal(transcript[0]?.kind, "system");
  assert.equal(transcript[0]?.kind === "system" ? transcript[0].text : "", "line-20");
});

test("token usage tracks the current turn separately from the session total", () => {
  const store = createAppStore();

  store.getState().pushTurn("first");
  store.getState().applyEvent({ type: "token_usage", input_tokens: 120, output_tokens: 30, total_tokens: 150 });
  store.getState().applyEvent({ type: "token_usage", input_tokens: 10, output_tokens: 40, total_tokens: 50 });
  assert.equal(store.getState().turnTokenUsage.total_tokens, 200);
  assert.equal(store.getState().tokenUsage.total_tokens, 200);

  store.getState().pushTurn("second");
  assert.equal(store.getState().turnTokenUsage.total_tokens, 0);
  assert.equal(store.getState().tokenUsage.total_tokens, 200);

  store.getState().applyEvent({ type: "token_usage", input_tokens: 60, output_tokens: 20, total_tokens: 80 });
  assert.equal(store.getState().turnTokenUsage.total_tokens, 80);
  assert.equal(store.getState().tokenUsage.total_tokens, 280);
});
