import assert from "node:assert/strict";
import test from "node:test";

import { displayWidth, padDisplayText, wrapDisplayText } from "./text-layout.js";

test("hard-wraps CJK and unspaced identifiers without losing characters", () => {
  const source = `模块职责：${"sha256:"}${"a".repeat(24)}`;
  const lines = wrapDisplayText(source, { width: 10, breakLongTokens: true });

  assert.equal(lines.join(""), source);
  assert.ok(lines.every((line) => displayWidth(line) <= 10));
});

test("keeps an unbroken URL intact when hard wrapping is disabled", () => {
  const url = "https://example.test/a/very/long/path";

  assert.deepEqual(wrapDisplayText(url, { width: 12, breakLongTokens: false }), [url]);
});

test("wraps ordinary words at whitespace before splitting a word", () => {
  assert.deepEqual(wrapDisplayText("one two three", { width: 7, breakLongTokens: true }), ["one two", "three"]);
});

test("hard-wraps preserved indentation instead of creating a wide whitespace line", () => {
  const source = "      value";
  const lines = wrapDisplayText(source, { width: 3, breakLongTokens: true, preserveWhitespace: true });

  assert.equal(lines.join(""), source);
  assert.ok(lines.every((line) => displayWidth(line) <= 3));
});

test("pads CJK text using terminal display width", () => {
  assert.equal(padDisplayText("模块", 8, "right"), "    模块");
  assert.equal(displayWidth(padDisplayText("模块", 8, "center")), 8);
});
