import assert from "node:assert/strict";
import test from "node:test";

import { parseUnifiedDiff, renderDiffLines } from "./diff-block.js";
import { displayWidth } from "./text-layout.js";

const SOURCE = [
  "diff --git a/src/example.ts b/src/example.ts",
  "--- a/src/example.ts",
  "+++ b/src/example.ts",
  "@@ -1,2 +1,2 @@",
  "-const message = 'old value';",
  "+const message = 'new value';",
  " export { message };",
].join("\n");

test("parses unified diff gutters and pairs neighbouring additions and deletions", () => {
  const diff = parseUnifiedDiff(SOURCE);

  assert.deepEqual(
    diff.lines.map((line) => [line.kind, line.oldLine, line.newLine]),
    [
      ["meta", null, null],
      ["file-old", null, null],
      ["file-new", null, null],
      ["hunk", null, null],
      ["deletion", 1, null],
      ["addition", null, 1],
      ["context", 2, 2],
    ],
  );
  assert.ok(diff.lines[4]?.changedRanges?.length);
  assert.ok(diff.lines[5]?.changedRanges?.length);
});

test("wraps long diff content with a hanging gutter and preserves every character", () => {
  const diff = parseUnifiedDiff(`@@ -1 +1 @@\n-${"a".repeat(36)}\n+${"b".repeat(36)}`);
  const lines = renderDiffLines(diff, 24);

  assert.ok(lines.every((line) => displayWidth(line.text) <= 24));
  assert.match(lines.map((line) => line.content).join(""), /a{36}/);
  assert.match(lines.map((line) => line.content).join(""), /b{36}/);
  assert.ok(lines.filter((line) => line.continuation).every((line) => line.text.startsWith("      │ ")));
});
