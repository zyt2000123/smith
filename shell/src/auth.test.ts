import assert from "node:assert/strict";
import test from "node:test";

import { buildAuthHeaders } from "./auth.js";

test("builds the bearer header used by local API requests", () => {
  assert.deepEqual(buildAuthHeaders("local-token"), {
    Authorization: "Bearer local-token",
  });
});
