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

test("config reopens the five-field form with saved values intact", async () => {
  const store = createAppStore();
  store.getState().set({
    config: {
      configured: true,
      has_api_key: true,
      provider: "openai",
      base_url: "https://gateway.example/v1",
      model: "primary-model",
      max_output_tokens: null,
      routes: { gate: { model: "review-model", has_api_key: false } },
      timeout_profiles: {},
    },
  });

  await runShellCommand("/config", {
    bridge: {} as NodeBridge,
    exit: () => {},
    getState: store.getState,
  });

  const state = store.getState();
  assert.equal(state.mode, "setup");
  assert.equal(state.setupFlow, "initial");
  assert.equal(state.setupDraft.provider, "openai");
  assert.equal(state.setupDraft.base_url, "https://gateway.example/v1");
  assert.equal(state.setupDraft.model, "primary-model");
  assert.equal(state.setupDraft.review_model, "review-model");
  assert.equal(state.setupDraft.api_key, "");
});
