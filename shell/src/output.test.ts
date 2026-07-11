import assert from "node:assert/strict";
import test from "node:test";

import { stripEmojiIcons } from "./output.js";

test("strips decorative emoji icons while preserving Markdown content", () => {
  const source = "# 🛣️ 主流程\n## 🔀 上匝道\n**`/implement`** — 交付功能";

  assert.equal(stripEmojiIcons(source), "# 主流程\n## 上匝道\n**`/implement`** — 交付功能");
});

test("strips emoji sequences without changing ordinary Unicode text", () => {
  const source = "🇨🇳 1️⃣ 👩🏽‍💻 中文 · plain — text ✓";

  assert.equal(stripEmojiIcons(source), "中文 · plain — text ✓");
});
