import { createToolActivity, type ToolActivity } from "./activity.js";
import type { Session, SkillSummary, TokenUsage } from "./api.js";
import type { QueuedMessage } from "./queue.js";
import type { TranscriptEntry } from "./transcript-state.js";

export type ConversationPanel = "welcome" | "chat";

export type EmptyConversation = {
  currentSession: Session | null;
  transcript: TranscriptEntry[];
  turnCount: number;
  toolActivity: ToolActivity;
  tokenUsage: TokenUsage;
  pendingSkill: SkillSummary | null;
  queuedMessages: QueuedMessage[];
  welcomeNotice: { text: string; tone: "info" | "error" } | null;
  panel: ConversationPanel;
  statusLine: string;
};

export function createEmptyConversation(panel: ConversationPanel, statusLine: string): EmptyConversation {
  return {
    currentSession: null,
    transcript: [],
    turnCount: 0,
    toolActivity: createToolActivity(),
    tokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
    pendingSkill: null,
    queuedMessages: [],
    welcomeNotice: null,
    panel,
    statusLine,
  };
}
