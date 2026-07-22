import assert from "node:assert/strict";
import test from "node:test";
import { renderToString } from "ink";
import stringWidth from "string-width";

import { skillPresentation } from "./skill-presentation.js";
import { BORDER } from "./theme.js";
import { processingScanSegments, TranscriptEntryView, userMessageBoxProps } from "./transcript.js";
import { createTurnEntry } from "./transcript-state.js";

function completedTurn(userText: string) {
  return { ...createTurnEntry(userText), streaming: false };
}

function stripAnsi(text: string): string {
  const ansiEscape = String.fromCharCode(27);
  return text.replace(new RegExp(`${ansiEscape}\\[[0-?]*[ -/]*[@-~]`, "g"), "");
}

test("workflow cards expose non-success terminal labels without mounting Ink", () => {
  assert.deepEqual(skillPresentation("running"), { heading: "Running Agent...", tone: "warning" });
  assert.deepEqual(skillPresentation("retry"), { heading: "Retrying Agent...", tone: "warning" });
  assert.deepEqual(skillPresentation("blocked"), { heading: "Agent blocked", tone: "warning" });
  assert.deepEqual(skillPresentation("error"), { heading: "Agent failed", tone: "error" });
  assert.deepEqual(skillPresentation("done"), { heading: "Agent complete", tone: "success" });
});

test("transcript turns frame user messages while aligning their content with replies", () => {
  const entry = { ...completedTurn("hello"), assistantText: "hi there" };
  const output = renderToString(<TranscriptEntryView entry={entry} viewMode="compact" />);

  assert.match(output, /hello/);
  assert.match(output, /hi there/);
  assert.match(output, /╭/);
  assert.match(output, /╰/);
  const lines = stripAnsi(output).split("\n");
  const userLine = lines.find((line) => line.includes("hello"));
  const assistantLine = lines.find((line) => line.includes("hi there"));
  assert.ok(userLine);
  assert.ok(assistantLine);
  assert.equal(userLine.indexOf("❯"), assistantLine.indexOf("●"));
  assert.equal(userLine.indexOf("hello"), assistantLine.indexOf("hi there"));
  assert.deepEqual(userMessageBoxProps(80), {
    width: 76,
    borderColor: BORDER,
    borderStyle: "round",
    paddingX: 1,
  });
  assert.equal(userMessageBoxProps(2).width, 1);
});

test("processing placeholder sweeps its bright character from left to right", () => {
  const firstFrame = processingScanSegments(0);
  const nextFrame = processingScanSegments(1);
  const finalFrame = processingScanSegments(9);

  assert.equal(firstFrame.map((segment) => segment.text).join(""), "Processing");
  assert.deepEqual(
    firstFrame.map((segment) => segment.active),
    [true, false, false, false, false, false, false, false, false, false],
  );
  assert.deepEqual(
    nextFrame.map((segment) => segment.active),
    [false, true, false, false, false, false, false, false, false, false],
  );
  assert.deepEqual(
    finalFrame.map((segment) => segment.active),
    [false, false, false, false, false, false, false, false, false, true],
  );
});

test("transcript renders simple unlabelled relationship diagrams outside generic code blocks", () => {
  const entry = {
    ...completedTurn("Explain outgoing webhooks"),
    assistantText: `\`\`\`
用户系统  <——HTTP POST——  云平台
                      (事件发生时)
\`\`\``,
  };
  const output = stripAnsi(renderToString(<TranscriptEntryView entry={entry} viewMode="compact" />));

  assert.match(output, /用户系统/);
  assert.match(output, /云平台/);
  assert.match(output, /HTTP.*POST/);
  assert.match(output, /事件发生时/);
  assert.doesNotMatch(output, /\[text\] · 2 行/);
});

test("transcript keeps JSON payloads in the code renderer", () => {
  const entry = {
    ...completedTurn("Show an event"),
    assistantText: `\`\`\`json
{
  "event_id": "evt_123"
}
\`\`\``,
  };
  const output = stripAnsi(renderToString(<TranscriptEntryView entry={entry} viewMode="compact" />));

  assert.match(output, /\[json\] · 3 行/);
});

test("transcript renders an invalid smith-ui payload through CodeBlock", () => {
  const entry = {
    ...completedTurn("Show a component"),
    blocks: [
      {
        id: "ui-fallback",
        type: "smith_ui_fallback" as const,
        reason: "Unsupported smith-ui payload",
        code: '{\n  "type": "TextInput"\n}',
      },
    ],
  };
  const output = stripAnsi(renderToString(<TranscriptEntryView entry={entry} viewMode="compact" />));

  assert.match(output, /structured result fallback/);
  assert.match(output, /\[json\] · 3 行/);
});

test("transcript keeps ordinary text code in the code renderer", () => {
  const entry = {
    ...completedTurn("Show a command"),
    assistantText: `\`\`\`
curl --request POST https://example.test
\`\`\``,
  };
  const output = stripAnsi(renderToString(<TranscriptEntryView entry={entry} viewMode="compact" />));

  assert.match(output, /\[text\] · 1 行/);
});

test("transcript keeps every long table cell visible in a narrow terminal", () => {
  const detail = "这段表格内容必须完整保留，不能因为终端宽度不足而被省略号替代。";
  const checksum = `sha256:${"a".repeat(160)}`;
  const entry = {
    ...completedTurn("Show the full table"),
    assistantText: `| Module | 当前职责 |\n| --- | --- |\n| execution | ${detail} |\n| checksum | ${checksum} |`,
  };
  const output = stripAnsi(renderToString(<TranscriptEntryView entry={entry} viewMode="compact" />));
  const compactOutput = output.replace(/[\s│┌┐└┘├┤┬┴┼─]/g, "");

  assert.match(compactOutput, new RegExp(detail));
  assert.match(compactOutput, new RegExp(checksum));
  assert.doesNotMatch(output, /…/);
});

test("transcript keeps an ordinary long Markdown token visible in a 40-column terminal", () => {
  const token = `ordinary_${"m".repeat(72)}`;
  const entry = {
    ...completedTurn("prose"),
    assistantText: `普通正文应该换行，但不能丢失 ${token}`,
  };
  const output = stripAnsi(
    renderToString(<TranscriptEntryView entry={entry} viewMode="compact" terminalColumns={40} />, { columns: 40 }),
  );
  const compact = output.replace(/\s/g, "");

  assert.ok(output.split("\n").every((line) => stringWidth(line) <= 40));
  assert.match(compact, new RegExp(token));
});

test("transcript keeps a full grid inside a 40-column terminal", () => {
  const checksum = `sha256:${"b".repeat(72)}`;
  const entry = {
    ...completedTurn("table"),
    assistantText: `| 模块 | 内容 |\n| --- | --- |\n| execution | 终端表格必须完整换行，不得省略。 |\n| checksum | ${checksum} |`,
  };
  const output = stripAnsi(
    renderToString(<TranscriptEntryView entry={entry} viewMode="compact" terminalColumns={40} />, { columns: 40 }),
  );
  const compact = output.replace(/[\s│┌┐└┘├┤┬┴┼─]/g, "");

  assert.ok(output.split("\n").every((line) => stringWidth(line) <= 40));
  assert.match(compact, new RegExp(checksum));
  assert.match(output, /┌.*┬.*┐/);
});

test("transcript keeps structured diffs inside a 40-column terminal", () => {
  const checksum = `sha256:${"d".repeat(72)}`;
  const entry = {
    ...completedTurn("diff"),
    assistantText: `\`\`\`diff\n@@ -1 +1 @@\n-const checksum = "old";\n+const checksum = "${checksum}";\n\`\`\``,
  };
  const output = stripAnsi(
    renderToString(<TranscriptEntryView entry={entry} viewMode="compact" terminalColumns={40} />, { columns: 40 }),
  );
  const compact = output.replace(/[\s│┌┐└┘├┤┬┴┼─]/g, "");

  assert.ok(output.split("\n").every((line) => stringWidth(line) <= 40));
  assert.match(compact, new RegExp(checksum));
});

test("transcript does not truncate a narrow fenced code block", () => {
  const token = `token_${"c".repeat(72)}`;
  const entry = {
    ...completedTurn("code"),
    assistantText: `\`\`\`typescript\nconst value = "${token}";\n\`\`\``,
  };
  const output = stripAnsi(
    renderToString(<TranscriptEntryView entry={entry} viewMode="compact" terminalColumns={40} />, { columns: 40 }),
  );
  const compact = output.replace(/[\s│┌┐└┘├┤┬┴┼─]/g, "");

  assert.ok(output.split("\n").every((line) => stringWidth(line) <= 40));
  assert.match(compact, new RegExp(token));
});

test("transcript renders fenced diffs with structured line gutters", () => {
  const entry = {
    ...completedTurn("Show the patch"),
    assistantText: "```diff\n@@ -1 +1 @@\n-const mode = 'old';\n+const mode = 'new';\n```",
  };
  const output = stripAnsi(renderToString(<TranscriptEntryView entry={entry} viewMode="compact" />));

  assert.match(output, /@@ -1 \+1 @@/);
  assert.match(output, /│ - const mode = 'old';/);
  assert.match(output, /│ \+ const mode = 'new';/);
});
