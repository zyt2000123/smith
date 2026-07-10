import { MarkdownText } from "@assistant-ui/react-ink-markdown";
import { Box, Text, useWindowSize } from "ink";
import Spinner from "ink-spinner";

import type { StreamEvent } from "./api.js";

const ACCENT = "#ff4d94";
const MUTED = "#8b8b91";
const BORDER = "#5c5c63";
const SUCCESS = "#93f77b";
const WARNING = "#ffd166";
const INFO = "#e9e9ea";
const ERROR = "#e06c75";
const SKILL = "#c678dd";
const ASSISTANT = "#61afef";

type SystemTone = "info" | "error";
type ToolState = "running" | "success" | "error" | "blocked" | "preflight";
type SkillState = "running" | "done" | "error";
type ToolCount = { total: number; ok: number; error: number; blocked: number; preflight: number };
export type TranscriptViewMode = "compact" | "transcript";

const TOOL_PRESENTATION: Record<ToolState, { color: string; marker: string; label: string }> = {
  running: { color: WARNING, marker: "◐", label: "running" },
  success: { color: SUCCESS, marker: "●", label: "success" },
  error: { color: ERROR, marker: "✕", label: "error" },
  blocked: { color: WARNING, marker: "⛔", label: "permission blocked" },
  preflight: { color: WARNING, marker: "◆", label: "fact preflight" },
};

export type SystemEntry = {
  id: string;
  kind: "system";
  text: string;
  tone: SystemTone;
};

export type ThinkingBlock = {
  id: string;
  type: "thinking";
  text: string;
  done: boolean;
};

export type ToolBlock = {
  id: string;
  type: "tool";
  toolCallId: string;
  name: string;
  hint: string;
  state: ToolState;
  summary: string;
};

export type SkillBlock = {
  id: string;
  type: "skill";
  name: string;
  state: SkillState;
};

export type TurnBlock = ThinkingBlock | ToolBlock | SkillBlock;

export type TurnEntry = {
  id: string;
  kind: "turn";
  userText: string;
  assistantText: string;
  blocks: TurnBlock[];
  streaming: boolean;
};

export type TranscriptEntry = SystemEntry | TurnEntry;
type ToolGroupBlock = {
  id: string;
  type: "tool_group";
  name: string;
  items: ToolBlock[];
};
type ToolSummaryBlock = {
  id: string;
  type: "tool_summary";
  counts: Record<string, ToolCount>;
};
type RenderBlock = ThinkingBlock | ToolBlock | SkillBlock | ToolGroupBlock | ToolSummaryBlock;

function createId(): string {
  return Math.random().toString(36).slice(2, 10);
}

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

function findLastTurnIndex(entries: TranscriptEntry[]): number {
  for (let i = entries.length - 1; i >= 0; i -= 1) {
    if (entries[i]?.kind === "turn") {
      return i;
    }
  }
  return -1;
}

function finishThinkingBlocks(blocks: TurnBlock[]): TurnBlock[] {
  const last = blocks[blocks.length - 1];
  if (!last || last.type !== "thinking" || last.done) {
    return blocks;
  }

  if (!last.text.trim()) {
    return blocks.slice(0, -1);
  }

  return [...blocks.slice(0, -1), { ...last, done: true }];
}

function toolStateFromResult(event: Extract<StreamEvent, { type: "tool_result" }>): ToolState {
  if (event.preflight) return "preflight";
  if (event.blocked) return "blocked";
  if (event.error) return "error";
  return "success";
}

function updateLastTurn(entries: TranscriptEntry[], updater: (turn: TurnEntry) => TurnEntry): TranscriptEntry[] {
  const index = findLastTurnIndex(entries);
  if (index === -1) {
    return entries;
  }

  const turn = entries[index];
  if (!turn || turn.kind !== "turn") {
    return entries;
  }

  const nextTurn = updater(turn);
  if (nextTurn === turn) {
    return entries;
  }

  return [...entries.slice(0, index), nextTurn, ...entries.slice(index + 1)];
}

function nextSkillState(status: string): SkillState {
  if (status === "error") {
    return "error";
  }
  if (status === "start") {
    return "running";
  }
  return "done";
}

export function createSystemEntry(text: string, tone: SystemTone = "info"): SystemEntry {
  return {
    id: createId(),
    kind: "system",
    text,
    tone,
  };
}

export function createTurnEntry(userText: string): TurnEntry {
  return {
    id: createId(),
    kind: "turn",
    userText,
    assistantText: "",
    blocks: [],
    streaming: true,
  };
}

export function closeLatestTurn(entries: TranscriptEntry[]): TranscriptEntry[] {
  return updateLastTurn(entries, (turn) => ({
    ...turn,
    blocks: finishThinkingBlocks(turn.blocks),
    streaming: false,
  }));
}

export function applyStreamEvent(entries: TranscriptEntry[], event: StreamEvent): TranscriptEntry[] {
  switch (event.type) {
    case "message":
      return updateLastTurn(entries, (turn) => ({
        ...turn,
        blocks: finishThinkingBlocks(turn.blocks),
        assistantText: turn.assistantText + event.text,
      }));

    case "thinking":
      return updateLastTurn(entries, (turn) => {
        const blocks = [...turn.blocks];
        const last = blocks[blocks.length - 1];

        if (last?.type === "thinking" && !last.done) {
          const text = event.text || last.text;
          if (event.done && !text.trim()) {
            return {
              ...turn,
              blocks: blocks.slice(0, -1),
            };
          }

          blocks[blocks.length - 1] = {
            ...last,
            text,
            done: event.done,
          };

          return {
            ...turn,
            blocks,
          };
        }

        if (!event.text.trim()) {
          return turn;
        }

        return {
          ...turn,
          blocks: [
            ...blocks,
            {
              id: createId(),
              type: "thinking",
              text: event.text,
              done: event.done,
            },
          ],
        };
      });

    case "tool_call":
      return updateLastTurn(entries, (turn) => {
        const blocks = finishThinkingBlocks(turn.blocks);
        const existingIndex = blocks.findIndex((block) => block.type === "tool" && block.toolCallId === event.id);

        if (existingIndex >= 0) {
          const existing = blocks[existingIndex];
          if (existing?.type !== "tool") {
            return turn;
          }

          const nextBlocks = [...blocks];
          nextBlocks[existingIndex] = {
            ...existing,
            name: event.name || existing.name,
            hint: event.hint || existing.hint,
            state: "running",
          };
          return { ...turn, blocks: nextBlocks };
        }

        return {
          ...turn,
          blocks: [
            ...blocks,
            {
              id: createId(),
              type: "tool",
              toolCallId: event.id,
              name: event.name || "tool",
              hint: event.hint || "",
              state: "running",
              summary: "",
            },
          ],
        };
      });

    case "tool_result":
      return updateLastTurn(entries, (turn) => {
        const blocks = finishThinkingBlocks(turn.blocks);
        const nextState = toolStateFromResult(event);
        const existingIndex = [...blocks]
          .reverse()
          .findIndex((block) => block.type === "tool" && block.toolCallId === event.id);

        if (existingIndex >= 0) {
          const realIndex = blocks.length - 1 - existingIndex;
          const existing = blocks[realIndex];
          if (existing?.type !== "tool") {
            return turn;
          }

          const nextBlocks = [...blocks];
          nextBlocks[realIndex] = {
            ...existing,
            state: nextState,
            summary: event.summary || existing.summary,
          };
          return { ...turn, blocks: nextBlocks };
        }

        return {
          ...turn,
          blocks: [
            ...blocks,
            {
              id: createId(),
              type: "tool",
              toolCallId: event.id,
              name: "tool",
              hint: "",
              state: nextState,
              summary: event.summary || "",
            },
          ],
        };
      });

    case "skill":
      return updateLastTurn(entries, (turn) => {
        const blocks = finishThinkingBlocks(turn.blocks);
        const state = nextSkillState(event.status);

        if (state === "running") {
          return {
            ...turn,
            blocks: [
              ...blocks,
              {
                id: createId(),
                type: "skill",
                name: event.name || "skill",
                state,
              },
            ],
          };
        }

        const realIndex = [...blocks]
          .reverse()
          .findIndex(
            (block) => block.type === "skill" && block.name === (event.name || "skill") && block.state === "running",
          );

        if (realIndex >= 0) {
          const index = blocks.length - 1 - realIndex;
          const existing = blocks[index];
          if (existing?.type !== "skill") {
            return turn;
          }

          const nextBlocks = [...blocks];
          nextBlocks[index] = {
            ...existing,
            state,
          };
          return { ...turn, blocks: nextBlocks };
        }

        return {
          ...turn,
          blocks: [
            ...blocks,
            {
              id: createId(),
              type: "skill",
              name: event.name || "skill",
              state,
            },
          ],
        };
      });

    case "token_usage":
      return entries;

    case "done":
      return closeLatestTurn(entries);
  }
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

function recordToolCount(counts: Record<string, ToolCount>, item: ToolBlock): void {
  const count = counts[item.name] ?? { total: 0, ok: 0, error: 0, blocked: 0, preflight: 0 };
  counts[item.name] = count;
  count.total++;
  if (item.state === "success") count.ok++;
  else if (item.state === "error") count.error++;
  else if (item.state === "blocked") count.blocked++;
  else if (item.state === "preflight") count.preflight++;
}

function collapseCompletedTools(blocks: RenderBlock[]): RenderBlock[] {
  const counts: Record<string, ToolCount> = {};
  const kept: RenderBlock[] = [];
  let collapsed = 0;

  for (const block of blocks) {
    if (block.type === "tool" && block.state !== "running") {
      recordToolCount(counts, block);
      collapsed++;
    } else if (block.type === "tool_group" && !block.items.some((i) => i.state === "running")) {
      for (const item of block.items) {
        recordToolCount(counts, item);
      }
      collapsed++;
    } else if (block.type === "thinking" && block.done) {
      collapsed++;
    } else {
      kept.push(block);
    }
  }

  if (collapsed < 2) return blocks;

  const summary: ToolSummaryBlock = { id: "tool-summary", type: "tool_summary", counts };
  return [summary, ...kept];
}

function ToolSummaryMessage({ block }: { block: ToolSummaryBlock }) {
  const parts = Object.entries(block.counts).map(([name, c]) => {
    const details = [
      c.ok ? `${c.ok} ok` : "",
      c.error ? `${c.error} err` : "",
      c.blocked ? `${c.blocked} blocked` : "",
      c.preflight ? `${c.preflight} preflight` : "",
    ]
      .filter(Boolean)
      .join(", ");
    return `${c.total}x ${name} (${details})`;
  });
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

function TurnViewWithMode({ entry, viewMode }: { entry: TurnEntry; viewMode: TranscriptViewMode }) {
  const hasAssistantBody = entry.assistantText.trim().length > 0;
  const assistantBody = hasAssistantBody ? entry.assistantText.trimEnd() : "";
  const grouped = groupToolBlocks(entry.blocks, viewMode);
  const renderBlocks = viewMode === "compact" ? collapseCompletedTools(grouped) : grouped;

  return (
    <Box flexDirection="column" marginBottom={2}>
      <Box>
        <Text color={ACCENT}>{"❯ "}</Text>
        <Text>{entry.userText}</Text>
      </Box>

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

      {hasAssistantBody || entry.streaming ? (
        <Box flexDirection="column" marginTop={1}>
          <Text color={ASSISTANT} bold>
            smith
          </Text>
          <Box marginTop={1} paddingLeft={1}>
            {hasAssistantBody ? (
              <MarkdownText text={assistantBody} />
            ) : (
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

function TurnDivider({ width }: { width: number }) {
  const lineWidth = Math.max(1, width - 6);
  return (
    <Box marginBottom={2} paddingLeft={1} paddingRight={1}>
      <Text color={BORDER}>{"─".repeat(lineWidth)}</Text>
    </Box>
  );
}

export function Transcript({ entries, viewMode }: { entries: TranscriptEntry[]; viewMode: TranscriptViewMode }) {
  const { columns } = useWindowSize();
  const visibleEntries = entries.slice(viewMode === "transcript" ? -24 : -16);
  let hasRenderedTurn = false;

  return (
    <Box flexDirection="column" marginTop={1}>
      {visibleEntries.map((entry) => {
        if (entry.kind === "system") {
          return <SystemMessage key={entry.id} entry={entry} />;
        }

        const showDivider = hasRenderedTurn;
        hasRenderedTurn = true;
        return (
          <Box key={entry.id} flexDirection="column">
            {showDivider ? <TurnDivider width={columns} /> : null}
            <TurnViewWithMode entry={entry} viewMode={viewMode} />
          </Box>
        );
      })}
    </Box>
  );
}
