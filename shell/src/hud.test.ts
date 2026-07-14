import assert from "node:assert/strict";
import test from "node:test";

import { buildRunProgressParts, formatElapsed } from "./hud.js";
import { MUTED } from "./theme.js";

test("formats active run duration for the status HUD", () => {
  assert.equal(formatElapsed(1_000, 1_000), "0s");
  assert.equal(formatElapsed(1_000, 60_999), "59s");
  assert.equal(formatElapsed(1_000, 181_000), "3m 0s");
});

test("keeps the run progress content aligned while removing its leading dot", () => {
  const parts = buildRunProgressParts(1_000, { input_tokens: 0, output_tokens: 0, total_tokens: 7_500 }, 11_000);

  assert.deepEqual(parts, [
    { text: "  ", color: MUTED },
    { text: "working ", color: MUTED },
    { text: "(10s", color: MUTED },
    { text: " · ↓ ", color: MUTED },
    { text: "7.5k tokens", color: MUTED },
    { text: ")", color: MUTED },
  ]);
  assert.equal(parts.map((part) => part.text).join(""), "  working (10s · ↓ 7.5k tokens)");
});

test("keeps the existing compact progress line when no token usage is available", () => {
  const parts = buildRunProgressParts(null, { input_tokens: 0, output_tokens: 0, total_tokens: 0 }, 11_000);

  assert.deepEqual(parts, [
    { text: "  ", color: MUTED },
    { text: "working ", color: MUTED },
    { text: "(0s", color: MUTED },
    { text: ")", color: MUTED },
  ]);
});
