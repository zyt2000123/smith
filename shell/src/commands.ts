import type { SkillSummary } from "./api.js";
import type { NodeBridge } from "./bridge.js";
import { createSetupDraft } from "./setup.js";
import type { AppStore } from "./store.js";
import { clearTerminal } from "./term.js";

export type SlashItem = {
  id: string;
  kind: "command" | "skill";
  title: string;
  command: string;
  description: string;
  category: string;
  skill?: SkillSummary;
};

type CommandContext = {
  bridge: NodeBridge;
  exit: () => void;
  getState: () => AppStore;
};

type CommandHandler = (args: string[], context: CommandContext) => Promise<void> | void;

const HELP_TEXT = [
  "- `/new` — fresh session",
  "- `/config` — edit LLM config",
  "- `/sessions` — recent sessions",
  "- `/skills` — inspect skills",
  "- `/resume <id>` — resume session",
  "- `/compact` / `/transcript` — switch view",
  "- `/home` — welcome · `/exit` — quit",
].join("\n");

export function buildSlashItems(skills: SkillSummary[]): SlashItem[] {
  const commands: SlashItem[] = [
    {
      id: "help",
      kind: "command",
      title: "/help",
      command: "/help",
      description: "Show commands.",
      category: "Commands",
    },
    { id: "exit", kind: "command", title: "/exit", command: "/exit", description: "Quit Smith.", category: "Commands" },
    { id: "new", kind: "command", title: "/new", command: "/new", description: "Fresh session.", category: "Commands" },
    {
      id: "config",
      kind: "command",
      title: "/config",
      command: "/config",
      description: "Edit LLM config.",
      category: "Commands",
    },
    {
      id: "sessions",
      kind: "command",
      title: "/sessions",
      command: "/sessions",
      description: "Recent sessions.",
      category: "Commands",
    },
    {
      id: "skills",
      kind: "command",
      title: "/skills",
      command: "/skills",
      description: "Inspect skills.",
      category: "Commands",
    },
    {
      id: "clear",
      kind: "command",
      title: "/clear",
      command: "/clear",
      description: "Clear conversation.",
      category: "Commands",
    },
    {
      id: "compact",
      kind: "command",
      title: "/compact",
      command: "/compact",
      description: "Compact view.",
      category: "Commands",
    },
    {
      id: "transcript",
      kind: "command",
      title: "/transcript",
      command: "/transcript",
      description: "Verbose view.",
      category: "Commands",
    },
  ];

  return [
    ...commands,
    ...skills.map((skill) => ({
      id: `sk-${skill.name}`,
      kind: "skill" as const,
      title: skill.name,
      command: `/${skill.name}`,
      description: skill.description || "Run skill.",
      category: "Skills",
      skill,
    })),
  ];
}

export function filterSlash(items: SlashItem[], input: string): SlashItem[] {
  if (!input.startsWith("/")) return [];

  const query = input.slice(1).trim().toLowerCase();
  if (!query) return items.slice(0, 12);
  return items
    .filter((item) => `${item.command} ${item.title} ${item.description}`.toLowerCase().includes(query))
    .slice(0, 12);
}

export function parseSkill(raw: string, skills: SkillSummary[]): { skill: SkillSummary; prompt: string } | null {
  const match = raw.trim().match(/^\/skill\s+(\S+)(?:\s+([\s\S]+))?$/);
  if (!match) return null;

  const skill = skills.find((candidate) => candidate.name === match[1]);
  return skill ? { skill, prompt: match[2]?.trim() || "" } : null;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function openConfig(context: CommandContext): void {
  const state = context.getState();
  const draft = createSetupDraft(state.config);
  state.set({
    mode: "setup",
    setupIndex: 0,
    setupDraft: draft,
    inputValue: draft.provider,
    statusLine: "Editing config.",
  });
}

async function resumeSession(args: string[], context: CommandContext): Promise<void> {
  const target = args[0];
  if (!target) {
    context.getState().set({ statusLine: "Usage: /resume <session-id>" });
    return;
  }

  const matches = context.getState().sessions.filter((candidate) => candidate.id.startsWith(target));
  if (matches.length === 0) {
    context.getState().set({ statusLine: `Not found: ${target}` });
    return;
  }
  if (matches.length > 1) {
    context.getState().set({ statusLine: `Ambiguous session prefix: ${target}` });
    return;
  }

  const [session] = matches;
  if (session) await context.bridge.resumeSession(session);
}

const COMMAND_HANDLERS: Record<string, CommandHandler> = {
  // process.exit 由 index.tsx 的 waitUntilExit() 在 Ink 卸载后统一触发
  "/exit": (_args, context) => context.exit(),
  "/quit": (_args, context) => context.exit(),
  "/new": (_args, context) => {
    clearTerminal();
    context.getState().resetChat();
  },
  "/config": (_args, context) => openConfig(context),
  "/skills": (_args, context) => {
    const state = context.getState();
    state.set({ panel: "skills", statusLine: `${state.skills.length} skill(s).` });
  },
  "/sessions": (_args, context) => {
    const state = context.getState();
    state.set({ panel: "sessions", statusLine: `${state.sessions.length} session(s).` });
  },
  "/compact": (_args, context) =>
    context.getState().set({ viewMode: "compact", panel: "chat", statusLine: "Compact view." }),
  "/transcript": (_args, context) =>
    context.getState().set({ viewMode: "transcript", panel: "chat", statusLine: "Transcript view." }),
  "/clear": (_args, context) => {
    clearTerminal();
    context.getState().clearChat();
  },
  "/resume": resumeSession,
  "/home": (_args, context) => context.getState().set({ panel: "welcome" }),
  "/help": (_args, context) => {
    const state = context.getState();
    state.pushSystemLine(HELP_TEXT);
    state.set({ panel: "chat", statusLine: "Help." });
  },
};

export async function runShellCommand(raw: string, context: CommandContext): Promise<void> {
  const [command, ...args] = raw.trim().split(/\s+/);
  const handler = command ? COMMAND_HANDLERS[command] : undefined;
  if (handler) {
    await handler(args, context);
    return;
  }

  const state = context.getState();
  const skill = state.skills.find((candidate) => candidate.name === command?.slice(1));
  if (!skill) {
    state.set({ statusLine: `Unknown: ${command}` });
    return;
  }

  const prompt = args.join(" ").trim();
  if (prompt) {
    await context.bridge.sendMessage(prompt, skill.name);
    return;
  }

  state.set({ pendingSkill: skill, panel: "chat", statusLine: `Skill ${skill.name} armed.` });
}
