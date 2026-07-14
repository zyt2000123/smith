import assert from "node:assert/strict";
import test from "node:test";

import { buildHeatmapWeeks, tokenLevel } from "./token-stats.js";

test("tokenLevel maps empty and increasing days to stable heat levels", () => {
  assert.equal(tokenLevel(0, 100), 0);
  assert.equal(tokenLevel(1, 100), 1);
  assert.equal(tokenLevel(25, 100), 1);
  assert.equal(tokenLevel(26, 100), 2);
  assert.equal(tokenLevel(51, 100), 3);
  assert.equal(tokenLevel(76, 100), 4);
  assert.equal(tokenLevel(100, 100), 5);
});

test("buildHeatmapWeeks pads a year into Monday-first columns", () => {
  const weeks = buildHeatmapWeeks(2026, [
    { date: "2026-01-01", input_tokens: 10, output_tokens: 5, total_tokens: 15, sessions: 1 },
    { date: "2026-12-31", input_tokens: 20, output_tokens: 10, total_tokens: 30, sessions: 1 },
  ]);

  assert.equal(weeks.length, 53);
  assert.equal(weeks[0]?.[3]?.date, "2026-01-01");
  assert.equal(weeks[0]?.[3]?.level, 2);
  assert.equal(weeks[52]?.[3]?.date, "2026-12-31");
});
