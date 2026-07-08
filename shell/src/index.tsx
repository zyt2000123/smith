import path from "node:path";
import React, {useCallback, useEffect, useMemo, useRef, useState} from "react";
import {Box, render, Text, useApp, useInput} from "ink";
import TextInput from "ink-text-input";

import {
  createSession,
  disablePlugin,
  enablePlugin,
  ensureSmithAgent,
  getLlmConfig,
  listPlugins,
  listSkills,
  listSessions,
  setLlmConfig,
  streamMessage,
  type Employee,
  type LlmConfig,
  type PluginManifest,
  type Session,
  type SkillSummary,
} from "./api.js";
import {ensureLocalServer} from "./dev-server.js";
import {
  applyStreamEvent,
  closeLatestTurn,
  createSystemEntry,
  createTurnEntry,
  Transcript,
  type TranscriptEntry,
  type TranscriptViewMode,
} from "./transcript.js";

const SHELL_VERSION = "0.1.0";
const ACCENT = "#ff4d94";
const MUTED = "#8b8b91";
const BORDER = "#5c5c63";
const SUCCESS = "#93f77b";
const WARNING = "#ffd166";
const INFO = "#e9e9ea";

const SMITH_LOGO = [
  "███████╗███╗   ███╗██╗████████╗██╗  ██╗",
  "██╔════╝████╗ ████║██║╚══██╔══╝██║  ██║",
  "███████╗██╔████╔██║██║   ██║   ███████║",
  "╚════██║██║╚██╔╝██║██║   ██║   ██╔══██║",
  "███████║██║ ╚═╝ ██║██║   ██║   ██║  ██║",
];

const GHOST_BUDDY = [
  "  ─╥╥─  ",
  "▄██████▄",
  "██ ██ ██",
  " ██████ ",
  "╰╯╰╮╭╯╰╯",
];

const PROVIDER_PRESETS = {
  openai: {
    label: "OpenAI",
    base_url: "https://api.openai.com/v1",
    model: "gpt-4.1-mini",
  },
  anthropic: {
    label: "Anthropic",
    base_url: "https://api.anthropic.com",
    model: "claude-sonnet-4-20250514",
  },
} as const;

const SETUP_FIELDS = [
  "provider",
  "base_url",
  "model",
  "api_key",
  "save",
] as const;

type SetupField = (typeof SETUP_FIELDS)[number];
type Panel = "welcome" | "chat" | "sessions" | "plugins" | "skills";
type Mode = "boot" | "setup" | "chat";
type SlashItem = {
  id: string;
  kind: "command" | "skill";
  title: string;
  command: string;
  description: string;
  category: "Commands" | "Skills" | "Plugins";
  skill?: SkillSummary;
};

type SetupDraft = {
  provider: string;
  base_url: string;
  model: string;
  api_key: string;
};

type WelcomeNotice = {
  text: string;
  tone: "info" | "error";
};

function truncate(text: string, max = 80): string {
  if (text.length <= max) {
    return text;
  }
  return `${text.slice(0, max - 1)}…`;
}

function buildSetupDraft(config: LlmConfig | null): SetupDraft {
  const provider = config?.provider && config.provider in PROVIDER_PRESETS
    ? config.provider
    : "openai";
  const preset = PROVIDER_PRESETS[provider as keyof typeof PROVIDER_PRESETS];

  return {
    provider,
    base_url: config?.base_url || preset.base_url,
    model: config?.model || preset.model,
    api_key: "",
  };
}

function setupFieldValue(draft: SetupDraft, field: SetupField): string {
  if (field === "save") {
    return "save and continue";
  }
  return draft[field];
}

function formatSetupLabel(field: SetupField, config: LlmConfig | null): string {
  switch (field) {
    case "provider":
      return "provider";
    case "base_url":
      return "base url";
    case "model":
      return "model";
    case "api_key":
      return config?.has_api_key ? "api key (leave blank to keep current)" : "api key";
    case "save":
      return "action";
  }
}

function pickSessionTitle(message: string): string {
  const firstLine = message.trim().split(/\n+/)[0] ?? "Smith Terminal Session";
  return truncate(firstLine || "Smith Terminal Session", 40);
}

function buildSlashItems(
  skills: SkillSummary[],
  plugins: PluginManifest[],
): SlashItem[] {
  const commandItems: SlashItem[] = [
    {
      id: "cmd-help",
      kind: "command",
      title: "/help",
      command: "/help",
      description: "Show available shell commands.",
      category: "Commands",
    },
    {
      id: "cmd-new",
      kind: "command",
      title: "/new",
      command: "/new",
      description: "Start a fresh chat session.",
      category: "Commands",
    },
    {
      id: "cmd-config",
      kind: "command",
      title: "/config",
      command: "/config",
      description: "Edit provider, base URL, API key, and model.",
      category: "Commands",
    },
    {
      id: "cmd-sessions",
      kind: "command",
      title: "/sessions",
      command: "/sessions",
      description: "Show recent sessions.",
      category: "Commands",
    },
    {
      id: "cmd-skills",
      kind: "command",
      title: "/skills",
      command: "/skills",
      description: "Inspect available built-in and employee skills.",
      category: "Commands",
    },
    {
      id: "cmd-plugins",
      kind: "command",
      title: "/plugins",
      command: "/plugins",
      description: "Inspect installed plugins and their status.",
      category: "Commands",
    },
    {
      id: "cmd-compact",
      kind: "command",
      title: "/compact",
      command: "/compact",
      description: "Switch transcript to the compact view.",
      category: "Commands",
    },
    {
      id: "cmd-transcript",
      kind: "command",
      title: "/transcript",
      command: "/transcript",
      description: "Switch transcript to the verbose transcript view.",
      category: "Commands",
    },
  ];

  const skillItems = skills.map((skill) => ({
    id: `skill-${skill.name}`,
    kind: "skill" as const,
    title: skill.name,
    command: `/skill ${skill.name}`,
    description: skill.description || "Run the selected skill on the next turn.",
    category: "Skills" as const,
    skill,
  }));

  const pluginItems = plugins.map((plugin) => ({
    id: `plugin-${plugin.name}`,
    kind: "command" as const,
    title: plugin.enabled ? `/plugin disable ${plugin.name}` : `/plugin enable ${plugin.name}`,
    command: plugin.enabled ? `/plugin disable ${plugin.name}` : `/plugin enable ${plugin.name}`,
    description: plugin.enabled
      ? `Disable plugin ${plugin.name}.`
      : `Enable plugin ${plugin.name}.`,
    category: "Plugins" as const,
  }));

  return [...commandItems, ...skillItems, ...pluginItems];
}

function filterSlashItems(items: SlashItem[], inputValue: string): SlashItem[] {
  if (!inputValue.startsWith("/")) {
    return [];
  }

  const query = inputValue.slice(1).trim().toLowerCase();
  if (!query) {
    return items.slice(0, 12);
  }

  return items
    .map((item) => {
      const title = item.title.toLowerCase();
      const command = item.command.toLowerCase();
      const description = item.description.toLowerCase();

      let score = 99;
      if (title.startsWith(query)) {
        score = 0;
      } else if (command.startsWith(`/${query}`)) {
        score = 1;
      } else if (command.includes(query)) {
        score = 2;
      } else if (description.includes(query)) {
        score = 3;
      }

      return {item, score};
    })
    .filter(({score}) => score < 99)
    .sort((left, right) => left.score - right.score)
    .map(({item}) => item)
    .filter((item) => {
      const haystack = `${item.command} ${item.title} ${item.description}`.toLowerCase();
      return haystack.includes(query);
    })
    .slice(0, 12);
}

function parseSkillCommand(rawCommand: string, skills: SkillSummary[]): {
  skill: SkillSummary;
  prompt: string;
} | null {
  const match = rawCommand.trim().match(/^\/skill\s+([^\s]+)(?:\s+([\s\S]+))?$/);
  if (!match) {
    return null;
  }

  const skillName = match[1] ?? "";
  const skill = skills.find((item) => item.name === skillName);
  if (!skill) {
    return null;
  }

  return {
    skill,
    prompt: match[2]?.trim() || "",
  };
}

function StatusBar(
  {config, workspaceName, currentSession, plugins, panel, mode, viewMode}:
  {
    config: LlmConfig | null;
    workspaceName: string;
    currentSession: Session | null;
    plugins: PluginManifest[];
    panel: Panel;
    mode: Mode;
    viewMode: TranscriptViewMode;
  },
) {
  const provider = truncate(config?.provider || "unconfigured", 12);
  const model = truncate(config?.model || "-", 16);
  const workspace = truncate(workspaceName, 18);
  const sessionLabel = currentSession
    ? truncate(currentSession.id, 10)
    : "new";
  const SEP = <Text color={BORDER}>{" │ "}</Text>;

  return (
    <Box flexDirection="column">
      <Box>
        <Text color="#e5c07b">[{provider}/{model}]</Text>
        {SEP}
        <Text color="#98c379">{workspace}</Text>
        <Text color={MUTED}>{" git:"}</Text>
        <Text color="#c678dd">(main)</Text>
      </Box>
      <Box>
        <Text color={MUTED}>session </Text>
        <Text color={mode === "setup" ? SUCCESS : "#61afef"}>{sessionLabel}</Text>
        {SEP}
        <Text color={MUTED}>plugins </Text>
        <Text color={INFO}>{String(plugins.filter((plugin) => plugin.enabled).length)}/{String(plugins.length)}</Text>
        {SEP}
        <Text color={MUTED}>view </Text>
        <Text color={INFO}>{viewMode}</Text>
        {SEP}
        <Text color={ACCENT}>{panel}</Text>
      </Box>
    </Box>
  );
}

function HeroPanel() {
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Box flexDirection="column" marginTop={1}>
        {SMITH_LOGO.map((line, i) => (
          <Box key={i}>
            <Text color={ACCENT}>{line}</Text>
            <Text>{"   "}</Text>
            <Text color={ACCENT}>{GHOST_BUDDY[i]}</Text>
          </Box>
        ))}
      </Box>
      <Text>{" "}</Text>
      <Text color={INFO}>Tips to get started:</Text>
      <Text color={INFO}>1. Type `/` to open commands, skills, and plugin actions</Text>
      <Text color={INFO}>2. Pick a skill from the slash palette to arm it for the next turn</Text>
      <Text color={INFO}>3. Use `Ctrl+O` or `/transcript` to switch transcript detail level</Text>
      <Text color={INFO}>4. Use /config, /sessions, /skills, and /plugins to inspect local state</Text>
    </Box>
  );
}

function WelcomeNoticePanel({notice}: {notice: WelcomeNotice}) {
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text color={notice.tone === "error" ? "#e06c75" : MUTED}>
        {notice.text}
      </Text>
    </Box>
  );
}

function ShellHeader({notice}: {notice: WelcomeNotice | null}) {
  return (
    <Box flexDirection="column" marginBottom={1}>
      <HeroPanel />
      {notice ? <WelcomeNoticePanel notice={notice} /> : null}
    </Box>
  );
}

function SetupPanel(
  {
    activeField,
    config,
    draft,
  }: {
    activeField: SetupField;
    config: LlmConfig | null;
    draft: SetupDraft;
  },
) {
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text color={ACCENT}>SMITH SETUP</Text>
      <Text color={MUTED}>
        First run setup. Use Tab or Up/Down to move. Enter applies the current field.
      </Text>
      <Text color={MUTED}>
        The shell stores platform-level LLM config in ~/.agent-smith/config.yaml.
      </Text>
      <Box flexDirection="column" marginTop={1}>
        {SETUP_FIELDS.map((field) => {
          const isActive = field === activeField;
          const value = setupFieldValue(draft, field);
          const color = isActive ? ACCENT : INFO;

          return (
            <Text key={field} color={color}>
              {isActive ? ">" : " "} {formatSetupLabel(field, config)}: {value || "-"}
            </Text>
          );
        })}
      </Box>
    </Box>
  );
}

function SessionsPanel({sessions}: {sessions: Session[]}) {
  return (
    <Box flexDirection="column">
      <Text color={ACCENT}>Recent sessions</Text>
      {sessions.length === 0 ? (
        <Text color={MUTED}>No sessions yet.</Text>
      ) : (
        sessions.slice(0, 8).map((session) => (
          <Text key={session.id} color={INFO}>
            {session.id}  {truncate(session.title, 40)}  {session.message_count} msg
          </Text>
        ))
      )}
    </Box>
  );
}

function PluginsPanel({plugins}: {plugins: PluginManifest[]}) {
  return (
    <Box flexDirection="column">
      <Text color={ACCENT}>Plugins</Text>
      {plugins.length === 0 ? (
        <Text color={MUTED}>No plugins discovered yet.</Text>
      ) : (
        plugins.slice(0, 8).map((plugin) => (
          <Box key={plugin.name} flexDirection="column" marginBottom={1}>
            <Text color={plugin.enabled ? SUCCESS : MUTED}>
              {plugin.enabled ? "●" : "○"} {plugin.name}
              {plugin.version ? `  v${plugin.version}` : ""}
              {plugin.trigger_type ? `  (${plugin.trigger_type})` : ""}
            </Text>
            <Text color={MUTED}>
              {plugin.description || "No description."}
              {typeof plugin.skill_count === "number" ? `  skills ${plugin.skill_count}` : ""}
              {plugin.installed ? "  installed" : ""}
            </Text>
          </Box>
        ))
      )}
    </Box>
  );
}

function SkillsPanel({skills}: {skills: SkillSummary[]}) {
  return (
    <Box flexDirection="column">
      <Text color={ACCENT}>Skills</Text>
      {skills.length === 0 ? (
        <Text color={MUTED}>No skills available.</Text>
      ) : (
        skills.slice(0, 12).map((skill) => (
          <Box key={skill.name} flexDirection="column" marginBottom={1}>
            <Text color={INFO}>
              {skill.name}  <Text color={MUTED}>[{skill.source}]</Text>
            </Text>
            <Text color={MUTED}>{skill.description || "No description."}</Text>
          </Box>
        ))
      )}
    </Box>
  );
}

function CapabilityBar(
  {
    plugins,
    skills,
    pendingSkill,
    viewMode,
    permissionState,
  }: {
    plugins: PluginManifest[];
    skills: SkillSummary[];
    pendingSkill: SkillSummary | null;
    viewMode: TranscriptViewMode;
    permissionState: "guarded" | "blocked";
  },
) {
  const SEP = <Text color={BORDER}>{" │ "}</Text>;
  const enabledPlugins = plugins.filter((plugin) => plugin.enabled).length;

  return (
    <Box flexWrap="wrap">
      <Text color={INFO}>skills {skills.length}</Text>
      {SEP}
      <Text color={INFO}>plugins {enabledPlugins}/{plugins.length}</Text>
      {SEP}
      <Text color={permissionState === "blocked" ? WARNING : SUCCESS}>
        permissions {permissionState}
      </Text>
      {SEP}
      <Text color={INFO}>view {viewMode}</Text>
      {pendingSkill ? (
        <>
          {SEP}
          <Text color={ACCENT}>armed {pendingSkill.name}</Text>
        </>
      ) : null}
    </Box>
  );
}

function ArmedSkillBanner({skill}: {skill: SkillSummary}) {
  return (
    <Box marginBottom={1}>
      <Text color={ACCENT}>Using skill </Text>
      <Text color={ACCENT} bold>{skill.name}</Text>
      <Text color={MUTED}> for the next turn. Press Esc to clear.</Text>
    </Box>
  );
}

function SlashMenu({items, selectedIndex}: {items: SlashItem[]; selectedIndex: number}) {
  let lastCategory = "";

  return (
    <Box flexDirection="column" marginTop={1} marginBottom={1}>
      <Text color={ACCENT}>Slash palette</Text>
      {items.length === 0 ? (
        <Text color={MUTED}>No matching commands or skills.</Text>
      ) : items.map((item, index) => {
        const showCategory = item.category !== lastCategory;
        lastCategory = item.category;
        const isSelected = index === selectedIndex;

        return (
          <Box key={item.id} flexDirection="column" marginTop={showCategory ? 1 : 0}>
            {showCategory ? <Text color={MUTED}>{item.category}</Text> : null}
            <Text color={isSelected ? ACCENT : INFO}>
              {isSelected ? ">" : " "} {item.command}
            </Text>
            <Text color={MUTED}>  {truncate(item.description, 88)}</Text>
          </Box>
        );
      })}
    </Box>
  );
}

function SmithApp() {
  const {exit} = useApp();
  const workspaceName = useMemo(() => path.basename(process.cwd()), []);

  const [mode, setMode] = useState<Mode>("boot");
  const [panel, setPanel] = useState<Panel>("welcome");
  const [baseUrl, setBaseUrl] = useState("");
  const [config, setConfig] = useState<LlmConfig | null>(null);
  const [agent, setAgent] = useState<Employee | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [plugins, setPlugins] = useState<PluginManifest[]>([]);
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [viewMode, setViewMode] = useState<TranscriptViewMode>("compact");
  const [pendingSkill, setPendingSkill] = useState<SkillSummary | null>(null);
  const [statusLine, setStatusLine] = useState("Booting Smith…");
  const [inputValue, setInputValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [setupDraft, setSetupDraft] = useState<SetupDraft>(buildSetupDraft(null));
  const [setupIndex, setSetupIndex] = useState(0);
  const [slashIndex, setSlashIndex] = useState(0);
  const suppressedShortcutInputRef = useRef<string | null>(null);
  const [welcomeNotice, setWelcomeNotice] = useState<WelcomeNotice | null>(null);

  const activeSetupField = SETUP_FIELDS[setupIndex];

  const hydrateShell = useCallback(async (
    serverBaseUrl: string,
    nextConfig: LlmConfig,
    bootNotes: string[] = [],
  ) => {
    const smithAgent = await ensureSmithAgent(serverBaseUrl);
    const warnings: string[] = [];
    const [recentSessions, discoveredPlugins, discoveredSkills] = await Promise.all([
      listSessions(serverBaseUrl, smithAgent.id).catch((error: unknown) => {
        const message = error instanceof Error ? error.message : String(error);
        warnings.push(`Recent sessions are unavailable right now: ${message}`);
        return [];
      }),
      listPlugins(serverBaseUrl),
      listSkills(serverBaseUrl, smithAgent.id).catch((error: unknown) => {
        const message = error instanceof Error ? error.message : String(error);
        warnings.push(`Skills could not be loaded, so slash skill selection is temporarily disabled: ${message}`);
        return [];
      }),
    ]);

    setAgent(smithAgent);
    setSessions(recentSessions);
    setPlugins(discoveredPlugins);
    setSkills(discoveredSkills);
    setConfig(nextConfig);
    setMode("chat");
    setPanel("welcome");
    setTranscript([]);
    setCurrentSession(null);
    setPendingSkill(null);
    setInputValue("");
    const noticeLines = [...bootNotes, ...warnings];
    setWelcomeNotice(
      noticeLines.length > 0
        ? {
          text: noticeLines.join("\n"),
          tone: warnings.length > 0 ? "error" : "info",
        }
        : null,
    );
    setStatusLine(
      warnings.length > 0
        ? "Ready, with a few startup warnings. Type / for commands and skills."
        : "Ready. Type / for commands and skills.",
    );
  }, []);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const server = await ensureLocalServer();
        if (cancelled) {
          return;
        }

        setBaseUrl(server.baseUrl);
        setStatusLine(
          server.note
            ? server.note
            : server.started
              ? "Local server started."
              : "Connected to local server.",
        );

        const loadedConfig = await getLlmConfig(server.baseUrl);
        if (cancelled) {
          return;
        }

        setConfig(loadedConfig);
        if (!loadedConfig.configured) {
          const draft = buildSetupDraft(loadedConfig);
          setSetupDraft(draft);
          setSetupIndex(0);
          setInputValue(draft.provider);
          setMode("setup");
          setWelcomeNotice(null);
          setStatusLine("Run the initial setup to wake Smith up.");
          return;
        }

        await hydrateShell(
          server.baseUrl,
          loadedConfig,
          server.note ? [server.note] : [],
        );
      } catch (error) {
        if (cancelled) {
          return;
        }

        const message = error instanceof Error ? error.message : String(error);
        setMode("chat");
        setPanel("welcome");
        setStatusLine(`Boot failed: ${message}`);
        setTranscript([]);
        setWelcomeNotice({
          text: `Smith could not start cleanly.\n\n${message}`,
          tone: "error",
        });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [hydrateShell]);

  const refreshPlugins = useCallback(async () => {
    if (!baseUrl) {
      return;
    }
    setPlugins(await listPlugins(baseUrl));
  }, [baseUrl]);

  const refreshSkills = useCallback(async () => {
    if (!baseUrl || !agent) {
      return;
    }
    setSkills(await listSkills(baseUrl, agent.id));
  }, [agent, baseUrl]);

  const slashItems = useMemo(
    () => filterSlashItems(buildSlashItems(skills, plugins), inputValue),
    [inputValue, plugins, skills],
  );
  const slashMenuOpen = mode === "chat" && inputValue.startsWith("/");
  const selectedSlashItem = slashItems[slashIndex] ?? null;

  useEffect(() => {
    if (slashIndex >= slashItems.length) {
      setSlashIndex(0);
    }
  }, [slashIndex, slashItems.length]);

  const permissionState = useMemo<"guarded" | "blocked">(() => {
    for (let entryIndex = transcript.length - 1; entryIndex >= 0; entryIndex -= 1) {
      const entry = transcript[entryIndex];
      if (!entry || entry.kind !== "turn") {
        continue;
      }
      for (let blockIndex = entry.blocks.length - 1; blockIndex >= 0; blockIndex -= 1) {
        const block = entry.blocks[blockIndex];
        if (block?.type === "tool" && block.state === "blocked") {
          return "blocked";
        }
      }
    }
    return "guarded";
  }, [transcript]);

  const armSkill = useCallback((skill: SkillSummary) => {
    setPendingSkill(skill);
    setInputValue("");
    setPanel("chat");
    setStatusLine(`Skill ${skill.name} armed for the next turn.`);
  }, []);

  const clearPendingSkill = useCallback((message?: string) => {
    setPendingSkill(null);
    if (message) {
      setStatusLine(message);
    }
  }, []);

  const handleInputChange = useCallback((nextValue: string) => {
    const suppressed = suppressedShortcutInputRef.current;
    if (suppressed) {
      suppressedShortcutInputRef.current = null;
      if (nextValue === `${inputValue}${suppressed}`) {
        return;
      }
    }

    setInputValue(nextValue);
  }, [inputValue]);

  const applySlashSelection = useCallback((item: SlashItem | null) => {
    if (!item) {
      return;
    }

    if (item.kind === "skill" && item.skill) {
      armSkill(item.skill);
      return;
    }

    setInputValue(item.command);
    setStatusLine(`Command ready: ${item.command}`);
  }, [armSkill]);

  const commitSetupInput = useCallback(
    (field: SetupField, rawValue: string): SetupDraft => {
      const trimmed = rawValue.trim();
      let nextDraft = setupDraft;

      if (field === "provider") {
        const provider = trimmed.toLowerCase();
        if (!(provider in PROVIDER_PRESETS)) {
          setStatusLine("Provider must be `openai` or `anthropic`.");
          return nextDraft;
        }

        const preset = PROVIDER_PRESETS[provider as keyof typeof PROVIDER_PRESETS];
        nextDraft = {
          ...setupDraft,
          provider,
          base_url: preset.base_url,
          model: preset.model,
        };
      } else if (field !== "save") {
        nextDraft = {
          ...setupDraft,
          [field]: rawValue,
        };
      }

      setSetupDraft(nextDraft);
      return nextDraft;
    },
    [setupDraft],
  );

  const focusSetupField = useCallback(
    (nextIndex: number) => {
      const bounded = (nextIndex + SETUP_FIELDS.length) % SETUP_FIELDS.length;
      const nextField = SETUP_FIELDS[bounded];
      setSetupIndex(bounded);
      setInputValue(nextField === "save" ? "" : setupFieldValue(setupDraft, nextField));
    },
    [setupDraft],
  );

  const saveSetup = useCallback(async () => {
    const draft = commitSetupInput(activeSetupField, inputValue);
    if (!draft.base_url.trim() || !draft.model.trim()) {
      setStatusLine("Base URL and model are required.");
      return;
    }
    if (!draft.api_key.trim() && !config?.has_api_key) {
      setStatusLine("API key is required on first setup.");
      return;
    }
    if (!baseUrl) {
      setStatusLine("Server base URL is not ready yet.");
      return;
    }

    setBusy(true);
    setStatusLine("Saving configuration…");

    try {
      const saved = await setLlmConfig(baseUrl, {
        provider: draft.provider,
        api_key: draft.api_key.trim() || undefined,
        base_url: draft.base_url.trim(),
        model: draft.model.trim(),
      });
      await hydrateShell(baseUrl, saved);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setStatusLine(`Save failed: ${message}`);
    } finally {
      setBusy(false);
    }
  }, [
    activeSetupField,
    baseUrl,
    commitSetupInput,
    config?.has_api_key,
    hydrateShell,
    inputValue,
  ]);

  const pushSystemLine = useCallback((text: string) => {
    setTranscript((current) => [
      ...current,
      createSystemEntry(text),
    ]);
  }, []);

  const handleCommand = useCallback(async (rawCommand: string) => {
    const [command, ...rest] = rawCommand.trim().split(/\s+/);

    switch (command) {
      case "/exit":
      case "/quit":
        exit();
        return;
      case "/new":
        setCurrentSession(null);
        setTranscript([]);
        setPendingSkill(null);
        setWelcomeNotice(null);
        setPanel("welcome");
        setStatusLine("Fresh shell ready.");
        return;
      case "/config": {
        const draft = buildSetupDraft(config);
        setSetupDraft(draft);
        setSetupIndex(0);
        setInputValue(draft.provider);
        setMode("setup");
        setStatusLine("Editing configuration. Leave API key blank to keep the current one.");
        return;
      }
      case "/plugins":
        setPanel("plugins");
        setStatusLine(`Showing ${plugins.length} plugin(s).`);
        return;
      case "/skills":
        setPanel("skills");
        setStatusLine(`Showing ${skills.length} skill(s).`);
        return;
      case "/sessions":
        setPanel("sessions");
        setStatusLine(`Showing ${sessions.length} recent session(s).`);
        return;
      case "/compact":
        setViewMode("compact");
        setPanel("chat");
        setStatusLine("Switched to compact view.");
        return;
      case "/transcript":
        setViewMode("transcript");
        setPanel("chat");
        setStatusLine("Switched to transcript view.");
        return;
      case "/plugin": {
        if (!baseUrl) {
          setStatusLine("Shell is not ready yet.");
          return;
        }

        const action = rest[0];
        const pluginName = rest[1];
        if (!action || !pluginName) {
          setStatusLine("Usage: /plugin <enable|disable> <name>");
          return;
        }

        try {
          if (action === "enable") {
            await enablePlugin(baseUrl, pluginName);
            await refreshPlugins();
            setPanel("plugins");
            setStatusLine(`Enabled plugin ${pluginName}.`);
            return;
          }

          if (action === "disable") {
            await disablePlugin(baseUrl, pluginName);
            await refreshPlugins();
            setPanel("plugins");
            setStatusLine(`Disabled plugin ${pluginName}.`);
            return;
          }
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          setStatusLine(`Plugin command failed: ${message}`);
          return;
        }

        setStatusLine("Usage: /plugin <enable|disable> <name>");
        return;
      }
      case "/home":
        setPanel("welcome");
        setStatusLine("Back on the welcome view.");
        return;
      case "/skill":
        setStatusLine("Use /skill <name> <prompt>, or pick a skill from the slash palette.");
        return;
      case "/resume": {
        const target = rest[0];
        if (!target) {
          setStatusLine("Usage: /resume <session-id>");
          return;
        }

        const session = sessions.find((item) => item.id.startsWith(target));
        if (!session) {
          setStatusLine(`Session not found: ${target}`);
          return;
        }

        setCurrentSession(session);
        setTranscript([
          createSystemEntry(`Resumed session ${session.id}. New messages will continue on this thread.`),
        ]);
        setPanel("chat");
        setStatusLine(`Resumed ${session.id}.`);
        return;
      }
      case "/help":
        pushSystemLine(
          [
            "/new      start a fresh session",
            "/config   edit provider / base URL / API key / model",
            "/sessions show recent session list",
            "/skills   inspect available skills",
            "/resume <id> continue a recent session",
            "/plugins  inspect discovered plugins",
            "/plugin <enable|disable> <name>",
            "/compact  switch to compact transcript",
            "/transcript switch to full transcript view",
            "/home     return to the welcome view",
            "/exit     quit Smith",
          ].join("\n"),
        );
        setPanel("chat");
        setStatusLine("Printed command help.");
        return;
      default:
        setStatusLine(`Unknown command: ${command}`);
    }
  }, [
    baseUrl,
    config,
    exit,
    plugins.length,
    pushSystemLine,
    refreshPlugins,
    sessions,
    skills.length,
  ]);

  const handleChatSubmit = useCallback(async (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || busy) {
      return;
    }

    const explicitSkillCommand = parseSkillCommand(trimmed, skills);
    setInputValue("");

    if (explicitSkillCommand && !explicitSkillCommand.prompt) {
      armSkill(explicitSkillCommand.skill);
      return;
    }

    if (
      trimmed.startsWith("/") &&
      slashMenuOpen &&
      selectedSlashItem &&
      !explicitSkillCommand &&
      trimmed.split(/\s+/).length === 1 &&
      trimmed !== selectedSlashItem.command
    ) {
      applySlashSelection(selectedSlashItem);
      return;
    }

    if (trimmed.startsWith("/") && !explicitSkillCommand) {
      await handleCommand(trimmed);
      return;
    }

    if (!baseUrl || !agent) {
      setStatusLine("Shell is not ready yet.");
      return;
    }

    setBusy(true);
    setPanel("chat");
    setStatusLine("Processing…");

    let session = currentSession;
    const activeSkill = explicitSkillCommand?.skill ?? pendingSkill;
    const promptText = explicitSkillCommand?.prompt || trimmed;

    try {
      if (!session) {
        session = await createSession(baseUrl, agent.id, pickSessionTitle(promptText));
        setCurrentSession(session);
      }

      if (!session) {
        throw new Error("Session could not be created.");
      }
      const resolvedSession = session;

      setTranscript((current) => [
        ...current,
        createTurnEntry(promptText),
      ]);

      for await (const event of streamMessage(baseUrl, agent.id, resolvedSession.id, promptText, {
        skillName: activeSkill?.name,
      })) {
        setTranscript((current) => applyStreamEvent(current, event));
        if (event.type === "done") {
          setStatusLine("Ready. Type the next task or /help.");
        }
      }

      setTranscript((current) => closeLatestTurn(current));
      if (activeSkill) {
        clearPendingSkill(`Skill ${activeSkill.name} finished. Ready for the next turn.`);
      }

      const updatedSessions = await listSessions(baseUrl, agent.id);
      setSessions(updatedSessions);
      if (currentSession === null) {
        const matched = updatedSessions.find((item) => item.id === resolvedSession.id);
        if (matched) {
          setCurrentSession(matched);
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setTranscript((current) => closeLatestTurn(current));
      setTranscript((current) => [
        ...current,
        createSystemEntry(`[error] ${message}`, "error"),
      ]);
      setStatusLine(`Request failed: ${message}`);
    } finally {
      setBusy(false);
    }
  }, [
    agent,
    applySlashSelection,
    armSkill,
    baseUrl,
    busy,
    clearPendingSkill,
    currentSession,
    handleCommand,
    pendingSkill,
    selectedSlashItem,
    skills,
    slashMenuOpen,
  ]);

  const handleSetupSubmit = useCallback(async (value: string) => {
    if (activeSetupField === "save") {
      await saveSetup();
      return;
    }

    const nextDraft = commitSetupInput(activeSetupField, value);
    const nextIndex = Math.min(setupIndex + 1, SETUP_FIELDS.length - 1);
    const nextField = SETUP_FIELDS[nextIndex];
    setSetupIndex(nextIndex);
    setInputValue(nextField === "save" ? "" : setupFieldValue(nextDraft, nextField));
    setStatusLine(`Captured ${formatSetupLabel(activeSetupField, config)}.`);
  }, [
    activeSetupField,
    commitSetupInput,
    config,
    saveSetup,
    setupIndex,
  ]);

  useInput((input, key) => {
    if (key.ctrl && input === "c") {
      exit();
      return;
    }

    if (mode === "setup") {
      if (key.tab || key.downArrow) {
        const nextDraft = commitSetupInput(activeSetupField, inputValue);
        const nextIndex = (setupIndex + 1) % SETUP_FIELDS.length;
        const nextField = SETUP_FIELDS[nextIndex];
        setSetupDraft(nextDraft);
        setSetupIndex(nextIndex);
        setInputValue(nextField === "save" ? "" : setupFieldValue(nextDraft, nextField));
        return;
      }

      if (key.upArrow) {
        const nextDraft = commitSetupInput(activeSetupField, inputValue);
        const nextIndex = (setupIndex - 1 + SETUP_FIELDS.length) % SETUP_FIELDS.length;
        const nextField = SETUP_FIELDS[nextIndex];
        setSetupDraft(nextDraft);
        setSetupIndex(nextIndex);
        setInputValue(nextField === "save" ? "" : setupFieldValue(nextDraft, nextField));
        return;
      }

      if (activeSetupField === "provider" && (key.leftArrow || key.rightArrow)) {
        const nextProvider = setupDraft.provider === "openai" ? "anthropic" : "openai";
        const preset = PROVIDER_PRESETS[nextProvider];
        const nextDraft = {
          ...setupDraft,
          provider: nextProvider,
          base_url: preset.base_url,
          model: preset.model,
        };
        setSetupDraft(nextDraft);
        setInputValue(nextProvider);
        return;
      }

      if (key.escape && config?.configured) {
        setMode("chat");
        setPanel("welcome");
        setInputValue("");
        setStatusLine("Returned to shell.");
      }
      return;
    }

    if (key.ctrl && input === "o") {
      suppressedShortcutInputRef.current = input;
      const nextView = viewMode === "compact" ? "transcript" : "compact";
      setViewMode(nextView);
      setStatusLine(`Switched to ${nextView} view.`);
      queueMicrotask(() => {
        setInputValue((current) => (
          current.endsWith(input)
            ? current.slice(0, -input.length)
            : current
        ));
      });
      return;
    }

    if (slashMenuOpen && slashItems.length > 0) {
      if (key.downArrow || key.tab) {
        setSlashIndex((current) => (current + 1) % slashItems.length);
        return;
      }

      if (key.upArrow) {
        setSlashIndex((current) => (current - 1 + slashItems.length) % slashItems.length);
        return;
      }
    }

    if (key.escape && busy) {
      setStatusLine("Cancel is not wired yet. Let the current turn finish.");
      return;
    }

    if (key.escape && slashMenuOpen) {
      setInputValue("");
      setSlashIndex(0);
      setStatusLine("Dismissed the slash palette.");
      return;
    }

    if (key.escape && pendingSkill) {
      clearPendingSkill("Cleared the armed skill.");
      return;
    }

    if (key.tab) {
      const orderedPanels: Panel[] = ["welcome", "sessions", "skills", "plugins", "chat"];
      const currentIndex = orderedPanels.indexOf(panel);
      const nextPanel = orderedPanels[(currentIndex + 1) % orderedPanels.length];
      setPanel(nextPanel);
      setStatusLine(`Switched to ${nextPanel}.`);
    }
  });

  const shellBody = (() => {
    const visibleTranscript = panel === "welcome" ? [] : transcript;

    if (mode === "boot") {
      return <Text color={MUTED}>Booting local server and loading workspace state…</Text>;
    }

    if (mode === "setup") {
      return (
        <SetupPanel
          activeField={activeSetupField}
          config={config}
          draft={setupDraft}
        />
      );
    }

    return (
      <>
        {panel === "plugins" && <PluginsPanel plugins={plugins} />}
        {panel === "skills" && <SkillsPanel skills={skills} />}
        {panel === "sessions" && <SessionsPanel sessions={sessions} />}
        {visibleTranscript.length > 0 && <Transcript entries={visibleTranscript} viewMode={viewMode} />}
      </>
    );
  })();

  const promptPlaceholder = mode === "setup"
    ? activeSetupField === "save"
      ? "Press Enter to save, or Tab to move"
      : `Edit ${formatSetupLabel(activeSetupField, config)}`
    : pendingSkill
      ? `Ask Smith to run ${pendingSkill.name}…`
      : "Tell Smith what to do…";

  return (
    <Box flexDirection="column" paddingY={1}>
      <Box paddingX={2} gap={1} marginBottom={1}>
        <Text color={ACCENT}>Agent-Smith</Text>
        <Text color={MUTED}>v{SHELL_VERSION}</Text>
      </Box>
      <Box flexDirection="column" paddingX={2}>
        {mode !== "boot" ? <ShellHeader notice={welcomeNotice} /> : null}
        {shellBody}
      </Box>
      <Box flexDirection="column" paddingX={2}>
        <CapabilityBar
          plugins={plugins}
          skills={skills}
          pendingSkill={pendingSkill}
          viewMode={viewMode}
          permissionState={permissionState}
        />
        <Text color={busy ? WARNING : MUTED}>
          {busy ? "Processing… let the current turn finish." : statusLine}
        </Text>
        {pendingSkill ? <ArmedSkillBanner skill={pendingSkill} /> : null}
        <Box borderStyle="round" borderColor={busy ? ACCENT : BORDER} paddingX={1}>
          <Text color={ACCENT}>{"❯ "}</Text>
          <TextInput
            value={inputValue}
            placeholder={promptPlaceholder}
            onChange={handleInputChange}
            onSubmit={mode === "setup" ? (value) => {
              void handleSetupSubmit(value);
            } : (value) => {
              void handleChatSubmit(value);
            }}
          />
        </Box>
        {slashMenuOpen ? <SlashMenu items={slashItems} selectedIndex={slashIndex} /> : null}
        <StatusBar
          config={config}
          workspaceName={workspaceName}
          currentSession={currentSession}
          plugins={plugins}
          panel={panel}
          mode={mode}
          viewMode={viewMode}
        />
      </Box>
    </Box>
  );
}

render(<SmithApp />);
