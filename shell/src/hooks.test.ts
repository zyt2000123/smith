import assert from "node:assert/strict";
import test from "node:test";

import { LIFECYCLE_HOOKS } from "./hooks.js";

test("lifecycle hook catalog mirrors the hooks dispatched by the runtime", () => {
  assert.deepEqual(
    LIFECYCLE_HOOKS.map((hook) => hook.event),
    [
      "memory_after_turn_completed",
      "memory_after_turn_incomplete",
      "memory_after_turn_failed",
      "memory_idle_tick",
      "memory_daily_tick",
    ],
  );
  assert.ok(LIFECYCLE_HOOKS.every((hook) => hook.handler === "MemoryLifecycleHooks"));
});
