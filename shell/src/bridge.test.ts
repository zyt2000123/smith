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

test("starting a new session keeps the existing session in history", () => {
  const store = createAppStore();
  const session = {
    id: "session-1",
    agent_id: "agent-1",
    title: "old",
    created_at: "now",
    message_count: 1,
  };
  store.getState().set({ currentSession: session, sessions: [session], inputValue: "draft" });

  const bridge = new NodeBridge(store);

  assert.equal(bridge.startNewSession(), true);
  assert.equal(store.getState().currentSession, null);
  assert.equal(store.getState().sessions[0]?.id, "session-1");
});

test("cancelling a request allows a new session before the stream cleanup finishes", () => {
  const store = createAppStore();
  const bridge = new NodeBridge(store);
  const controller = new AbortController();
  const internal = bridge as unknown as { activeRequest: AbortController | null };
  internal.activeRequest = controller;
  store.getState().set({ busy: true, currentSession: null });

  assert.equal(bridge.cancelRequest(), true);
  assert.equal(internal.activeRequest, controller);
  assert.equal(bridge.startNewSession(), true);
});

test("leaving the token panel while it loads does not reopen it", async () => {
  const originalFetch = globalThis.fetch;
  let release!: (response: Response) => void;
  const response = new Promise<Response>((resolve) => {
    release = resolve;
  });
  globalThis.fetch = async () => response;

  const store = createAppStore();
  store.getState().set({ baseUrl: "http://127.0.0.1:8140" });
  const bridge = new NodeBridge(store);
  const loading = bridge.openTokenStats();
  assert.equal(store.getState().panel, "tokens");
  store.getState().set({ panel: "chat" });
  release(
    new Response(
      JSON.stringify({
        year: 2026,
        session_count: 0,
        active_days: 0,
        current_streak: 0,
        longest_streak: 0,
        favorite_model: null,
        peak_hour: null,
        input_tokens: 0,
        output_tokens: 0,
        total_tokens: 0,
        daily: [],
        models: [],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );
  await loading;

  assert.equal(store.getState().panel, "chat");
  globalThis.fetch = originalFetch;
});

test("clearing a session locks out new requests until deletion finishes", async () => {
  const originalFetch = globalThis.fetch;
  let release!: (response: Response) => void;
  const response = new Promise<Response>((resolve) => {
    release = resolve;
  });
  globalThis.fetch = async () => response;

  const store = createAppStore();
  const session = {
    id: "session-1",
    agent_id: "agent-1",
    title: "old",
    created_at: "now",
    message_count: 1,
  };
  store.getState().set({
    baseUrl: "http://127.0.0.1:8140",
    agent: { id: "agent-1", name: "Smith", role: "agent" },
    currentSession: session,
  });
  const bridge = new NodeBridge(store);
  const clearing = bridge.clearCurrentSession();

  assert.equal(store.getState().inputLocked, true);
  assert.equal(await bridge.sendMessage("must wait"), false);
  release(new Response(null, { status: 204 }));
  assert.equal(await clearing, true);
  assert.equal(store.getState().inputLocked, false);
  assert.equal(store.getState().currentSession, null);
  globalThis.fetch = originalFetch;
});

test("a failed resume keeps the current session and removes a stale 404 target", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response("gone", { status: 404, statusText: "Not Found" });

  const currentSession = {
    id: "current",
    agent_id: "agent-1",
    title: "current",
    created_at: "now",
    message_count: 1,
  };
  const staleSession = { ...currentSession, id: "stale", title: "stale" };
  const store = createAppStore();
  store.getState().set({
    baseUrl: "http://127.0.0.1:8140",
    currentSession,
    sessions: [currentSession, staleSession],
  });

  await new NodeBridge(store).resumeSession(staleSession);

  assert.equal(store.getState().currentSession?.id, "current");
  assert.deepEqual(
    store.getState().sessions.map((session) => session.id),
    ["current"],
  );
  assert.equal(store.getState().inputLocked, false);
  globalThis.fetch = originalFetch;
});

test("changing a session model locks out session switches until the patch finishes", async () => {
  const originalFetch = globalThis.fetch;
  let release!: (response: Response) => void;
  const response = new Promise<Response>((resolve) => {
    release = resolve;
  });
  globalThis.fetch = async () => response;

  const currentSession = {
    id: "current",
    agent_id: "agent-1",
    title: "current",
    created_at: "now",
    message_count: 1,
  };
  const store = createAppStore();
  store.getState().set({
    baseUrl: "http://127.0.0.1:8140",
    currentSession,
    config: {
      configured: true,
      has_api_key: true,
      provider: "openai",
      base_url: "https://relay.example/v1",
      model: "default-model",
      max_output_tokens: null,
      routes: {},
      timeout_profiles: {},
      models: { fast: { model: "fast-model", has_api_key: true } },
    },
  });
  const bridge = new NodeBridge(store);
  const selecting = bridge.selectModel("fast");

  assert.equal(store.getState().inputLocked, true);
  assert.equal(bridge.startNewSession(), false);
  release(
    new Response(JSON.stringify({ ...currentSession, model_profile: "fast" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  await selecting;

  assert.equal(store.getState().inputLocked, false);
  assert.equal(store.getState().selectedModelProfile, "fast");
  globalThis.fetch = originalFetch;
});
