/**
 * Transcript state machine — pure functions only, no rendering.
 * transcript.tsx renders these structures; store.ts mutates them via applyStreamEvent.
 */

import { type ToolState, toolStateFromResult } from "./activity.js";
import type { Message, StreamEvent } from "./api.js";

type SystemTone = "info" | "error";
export type SkillState = "running" | "done" | "error";
export type TranscriptViewMode = "compact" | "transcript";

export function limitTranscript(entries: TranscriptEntry[], limit: number): TranscriptEntry[] {
  return entries.length <= limit ? entries : entries.slice(-limit);
}

export type SystemEntry = {
  id: string;
  kind: "system";
  text: string;
  tone: SystemTone;
  approvalId?: string;
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

export type ProvisionalText = {
  provisionId: string;
  text: string;
};

export type TurnBlock = ThinkingBlock | ToolBlock | SkillBlock;

export type TurnEntry = {
  id: string;
  kind: "turn";
  userText: string;
  assistantText: string;
  provisional: ProvisionalText[];
  blocks: TurnBlock[];
  streaming: boolean;
};

export type TranscriptEntry = SystemEntry | TurnEntry;

function createId(): string {
  return Math.random().toString(36).slice(2, 10);
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
  if (last?.type !== "thinking" || last.done) {
    return blocks;
  }

  if (!last.text.trim()) {
    return blocks.slice(0, -1);
  }

  return [...blocks.slice(0, -1), { ...last, done: true }];
}

function appendProvisionalText(provisional: ProvisionalText[], provisionId: string, text: string): ProvisionalText[] {
  const index = provisional.findIndex((item) => item.provisionId === provisionId);
  if (index === -1) {
    return [...provisional, { provisionId, text }];
  }

  const existing = provisional[index];
  if (!existing) return provisional;
  const next = [...provisional];
  next[index] = { ...existing, text: existing.text + text };
  return next;
}

function updateLastTurn(entries: TranscriptEntry[], updater: (turn: TurnEntry) => TurnEntry): TranscriptEntry[] {
  const index = findLastTurnIndex(entries);
  if (index === -1) {
    return entries;
  }

  const turn = entries[index];
  if (turn?.kind !== "turn") {
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

export function removeApprovalNotice(entries: TranscriptEntry[], approvalId: string): TranscriptEntry[] {
  return entries.filter((entry) => entry.kind !== "system" || entry.approvalId !== approvalId);
}

export function createTurnEntry(userText: string): TurnEntry {
  return {
    id: createId(),
    kind: "turn",
    userText,
    assistantText: "",
    provisional: [],
    blocks: [],
    streaming: true,
  };
}

export function closeLatestTurn(entries: TranscriptEntry[]): TranscriptEntry[] {
  return updateLastTurn(entries, (turn) => ({
    ...turn,
    blocks: finishThinkingBlocks(turn.blocks),
    provisional: [],
    streaming: false,
  }));
}

function approvalArgumentsSummary(arguments_: Record<string, unknown>): string {
  const entries = Object.entries(arguments_);
  if (entries.length === 0) return "";
  const text = entries
    .map(([key, value]) => `${key}=${typeof value === "string" ? value : (JSON.stringify(value) ?? String(value))}`)
    .join(", ");
  const safeText = Array.from(text, (character) => {
    const code = character.charCodeAt(0);
    return code < 32 || code === 127 ? " " : character;
  }).join("");
  return ` Details: ${safeText.slice(0, 500)}.`;
}

export function applyStreamEvent(entries: TranscriptEntry[], event: StreamEvent): TranscriptEntry[] {
  switch (event.type) {
    case "run_started":
      return entries;

    case "approval_required":
      return [
        ...entries,
        {
          ...createSystemEntry(
            `Approval required for ${event.tool} (${event.level}). ${event.reason}${approvalArgumentsSummary(event.arguments)} Use /approve or /deny.`,
            "info",
          ),
          approvalId: event.approvalId,
        },
      ];

    case "provisional_text_delta":
      if (!event.provisionId || !event.text) return entries;
      return updateLastTurn(entries, (turn) => ({
        ...turn,
        blocks: finishThinkingBlocks(turn.blocks),
        provisional: appendProvisionalText(turn.provisional, event.provisionId, event.text),
      }));

    case "provisional_commit":
      if (!event.provisionId) return entries;
      return updateLastTurn(entries, (turn) => {
        const index = turn.provisional.findIndex((item) => item.provisionId === event.provisionId);
        const settled = turn.provisional[index];
        if (!settled) return turn;
        return {
          ...turn,
          assistantText: turn.assistantText + settled.text,
          provisional: [...turn.provisional.slice(0, index), ...turn.provisional.slice(index + 1)],
        };
      });

    case "provisional_retract":
      if (!event.provisionId) return entries;
      return updateLastTurn(entries, (turn) => {
        const provisional = turn.provisional.filter((item) => item.provisionId !== event.provisionId);
        return provisional.length === turn.provisional.length ? turn : { ...turn, provisional };
      });

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

        const reversedIndex = [...blocks]
          .reverse()
          .findIndex(
            (block) => block.type === "skill" && block.name === (event.name || "skill") && block.state === "running",
          );

        if (reversedIndex >= 0) {
          const index = blocks.length - 1 - reversedIndex;
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

    case "context_usage":
    case "compression":
      return entries;

    case "done":
      return closeLatestTurn(entries);
  }
}

/**
 * Rebuild transcript entries from persisted session messages.
 * Consecutive assistant messages (cancel/retry residue) merge into the previous
 * turn; a leading assistant message becomes a turn with empty user text.
 */
export function restoreTranscript(messages: Message[]): TranscriptEntry[] {
  const entries: TranscriptEntry[] = [];

  for (const message of messages) {
    if (message.role === "user") {
      const turn = createTurnEntry(message.content);
      turn.streaming = false;
      entries.push(turn);
      continue;
    }

    const last = entries[entries.length - 1];
    if (last?.kind === "turn") {
      last.assistantText = last.assistantText ? `${last.assistantText}\n\n${message.content}` : message.content;
      continue;
    }

    const orphan = createTurnEntry("");
    orphan.assistantText = message.content;
    orphan.streaming = false;
    entries.push(orphan);
  }

  return entries;
}

/**
 * Split entries into the immutable prefix (rendered once via <Static>) and the
 * still-changing suffix. Only the last turn can be streaming, so everything
 * before the first streaming turn is final.
 */
export function splitTranscript(entries: TranscriptEntry[]): {
  done: TranscriptEntry[];
  active: TranscriptEntry[];
} {
  const firstActive = entries.findIndex((entry) => entry.kind === "turn" && entry.streaming);
  if (firstActive === -1) {
    return { done: entries, active: [] };
  }
  return { done: entries.slice(0, firstActive), active: entries.slice(firstActive) };
}
