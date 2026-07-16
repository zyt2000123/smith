import type { SkillSummary } from "./api.js";
import { errorMessage, type NodeBridge } from "./bridge.js";
import { createSetupDraft } from "./setup.js";
import type { AppStore } from "./store.js";

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
  workingDir?: string;
};

type CommandHandler = (args: string[], context: CommandContext) => Promise<void> | void;

const HELP_TEXT = [
  "- `/new` — start a fresh session and keep the current session in history",
  "- `/init` — create a project .smith/SMITH.md instruction template",
  "- `/clear` — delete the current session and start fresh",
  "- `/compress` — summarize and persist the active session context",
  "- `/model` — discover relay models and configure the primary or review model",
  "- `/config` — edit LLM config",
  "- `/sessions` — recent sessions",
  "- `/token` — local token usage dashboard",
  "- `/skill [name] [prompt]` / `/skills` — inspect or run a standard SKILL.md skill",
  "- `/mcp` — inspect configured MCP servers and tools",
  "- `/resume <id>` — resume session",
  "- `/run resume [id]` — recover the last failed or interrupted run",
  "- `/compact` — switch to compact view; Ctrl+O toggles compact/transcript",
  "- `/exit` — quit",
].join("\n");

export function buildSlashItems(_skills: SkillSummary[]): SlashItem[] {
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
    {
      id: "new",
      kind: "command",
      title: "/new",
      command: "/new",
      description: "New session; keep history.",
      category: "Commands",
    },
    {
      id: "init",
      kind: "command",
      title: "/init",
      command: "/init",
      description: "Create a project instruction template.",
      category: "Commands",
    },
    {
      id: "compress",
      kind: "command",
      title: "/compress",
      command: "/compress",
      description: "Persist a context summary for this session.",
      category: "Commands",
    },
    {
      id: "model",
      kind: "command",
      title: "/model",
      command: "/model",
      description: "Select or add a model profile.",
      category: "Commands",
    },
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
      id: "resume",
      kind: "command",
      title: "/resume",
      command: "/resume",
      description: "Resume a recent session by ID.",
      category: "Commands",
    },
    {
      id: "run",
      kind: "command",
      title: "/run resume [id]",
      command: "/run resume",
      description: "Recover the last failed or interrupted run.",
      category: "Commands",
    },
    {
      id: "token",
      kind: "command",
      title: "/token",
      command: "/token",
      description: "Local token usage dashboard.",
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
      id: "skill",
      kind: "command",
      title: "/skill",
      command: "/skill",
      description: "Inspect or run a SKILL.md skill.",
      category: "Commands",
    },
    {
      id: "mcp",
      kind: "command",
      title: "/mcp",
      command: "/mcp",
      description: "Inspect MCP servers and tools.",
      category: "Commands",
    },
    {
      id: "clear",
      kind: "command",
      title: "/clear",
      command: "/clear",
      description: "Delete current session.",
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
  ];

  return commands;
}

export function filterSlash(items: SlashItem[], input: string): SlashItem[] {
  if (!input.startsWith("/")) return [];

  const query = input.slice(1).trim().toLowerCase();
  if (!query) return items;
  return items.filter((item) => `${item.command} ${item.title} ${item.description}`.toLowerCase().includes(query));
}

export function parseSkill(raw: string, skills: SkillSummary[]): { skill: SkillSummary; prompt: string } | null {
  const match = raw.trim().match(/^\/skill\s+(\S+)(?:\s+([\s\S]+))?$/);
  if (!match) return null;

  const skill = skills.find((candidate) => candidate.name === match[1]);
  return skill ? { skill, prompt: match[2]?.trim() || "" } : null;
}

function openConfig(context: CommandContext): void {
  const state = context.getState();
  const draft = createSetupDraft(state.config);
  state.set({
    mode: "setup",
    // Keep /config on the five-field setup flow; advanced routing remains available to the runtime.
    setupFlow: "initial",
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

async function resumeRun(args: string[], context: CommandContext): Promise<void> {
  if (args[0] !== "resume" || args.length > 2) {
    context.getState().set({ statusLine: "Usage: /run resume [run-id]" });
    return;
  }
  await context.bridge.resumeRun(args[1]);
}

const COMMAND_HANDLERS: Record<string, CommandHandler> = {
  // process.exit 由 index.tsx 的 waitUntilExit() 在 Ink 卸载后统一触发
  "/exit": (_args, context) => context.exit(),
  "/new": async (_args, context) => {
    context.bridge.startNewSession();
  },
  "/init": async (args, context) => {
    const state = context.getState();
    if (args.length > 0) {
      state.set({ statusLine: "Usage: /init" });
      return;
    }

    try {
      const result = await context.bridge.initializeProject(context.workingDir ?? process.cwd());
      state.set({
        statusLine: result.created
          ? `Created ${result.path}. Add your project instructions.`
          : `Already exists: ${result.path} (not changed).`,
      });
    } catch (error) {
      state.set({ statusLine: `Project initialization failed: ${errorMessage(error)}` });
    }
  },
  "/config": (_args, context) => openConfig(context),
  "/approve": async (_args, context) => {
    await context.bridge.resolveApproval(true);
  },
  "/deny": async (_args, context) => {
    await context.bridge.resolveApproval(false);
  },
  "/skills": (_args, context) => {
    const state = context.getState();
    state.set({ panel: "skills", statusLine: `${state.skills.length} skill(s).` });
  },
  "/skill": async (args, context) => {
    const state = context.getState();
    if (args.length === 0) {
      state.set({ panel: "skills", statusLine: `${state.skills.length} skill(s).` });
      return;
    }
    const skill = state.skills.find((candidate) => candidate.name === args[0]);
    if (!skill) {
      state.set({ statusLine: `Unknown skill: ${args[0]}` });
      return;
    }
    const prompt = args.slice(1).join(" ").trim();
    if (prompt) {
      await context.bridge.sendMessage(prompt, skill.name);
      return;
    }
    state.set({ pendingSkill: skill, panel: "chat", statusLine: "" });
  },
  "/mcp": async (_args, context) => {
    await context.bridge.refreshMcpServers();
    const state = context.getState();
    state.set({ panel: "mcp", statusLine: `${state.mcpServers.length} MCP server(s).` });
  },
  "/model": async (args, context) => {
    const state = context.getState();
    const requested = args[0];
    if (!requested) {
      await context.bridge.openModelPicker();
      return;
    }
    if (requested === "add") {
      const [model, profileName = model, ...extra] = args.slice(1);
      if (!model || !profileName || extra.length > 0) {
        state.set({ statusLine: "Usage: /model add <model-id> [profile]." });
        return;
      }
      await context.bridge.addModelProfile(model, profileName);
      return;
    }
    await context.bridge.selectModel(requested === "default" || requested === "base" ? null : requested);
  },
  "/compress": async (_args, context) => {
    await context.bridge.compressCurrentSession();
  },
  "/sessions": (_args, context) => {
    const state = context.getState();
    state.set({ panel: "sessions", statusLine: `${state.sessions.length} session(s).` });
  },
  "/token": async (_args, context) => {
    await context.bridge.openTokenStats();
  },
  "/compact": (_args, context) =>
    context.getState().set({ viewMode: "compact", panel: "chat", statusLine: "Compact view." }),
  "/clear": async (_args, context) => {
    await context.bridge.clearCurrentSession();
  },
  "/resume": resumeSession,
  "/run": resumeRun,
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

  state.set({ pendingSkill: skill, panel: "chat", statusLine: "" });
}
