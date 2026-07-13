import assert from "node:assert/strict";
import test from "node:test";

import { decodeSseEvent } from "./api.js";

test("SSE decoder accepts standard data fields without a trailing space", () => {
  const event = decodeSseEvent('event: done\ndata:{"id":"message-1"}');

  assert.deepEqual(event, { type: "done", id: "message-1", status: "completed" });
});

test("SSE decoder exposes the run id when execution starts", () => {
  assert.deepEqual(
    decodeSseEvent('event: run_started\ndata: {"run_id":"run-1"}'),
    { type: "run_started", runId: "run-1" },
  );
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
