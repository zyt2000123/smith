import assert from "node:assert/strict";
import test from "node:test";

import { formatCodeLines } from "./code-block.js";

test("formats code with aligned line numbers", () => {
  assert.deepEqual(formatCodeLines("const x = 1;\nreturn x;", undefined, "typescript"), [
    { number: "1", text: "const x = 1;" },
    { number: "2", text: "return x;" },
  ]);
});

test("passes the complete code block and language to the highlighter", () => {
  const calls: Array<{ code: string; language?: string }> = [];
  const highlighter = (code: string, language?: string) => {
    calls.push({ code, language });
    return `highlighted:${code}`;
  };

  assert.deepEqual(formatCodeLines("print('hi')", highlighter, "python"), [
    { number: "1", text: "highlighted:print('hi')" },
  ]);
  assert.deepEqual(calls, [{ code: "print('hi')", language: "python" }]);
});

test("keeps an empty code block visible as one line", () => {
  assert.deepEqual(formatCodeLines("", undefined, undefined), [{ number: "1", text: "" }]);
});

test("falls back to raw code when highlighting fails", () => {
  const highlighter = () => {
    throw new Error("unsupported language");
  };

  assert.deepEqual(formatCodeLines("plain", highlighter, "unknown"), [{ number: "1", text: "plain" }]);
});
