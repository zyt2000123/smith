/** Transcript rendering — state shapes and transitions live in transcript-state.ts. */

import { MarkdownText } from "@assistant-ui/react-ink-markdown";
import { Box, Text, useWindowSize } from "ink";
import Spinner from "ink-spinner";

import type { ToolState } from "./activity.js";
import { stripEmojiIcons } from "./output.js";
import { ACCENT, ASSISTANT, BORDER, ERROR, INFO, MUTED, SKILL, SUCCESS, WARNING } from "./theme.js";
import type {
  SkillBlock,
  SystemEntry,
  ThinkingBlock,
  ToolBlock,
  TranscriptEntry,
  TranscriptViewMode,
  TurnBlock,
  TurnEntry,
} from "./transcript-state.js";

const TOOL_PRESENTATION: Record<ToolState, { color: string; marker: string; label: string }> = {
  running: { color: WARNING, marker: "◐", label: "running" },
  success: { color: SUCCESS, marker: "●", label: "success" },
  error: { color: ERROR, marker: "✕", label: "error" },
  blocked: { color: WARNING, marker: "⛔", label: "permission blocked" },
  preflight: { color: WARNING, marker: "◆", label: "fact preflight" },
};

type ToolGroupBlock = {
  id: string;
  type: "tool_group";
  name: string;
  items: ToolBlock[];
};
type ToolSummaryBlock = {
  id: string;
  type: "tool_summary";
  counts: Record<string, number>;
};
type RenderBlock = ThinkingBlock | ToolBlock | SkillBlock | ToolGroupBlock | ToolSummaryBlock;

function truncate(text: string, max = 80): string {
  if (text.length <= max) {
    return text;
  }
  return `${text.slice(0, max - 1)}…`;
}

function truncateLines(text: string, max = 4): { text: string; hidden: number } {
  const lines = text.split("\n");
  if (lines.length <= max) {
    return { text, hidden: 0 };
  }
  return {
    text: lines.slice(0, max).join("\n"),
    hidden: lines.length - max,
  };
}

function SystemMessage({ entry }: { entry: SystemEntry }) {
  const trimmed = entry.text.trim();
  return (
    <Box marginBottom={1} paddingLeft={1}>
      {trimmed ? (
        <MarkdownText text={trimmed} />
      ) : (
        <Text color={entry.tone === "error" ? ERROR : MUTED}>{entry.text}</Text>
      )}
    </Box>
  );
}

function ThinkingMessage({ block, viewMode }: { block: ThinkingBlock; viewMode: TranscriptViewMode }) {
  const { text, hidden } = truncateLines(block.text, viewMode === "transcript" ? 5 : 2);
  return (
    <Box flexDirection="column" marginTop={1} paddingLeft={2}>
      <Text color={MUTED} italic>
        {block.done ? "∴ thinking" : "∴ thinking..."}
      </Text>
      <Text dimColor>{text || "working..."}</Text>
      {hidden > 0 ? (
        <Text color={BORDER}>
          … {hidden} more line{hidden === 1 ? "" : "s"}
        </Text>
      ) : null}
    </Box>
  );
}

function groupToolBlocks(blocks: TurnBlock[], viewMode: TranscriptViewMode): RenderBlock[] {
  if (viewMode === "transcript") {
    return blocks;
  }

  const grouped: RenderBlock[] = [];
  for (const block of blocks) {
    const previous = grouped[grouped.length - 1];
    if (block.type === "tool" && previous?.type === "tool_group" && previous.name === block.name) {
      previous.items.push(block);
      continue;
    }

    if (block.type === "tool" && previous?.type === "tool" && previous.name === block.name) {
      grouped[grouped.length - 1] = {
        id: previous.id,
        type: "tool_group",
        name: block.name,
        items: [previous, block],
      };
      continue;
    }

    grouped.push(block);
  }
  return grouped;
}

function recordSuccess(counts: Record<string, number>, item: ToolBlock): void {
  counts[item.name] = (counts[item.name] ?? 0) + 1;
}

function collapseBlock(block: RenderBlock, counts: Record<string, number>, kept: RenderBlock[]): boolean {
  if (block.type === "tool" && block.state === "success") {
    recordSuccess(counts, block);
    return true;
  }
  if (block.type === "tool_group" && block.items.every((item) => item.state === "success")) {
    for (const item of block.items) {
      recordSuccess(counts, item);
    }
    return true;
  }
  if (block.type === "thinking" && block.done) return true;

  kept.push(block);
  return false;
}

function collapseCompletedTools(blocks: RenderBlock[]): RenderBlock[] {
  const counts: Record<string, number> = {};
  const kept: RenderBlock[] = [];
  let collapsed = 0;

  for (const block of blocks) {
    if (collapseBlock(block, counts, kept)) collapsed++;
  }

  if (collapsed < 2) return blocks;
  if (Object.keys(counts).length === 0) return kept;

  const summary: ToolSummaryBlock = { id: "tool-summary", type: "tool_summary", counts };
  return [summary, ...kept];
}

function ToolSummaryMessage({ block }: { block: ToolSummaryBlock }) {
  const parts = Object.entries(block.counts).map(([name, count]) => `${count}x ${name}`);
  return (
    <Box marginTop={1} paddingLeft={2}>
      <Text color={SUCCESS}>✓ </Text>
      <Text color={MUTED}>{parts.join("  ")}</Text>
    </Box>
  );
}

function toolSummaryColor(state: ToolState): string {
  if (state === "error") return ERROR;
  if (state === "blocked" || state === "preflight") return WARNING;
  return MUTED;
}

function ToolMessage({ block, viewMode }: { block: ToolBlock; viewMode: TranscriptViewMode }) {
  const presentation = TOOL_PRESENTATION[block.state];
  const { text, hidden } = truncateLines(block.summary, viewMode === "transcript" ? 5 : 3);

  return (
    <Box flexDirection="column" marginTop={1} paddingLeft={2}>
      <Box>
        <Text color={presentation.color}>{presentation.marker} </Text>
        <Text color={presentation.color} bold>
          {block.name}
        </Text>
        {block.hint ? (
          <Text color={MUTED}>
            {" ("}
            {truncate(block.hint, 56)}
            {")"}
          </Text>
        ) : null}
        <Text color={MUTED}>
          {"  "}
          {presentation.label}
        </Text>
      </Box>
      {block.summary ? (
        <>
          <Text color={toolSummaryColor(block.state)}> {text}</Text>
          {hidden > 0 ? (
            <Text color={BORDER}>
              {" "}
              … {hidden} more line{hidden === 1 ? "" : "s"}
            </Text>
          ) : null}
        </>
      ) : block.state === "running" ? (
        <Text color={BORDER}> waiting for result...</Text>
      ) : null}
    </Box>
  );
}

function ToolGroupMessage({ group }: { group: ToolGroupBlock }) {
  const successCount = group.items.filter((item) => item.state === "success").length;
  const blockedCount = group.items.filter((item) => item.state === "blocked").length;
  const preflightCount = group.items.filter((item) => item.state === "preflight").length;
  const errorCount = group.items.filter((item) => item.state === "error").length;
  const runningCount = group.items.filter((item) => item.state === "running").length;
  const lastHint = group.items[group.items.length - 1]?.hint || group.items[0]?.hint || "";
  const headline = [
    successCount ? `${successCount} ok` : "",
    blockedCount ? `${blockedCount} blocked` : "",
    preflightCount ? `${preflightCount} preflight` : "",
    errorCount ? `${errorCount} error` : "",
    runningCount ? `${runningCount} running` : "",
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <Box flexDirection="column" marginTop={1} paddingLeft={2}>
      <Box>
        <Text color={INFO}>◦ </Text>
        <Text color={INFO} bold>
          {group.items.length}x {group.name}
        </Text>
        {lastHint ? (
          <Text color={MUTED}>
            {" ("}
            {truncate(lastHint, 48)}
            {")"}
          </Text>
        ) : null}
      </Box>
      <Text color={MUTED}> {headline || "grouped tool activity"}</Text>
    </Box>
  );
}

function SkillMessage({ block }: { block: SkillBlock }) {
  const color = block.state === "error" ? ERROR : SKILL;
  const statusText = block.state === "running" ? "running" : block.state;

  return (
    <Box marginTop={1} paddingLeft={2}>
      <Text color={color}>◦ </Text>
      <Text color={color} bold>
        skill
      </Text>
      <Text color={INFO}> {block.name}</Text>
      <Text color={MUTED}>
        {"  "}
        {statusText}
      </Text>
    </Box>
  );
}

function TurnView({ entry, viewMode }: { entry: TurnEntry; viewMode: TranscriptViewMode }) {
  const hasAssistantBody = entry.assistantText.trim().length > 0;
  const assistantBody = hasAssistantBody ? stripEmojiIcons(entry.assistantText).trimEnd() : "";
  const provisionalBody = stripEmojiIcons(entry.provisional.map((item) => item.text).join(""));
  const hasProvisionalBody = provisionalBody.trim().length > 0;
  const grouped = groupToolBlocks(entry.blocks, viewMode);
  const renderBlocks = viewMode === "compact" ? collapseCompletedTools(grouped) : grouped;

  return (
    <Box flexDirection="column" marginBottom={2}>
      {entry.userText ? (
        <Box>
          <Text color={ACCENT}>{"❯ "}</Text>
          <Text>{entry.userText}</Text>
        </Box>
      ) : null}

      {renderBlocks.map((block) => {
        switch (block.type) {
          case "thinking":
            return <ThinkingMessage key={block.id} block={block} viewMode={viewMode} />;
          case "tool":
            return <ToolMessage key={block.id} block={block} viewMode={viewMode} />;
          case "tool_group":
            return <ToolGroupMessage key={block.id} group={block} />;
          case "tool_summary":
            return <ToolSummaryMessage key={block.id} block={block} />;
          case "skill":
            return <SkillMessage key={block.id} block={block} />;
          default:
            return null;
        }
      })}

      {hasAssistantBody || hasProvisionalBody || entry.streaming ? (
        <Box flexDirection="column" marginTop={1}>
          <Text color={ASSISTANT} bold>
            smith
          </Text>
          <Box marginTop={1} paddingLeft={1}>
            {hasAssistantBody ? <MarkdownText text={assistantBody} /> : null}
            {hasProvisionalBody ? (
              <Box flexDirection="column">
                <Text color={MUTED} italic>
                  draft…
                </Text>
                <MarkdownText text={provisionalBody} />
              </Box>
            ) : hasAssistantBody ? null : (
              <Box>
                <Spinner type="dots" />
                <Text color={WARNING}> Processing…</Text>
              </Box>
            )}
          </Box>
        </Box>
      ) : null}
    </Box>
  );
}

function TurnDivider() {
  const { columns } = useWindowSize();
  const lineWidth = Math.max(1, columns - 6);
  return (
    <Box marginBottom={2} paddingLeft={1} paddingRight={1}>
      <Text color={BORDER}>{"─".repeat(lineWidth)}</Text>
    </Box>
  );
}

/**
 * Renders one transcript entry. Completed entries go through Ink's <Static>
 * (rendered exactly once, then live in scrollback); the active streaming turn
 * renders in the dynamic region with the same component.
 */
export function TranscriptEntryView({
  entry,
  showDivider,
  viewMode,
}: {
  entry: TranscriptEntry;
  showDivider: boolean;
  viewMode: TranscriptViewMode;
}) {
  if (entry.kind === "system") {
    return <SystemMessage entry={entry} />;
  }

  return (
    <Box flexDirection="column">
      {showDivider ? <TurnDivider /> : null}
      <TurnView entry={entry} viewMode={viewMode} />
    </Box>
  );
}
