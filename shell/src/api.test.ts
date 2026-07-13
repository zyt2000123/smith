import assert from "node:assert/strict";
import test from "node:test";

import { createTimeoutSignal, decodeSseEvent, streamMessage } from "./api.js";

test("SSE decoder accepts standard data fields without a trailing space", () => {
  const event = decodeSseEvent('event: done\ndata:{"id":"message-1"}');

  assert.deepEqual(event, { type: "done", id: "message-1", status: "completed" });
});

test("SSE decoder exposes the run id when execution starts", () => {
  assert.deepEqual(decodeSseEvent('event: run_started\ndata: {"run_id":"run-1"}'), {
    type: "run_started",
    runId: "run-1",
  });
});

test("request timeout signals abort and identify timeout rather than user cancellation", async () => {
  const request = createTimeoutSignal(5);
  try {
    await new Promise<void>((resolve, reject) => {
      request.signal.addEventListener("abort", () => {
        try {
          assert.equal(request.didTimeout(), true);
          assert.equal(request.signal.reason?.name, "TimeoutError");
          resolve();
        } catch (error) {
          reject(error);
        }
      });
    });
  } finally {
    request.dispose();
  }
});

test("SSE decoder preserves an incomplete terminal status", () => {
  const event = decodeSseEvent('event: done\ndata: {"id":"message-1","status":"incomplete"}');

  assert.deepEqual(event, { type: "done", id: "message-1", status: "incomplete" });
});

test("SSE decoder retains a tool preflight result", () => {
  const event = decodeSseEvent('event: tool_result\ndata: {"id":"tool-1","preflight":true,"summary":"facts first"}');

  assert.deepEqual(event, {
    type: "tool_result",
    id: "tool-1",
    error: false,
    blocked: false,
    preflight: true,
    summary: "facts first",
  });
});

test("SSE decoder preserves provisional lifecycle events", () => {
  assert.deepEqual(decodeSseEvent('event: provisional_text_delta\ndata: {"provision_id":"draft-1","text":"draft"}'), {
    type: "provisional_text_delta",
    provisionId: "draft-1",
    text: "draft",
  });
  assert.deepEqual(decodeSseEvent('event: provisional_retract\ndata: {"provision_id":"draft-1","reason":"retry"}'), {
    type: "provisional_retract",
    provisionId: "draft-1",
    reason: "retry",
  });
  assert.deepEqual(decodeSseEvent('event: provisional_commit\ndata: {"provision_id":"draft-2"}'), {
    type: "provisional_commit",
    provisionId: "draft-2",
  });
});

test("streamMessage stops after done even when the SSE body stays open", async () => {
  const originalFetch = globalThis.fetch;
  let streamController: ReadableStreamDefaultController<Uint8Array> | undefined;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      streamController = controller;
      controller.enqueue(new TextEncoder().encode('event: done\ndata: {"id":"message-1"}\n\n'));
    },
  });

  globalThis.fetch = async () =>
    new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });

  const consume = (async () => {
    const events = [];
    for await (const event of streamMessage("http://127.0.0.1:8140", "session-1", "hello", { timeoutMs: 1_000 })) {
      events.push(event);
    }
    return events;
  })();

  try {
    const result = await Promise.race([
      consume,
      new Promise<"timeout">((resolve) => setTimeout(() => resolve("timeout"), 100)),
    ]);

    assert.notEqual(result, "timeout", "done should end the stream without waiting for socket close");
    assert.deepEqual(result, [{ type: "done", id: "message-1", status: "completed" }]);
  } finally {
    try {
      streamController?.close();
    } catch {
      // The fixed reader cancels the stream before this cleanup runs.
    }
    await consume.catch(() => undefined);
    globalThis.fetch = originalFetch;
  }
});

test("stream timeout resets on SSE activity instead of limiting total run time", async () => {
  const originalFetch = globalThis.fetch;
  const encoder = new TextEncoder();
  let streamController: ReadableStreamDefaultController<Uint8Array> | undefined;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      streamController = controller;
      controller.enqueue(encoder.encode('event: run_started\ndata: {"run_id":"run-1"}\n\n'));
      setTimeout(() => {
        controller.enqueue(encoder.encode('event: thinking\ndata: {"text":"still working","done":false}\n\n'));
      }, 30);
      setTimeout(() => {
        controller.enqueue(encoder.encode('event: done\ndata: {"id":"message-1"}\n\n'));
      }, 70);
    },
  });

  globalThis.fetch = async (_input, init) => {
    init?.signal?.addEventListener(
      "abort",
      () => {
        try {
          streamController?.error(init.signal?.reason);
        } catch {
          // The stream may already be closed after the done event.
        }
      },
      { once: true },
    );
    return new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
  };

  try {
    const events = [];
    for await (const event of streamMessage("http://127.0.0.1:8140", "session-1", "hello", { timeoutMs: 50 })) {
      events.push(event);
    }

    assert.deepEqual(events.at(-1), { type: "done", id: "message-1", status: "completed" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("stream timeout still fails after an idle gap", async () => {
  const originalFetch = globalThis.fetch;
  let streamController: ReadableStreamDefaultController<Uint8Array> | undefined;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      streamController = controller;
      controller.enqueue(new TextEncoder().encode('event: run_started\ndata: {"run_id":"run-1"}\n\n'));
    },
  });

  globalThis.fetch = async (_input, init) => {
    init?.signal?.addEventListener(
      "abort",
      () => {
        try {
          streamController?.error(init.signal?.reason);
        } catch {
          // The stream may already be closed after the done event.
        }
      },
      { once: true },
    );
    return new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
  };

  try {
    await assert.rejects(
      (async () => {
        for await (const _event of streamMessage("http://127.0.0.1:8140", "session-1", "hello", { timeoutMs: 20 })) {
          // Keep consuming until the idle timeout aborts the stream.
        }
      })(),
      /Request timed out after 20ms\./,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
