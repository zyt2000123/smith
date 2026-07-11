import assert from "node:assert/strict";
import test from "node:test";

import { applyToolActivity, createToolActivity } from "./activity.js";

test("preflight is tracked separately from successful tools", () => {
  const started = applyToolActivity(createToolActivity(), {
    type: "tool_call",
    id: "tool-1",
    name: "web_search",
    hint: "query",
  });
  const activity = applyToolActivity(started, {
    type: "tool_result",
    id: "tool-1",
    error: false,
    blocked: false,
    preflight: true,
    summary: "present facts first",
  });

  assert.deepEqual(activity.successes, {});
  assert.deepEqual(activity.preflight, { web_search: 1 });
  assert.deepEqual(activity.running, {});
});

test("a duplicate result does not inflate HUD counters", () => {
  const started = applyToolActivity(createToolActivity(), {
    type: "tool_call",
    id: "tool-1",
    name: "read_file",
    hint: "file",
  });
  const result = {
    type: "tool_result" as const,
    id: "tool-1",
    error: false,
    blocked: false,
    preflight: false,
    summary: "ok",
  };

  const once = applyToolActivity(started, result);
  const twice = applyToolActivity(once, result);

  assert.deepEqual(twice.successes, { read_file: 1 });
});
