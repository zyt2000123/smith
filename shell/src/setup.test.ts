import assert from "node:assert/strict";
import test from "node:test";

import type { LlmConfig } from "./api.js";
import { buildLlmConfigInput, createSetupDraft } from "./setup.js";
import type { SetupDraft } from "./store.js";

function draft(overrides: Partial<SetupDraft> = {}): SetupDraft {
  return {
    provider: "openai",
    base_url: "https://api.openai.com/v1",
    model: "gpt-4.1-mini",
    max_output_tokens: "",
    api_key: "",
    routes: "",
    interactive_api_key: "",
    gate_api_key: "",
    background_api_key: "",
    timeout_profiles: "",
    ...overrides,
  };
}

test("setup draft exposes route and timeout config without exposing stored secrets", () => {
  const config: LlmConfig = {
    configured: true,
    has_api_key: true,
    provider: "openai",
    base_url: "https://api.openai.com/v1",
    model: "gpt-4.1-mini",
    max_output_tokens: 2048,
    routes: {
      gate: { model: "cheap-gate-model", max_output_tokens: 512, timeout_profile: "gate", has_api_key: true },
    },
    timeout_profiles: {
      gate: { read: 45, stream_read: 50 },
    },
  };

  const result = createSetupDraft(config);

  assert.deepEqual(JSON.parse(result.routes), {
    gate: { model: "cheap-gate-model", max_output_tokens: 512, timeout_profile: "gate" },
  });
  assert.equal(result.max_output_tokens, "2048");
  assert.equal(result.routes.includes("api_key"), false);
  assert.deepEqual(JSON.parse(result.timeout_profiles), { gate: { read: 45, stream_read: 50 } });
});

test("setup builds complete route and timeout patches while keeping route keys masked", () => {
  const result = buildLlmConfigInput(
    draft({
      max_output_tokens: "2048",
      routes: '{"gate":{"model":"cheap-gate-model","max_output_tokens":512,"timeout_profile":"gate"},"background":{"base_url":null,"max_output_tokens":null}}',
      gate_api_key: "gate-secret",
      background_api_key: "-",
      timeout_profiles: '{"gate":{"read":45,"stream_read":50},"background":{"read":null}}',
    }),
  );

  assert.deepEqual(result, {
    provider: "openai",
    base_url: "https://api.openai.com/v1",
    model: "gpt-4.1-mini",
    max_output_tokens: 2048,
    routes: {
      gate: { model: "cheap-gate-model", max_output_tokens: 512, timeout_profile: "gate", api_key: "gate-secret" },
      background: { base_url: null, max_output_tokens: null, api_key: null },
    },
    timeout_profiles: {
      gate: { read: 45, stream_read: 50 },
      background: { read: null },
    },
  });
});

test("setup permits clearing advanced configuration with empty JSON objects", () => {
  const result = buildLlmConfigInput(draft({ routes: "{}", timeout_profiles: "{}" }));

  assert.deepEqual(result.routes, {});
  assert.deepEqual(result.timeout_profiles, {});
});

test("setup rejects route API keys pasted into visible JSON", () => {
  assert.throws(
    () => buildLlmConfigInput(draft({ routes: '{"gate":{"api_key":"should-not-be-visible"}}' })),
    /gate route API key field/,
  );
});

test("setup validates top-level and route output-token limits", () => {
  assert.equal("max_output_tokens" in buildLlmConfigInput(draft()), false);
  assert.deepEqual(buildLlmConfigInput(draft({ max_output_tokens: "-" })).max_output_tokens, null);
  assert.throws(
    () => buildLlmConfigInput(draft({ max_output_tokens: "1.5" })),
    /Max output tokens must be a positive integer/,
  );
  assert.throws(
    () => buildLlmConfigInput(draft({ routes: '{"gate":{"max_output_tokens":true}}' })),
    /routes\.gate\.max_output_tokens must be a positive integer or null/,
  );
});
