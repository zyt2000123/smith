import assert from "node:assert/strict";
import test from "node:test";

import { createEmptyConversation } from "./conversation.js";

test("clearing a conversation removes the armed skill and all HUD state", () => {
  const conversation = createEmptyConversation("chat", "Conversation cleared. Next message starts a fresh session.");

  assert.equal(conversation.pendingSkill, null);
  assert.equal(conversation.currentSession, null);
  assert.equal(conversation.turnCount, 0);
  assert.deepEqual(conversation.transcript, []);
  assert.deepEqual(conversation.toolActivity, {
    calls: {},
    running: {},
    successes: {},
    errors: {},
    blocked: {},
    preflight: {},
  });
});
