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
