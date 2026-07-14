import assert from "node:assert/strict";
import test from "node:test";

import { buildRecentDays, TOKEN_TABS } from "./token-stats.js";

test("token dashboard tabs exclude the redundant daily breakdown", () => {
  assert.deepEqual(TOKEN_TABS, ["overview", "models", "stats"]);
});

test("buildRecentDays fills a rolling seven-day window with zero-usage days", () => {
  const days = buildRecentDays(
    [
      { date: "2026-07-10", input_tokens: 10, output_tokens: 5, total_tokens: 15, sessions: 1 },
      { date: "2026-07-14", input_tokens: 20, output_tokens: 10, total_tokens: 30, sessions: 2 },
    ],
    "2026-07-14",
  );

  assert.deepEqual(
    days.map((day) => day.date),
    ["2026-07-08", "2026-07-09", "2026-07-10", "2026-07-11", "2026-07-12", "2026-07-13", "2026-07-14"],
  );
  assert.equal(days[0]?.total_tokens, 0);
  assert.equal(days[2]?.total_tokens, 15);
  assert.equal(days[6]?.sessions, 2);
});
