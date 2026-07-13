import assert from "node:assert/strict";
import test from "node:test";

import type { NodeBridge } from "./bridge.js";
import { runShellCommand } from "./commands.js";
import { createAppStore } from "./store.js";

test("retry command resets the shell to boot and reruns bridge startup", async () => {
  const store = createAppStore();
  let bootCalls = 0;
  const bridge = {
    boot: async () => {
      bootCalls += 1;
    },
  } as unknown as NodeBridge;

  await runShellCommand("/retry", { bridge, exit: () => {}, getState: store.getState });

  assert.equal(bootCalls, 1);
  assert.equal(store.getState().mode, "boot");
});
