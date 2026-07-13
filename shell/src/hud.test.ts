import assert from "node:assert/strict";
import test from "node:test";

import { formatElapsed } from "./hud.js";

test("formats active run duration for the status HUD", () => {
  assert.equal(formatElapsed(1_000, 1_000), "0s");
  assert.equal(formatElapsed(1_000, 60_999), "59s");
  assert.equal(formatElapsed(1_000, 181_000), "3m 0s");
});
