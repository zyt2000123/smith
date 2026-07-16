import assert from "node:assert/strict";
import test from "node:test";

import type { NodeBridge } from "./bridge.js";
import { buildSlashItems, filterSlash, runShellCommand } from "./commands.js";
import { createAppStore } from "./store.js";

function skill(name: string) {
  return {
    name,
    description: `Run ${name}.`,
    source: "builtin",
    version: "0.1.0",
    argument_hint: "",
  };
}

test("slash filtering keeps only general commands", () => {
  const skills = Array.from({ length: 8 }, (_, index) => skill(`skill-${index + 1}`));
  const items = filterSlash(buildSlashItems(skills), "/");

  assert.equal(items.length, 15);
  assert.equal(
    items.some((item) => item.command === "/init"),
    true,
  );
  assert.equal(
    items.some((item) => item.command === "/resume"),
    true,
  );
  assert.equal(
    items.some((item) => item.command === "/skills"),
    true,
  );
  assert.equal(
    items.some((item) => item.command === "/skill"),
    false,
  );
  assert.equal(
    items.some((item) => item.command === "/approve" || item.command === "/deny"),
    false,
  );
  assert.equal(
    items.some((item) => item.kind === "skill"),
    false,
  );
});

test("run resume delegates an explicit or retained run id to the bridge", async () => {
  const store = createAppStore();
  const calls: Array<string | undefined> = [];
  const bridge = {
    resumeRun: async (runId?: string) => {
      calls.push(runId);
    },
  } as unknown as NodeBridge;

  await runShellCommand("/run resume run-123", { bridge, exit: () => {}, getState: store.getState });
  await runShellCommand("/run resume", { bridge, exit: () => {}, getState: store.getState });

  assert.deepEqual(calls, ["run-123", undefined]);
});

test("new keeps the old session while clear delegates deletion", async () => {
  const oldSession = {
    id: "session-1",
    agent_id: "agent-1",
    title: "old",
    created_at: "now",
    message_count: 1,
  };

  const newStore = createAppStore();
  newStore.getState().set({ currentSession: oldSession, sessions: [oldSession], inputValue: "draft" });
  let newCalls = 0;
  const newBridge = {
    startNewSession: async () => {
      newCalls += 1;
      newStore.getState().startFreshSession();
      return true;
    },
  } as unknown as NodeBridge;
  await runShellCommand("/new", { bridge: newBridge, exit: () => {}, getState: newStore.getState });
  assert.equal(newCalls, 1);
  assert.equal(newStore.getState().currentSession, null);
  assert.equal(newStore.getState().sessions[0]?.id, "session-1");
  assert.deepEqual(newStore.getState().transcript, []);

  const clearStore = createAppStore();
  clearStore.getState().set({ currentSession: oldSession, sessions: [oldSession] });
  let clearCalls = 0;
  const clearBridge = {
    clearCurrentSession: async () => {
      clearCalls += 1;
      clearStore.getState().set({ sessions: [] });
      clearStore.getState().startFreshSession();
      return true;
    },
  } as unknown as NodeBridge;
  await runShellCommand("/clear", { bridge: clearBridge, exit: () => {}, getState: clearStore.getState });
  assert.equal(clearCalls, 1);
  assert.equal(clearStore.getState().currentSession, null);
  assert.deepEqual(clearStore.getState().sessions, []);
});

test("clear keeps the current session when deletion fails", async () => {
  const store = createAppStore();
  store.getState().set({
    currentSession: { id: "session-1", agent_id: "agent-1", title: "old", created_at: "now", message_count: 1 },
  });
  const bridge = {
    clearCurrentSession: async () => false,
  } as unknown as NodeBridge;

  await runShellCommand("/clear", { bridge, exit: () => {}, getState: store.getState });

  assert.equal(store.getState().currentSession?.id, "session-1");
});

test("init command creates project instructions once and reports the preserved file", async () => {
  const store = createAppStore();
  const calls: string[] = [];
  const context = {
    bridge: {
      initializeProject: async (workingDir: string) => {
        calls.push(workingDir);
        return { path: `${workingDir}/.smith/SMITH.md`, created: calls.length === 1 };
      },
    } as unknown as NodeBridge,
    exit: () => {},
    getState: store.getState,
    workingDir: "/workspace/project",
  };

  await runShellCommand("/init", context);
  assert.match(store.getState().statusLine, /Created .+\.smith\/SMITH\.md/);

  await runShellCommand("/init", context);
  assert.match(store.getState().statusLine, /Already exists:.+not changed/);
  assert.deepEqual(calls, ["/workspace/project", "/workspace/project"]);
});

test("init command surfaces the failure reason in the status line", async () => {
  const store = createAppStore();
  const context = {
    bridge: {
      initializeProject: async () => {
        throw new Error("permission denied: .smith");
      },
    } as unknown as NodeBridge,
    exit: () => {},
    getState: store.getState,
    workingDir: "/workspace/project",
  };

  await runShellCommand("/init", context);
  assert.match(store.getState().statusLine, /Project initialization failed: permission denied: \.smith/);
});

test("model commands add relay-sharing profiles and use bridge contracts", async () => {
  const store = createAppStore();
  store.getState().set({
    config: {
      configured: true,
      has_api_key: true,
      provider: "openai",
      base_url: "https://relay.example/v1",
      model: "default-model",
      max_output_tokens: null,
      routes: {},
      timeout_profiles: {},
      models: {
        "relay-fast": { provider: "openai", model: "fast-model", has_api_key: true },
      },
    },
  });
  const calls: string[] = [];
  const bridge = {
    addModelProfile: async (model: string, name: string) => calls.push(`add:${name}:${model}`),
    selectModel: async (name: string | null) => calls.push(`model:${name}`),
    compressCurrentSession: async () => calls.push("compress"),
    refreshMcpServers: async () => calls.push("mcp"),
    openTokenStats: async () => calls.push("token"),
  } as unknown as NodeBridge;

  await runShellCommand("/model add GLM-5.2 fast", { bridge, exit: () => {}, getState: store.getState });
  await runShellCommand("/model relay-fast", { bridge, exit: () => {}, getState: store.getState });
  await runShellCommand("/compress", { bridge, exit: () => {}, getState: store.getState });
  await runShellCommand("/mcp", { bridge, exit: () => {}, getState: store.getState });
  await runShellCommand("/token", { bridge, exit: () => {}, getState: store.getState });

  assert.deepEqual(calls, ["add:fast:GLM-5.2", "model:relay-fast", "compress", "mcp", "token"]);
});

test("model opens the relay model picker", async () => {
  const store = createAppStore();
  store.getState().set({
    config: {
      configured: true,
      has_api_key: true,
      provider: "openai",
      base_url: "https://relay.example/v1",
      model: "default-model",
      max_output_tokens: null,
      routes: {},
      timeout_profiles: {},
      models: {},
    },
  });

  let opened = 0;
  const bridge = {
    openModelPicker: async () => {
      opened += 1;
    },
  } as unknown as NodeBridge;

  await runShellCommand("/model", { bridge, exit: () => {}, getState: store.getState });

  assert.equal(opened, 1);
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
      models: {},
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
