import assert from "node:assert/strict";
import test from "node:test";

import { renderMermaidDiagram, splitMarkdownBlocks, splitMermaidBlocks } from "./mermaid.js";

test("splits ordinary fenced code into a code segment", () => {
  assert.deepEqual(splitMarkdownBlocks("Before\n\n```python\nprint('hi')\n```\n\nAfter"), [
    { type: "markdown", text: "Before\n" },
    { type: "code", language: "python", text: "print('hi')" },
    { type: "markdown", text: "\nAfter" },
  ]);
});

test("splits Mermaid fenced blocks from surrounding Markdown", () => {
  const segments = splitMermaidBlocks("Before\n\n```mermaid\nflowchart TD\n  A[Start] --> B[End]\n```\n\nAfter");

  assert.deepEqual(segments, [
    { type: "markdown", text: "Before\n" },
    { type: "mermaid", text: "flowchart TD\n  A[Start] --> B[End]" },
    { type: "markdown", text: "\nAfter" },
  ]);
});

test("recognizes Mermaid language tags case-insensitively", () => {
  const segments = splitMermaidBlocks("```Mermaid\ngraph LR\n  A --> B\n```");

  assert.deepEqual(segments, [{ type: "mermaid", text: "graph LR\n  A --> B" }]);
});

test("keeps an unfinished Mermaid fence as ordinary Markdown", () => {
  const source = "```mermaid\nflowchart TD\n  A --> B";

  assert.deepEqual(splitMermaidBlocks(source), [{ type: "markdown", text: source }]);
});

test("renders a basic Mermaid flowchart as terminal Unicode", () => {
  const rendered = renderMermaidDiagram("flowchart TD\n  A[Start] --> B[End]");

  assert.match(rendered ?? "", /Start/);
  assert.match(rendered ?? "", /End/);
  assert.match(rendered ?? "", /[┌┐└┘]/);
  assert.doesNotMatch(rendered ?? "", /A\[Start\]/);
  assert.equal(
    rendered?.split("\n").some((line) => line.endsWith(" ")),
    false,
  );
});

test("returns null for an unsupported or invalid diagram", () => {
  assert.equal(renderMermaidDiagram("not valid Mermaid"), null);
});
