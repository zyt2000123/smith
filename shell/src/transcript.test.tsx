import assert from "node:assert/strict";
import test from "node:test";
import { renderToString } from "ink";

import { skillPresentation } from "./skill-presentation.js";
import { BORDER } from "./theme.js";
import { TranscriptEntryView, userMessageBoxProps } from "./transcript.js";
import { createTurnEntry } from "./transcript-state.js";

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
  const entry = { ...createTurnEntry("hello"), assistantText: "hi there" };
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

test("transcript renders simple unlabelled relationship diagrams outside generic code blocks", () => {
  const entry = {
    ...createTurnEntry("Explain outgoing webhooks"),
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
    ...createTurnEntry("Show an event"),
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
    ...createTurnEntry("Show a component"),
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
    ...createTurnEntry("Show a command"),
    assistantText: `\`\`\`
curl --request POST https://example.test
\`\`\``,
  };
  const output = stripAnsi(renderToString(<TranscriptEntryView entry={entry} viewMode="compact" />));

  assert.match(output, /\[text\] · 1 行/);
});
