import path from "node:path";
import { Box, render, Text, useApp, useInput } from "ink";
import Spinner from "ink-spinner";
import TextInput from "ink-text-input";
import React, { useCallback, useEffect, useMemo, useRef } from "react";
import { useStore } from "zustand";

import type { PluginManifest, SkillSummary } from "./api.js";
import { NodeBridge } from "./bridge.js";
import { StatusHud } from "./hud.js";
import { type AppStore, createAppStore, type Panel, type SetupDraft } from "./store.js";
import { Transcript, type TranscriptViewMode } from "./transcript.js";

const SHELL_VERSION = "0.2.0";
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
const GHOST_BUDDY = ["  ─╥╥─  ", "▄██████▄", "██ ██ ██", " ██████ ", "╰╯╰╮╭╯╰╯"];

const PROVIDER_PRESETS = {
  openai: { base_url: "https://api.openai.com/v1", model: "gpt-4.1-mini" },
  anthropic: { base_url: "https://api.anthropic.com", model: "claude-sonnet-4-20250514" },
} as const;

const SETUP_FIELDS = ["provider", "base_url", "model", "api_key", "save"] as const;
type SetupField = (typeof SETUP_FIELDS)[number];

// ── Globals ────────────────────────────────────────────────

const store = createAppStore();
const bridge = new NodeBridge(store);
function useS<T>(sel: (s: AppStore) => T): T {
  return useStore(store, sel);
}

// ── Helpers ────────────────────────────────────────────────

function truncate(t: string, max = 80) {
  return t.length <= max ? t : `${t.slice(0, max - 1)}…`;
}
function fieldVal(d: SetupDraft, f: SetupField) {
  return f === "save" ? "save and continue" : d[f];
}

type SlashItem = {
  id: string;
  kind: "command" | "skill";
  title: string;
  command: string;
  description: string;
  category: string;
  skill?: SkillSummary;
};

function buildSlashItems(skills: SkillSummary[], plugins: PluginManifest[]): SlashItem[] {
  const cmds: SlashItem[] = [
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
      id: "plugins",
      kind: "command",
      title: "/plugins",
      command: "/plugins",
      description: "Inspect plugins.",
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
      description: "Compact & remove thinking.",
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
    ...cmds,
    ...skills.map((s) => ({
      id: `sk-${s.name}`,
      kind: "skill" as const,
      title: s.name,
      command: `/${s.name}`,
      description: s.description || "Run skill.",
      category: "Skills",
      skill: s,
    })),
    ...plugins.map((p) => ({
      id: `pl-${p.name}`,
      kind: "command" as const,
      title: p.enabled ? `/plugin disable ${p.name}` : `/plugin enable ${p.name}`,
      command: p.enabled ? `/plugin disable ${p.name}` : `/plugin enable ${p.name}`,
      description: p.enabled ? `Disable ${p.name}.` : `Enable ${p.name}.`,
      category: "Plugins",
    })),
  ];
}

function filterSlash(items: SlashItem[], input: string): SlashItem[] {
  if (!input.startsWith("/")) return [];
  const q = input.slice(1).trim().toLowerCase();
  if (!q) return items.slice(0, 12);
  return items.filter((i) => `${i.command} ${i.title} ${i.description}`.toLowerCase().includes(q)).slice(0, 12);
}

function parseSkill(raw: string, skills: SkillSummary[]) {
  const m = raw.trim().match(/^\/skill\s+(\S+)(?:\s+([\s\S]+))?$/);
  if (!m) return null;
  const skill = skills.find((s) => s.name === m[1]);
  return skill ? { skill, prompt: m[2]?.trim() || "" } : null;
}

// ── Sub-components ─────────────────────────────────────────

function HeroPanel() {
  return (
    <Box flexDirection="column" marginBottom={1} marginTop={1}>
      {SMITH_LOGO.map((line, i) => (
        <Box key={i}>
          <Text color={ACCENT}>{line}</Text>
          <Text>{"   "}</Text>
          <Text color={ACCENT}>{GHOST_BUDDY[i]}</Text>
        </Box>
      ))}
      <Text> </Text>
      <Text color={INFO}>Type `/` for commands · `Ctrl+O` toggle view · `/help` for all</Text>
    </Box>
  );
}

function SetupPanel() {
  const config = useS((s) => s.config);
  const draft = useS((s) => s.setupDraft);
  const idx = useS((s) => s.setupIndex);
  const active = SETUP_FIELDS[idx];
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text color={ACCENT}>SMITH SETUP</Text>
      <Text color={MUTED}>Tab/arrows to move, Enter to apply.</Text>
      <Box flexDirection="column" marginTop={1}>
        {SETUP_FIELDS.map((f) => (
          <Text key={f} color={f === active ? ACCENT : INFO}>
            {f === active ? ">" : " "} {f === "api_key" && config?.has_api_key ? "api key (blank=keep)" : f}:{" "}
            {f === "api_key" ? "•".repeat(fieldVal(draft, f).length) || "-" : fieldVal(draft, f) || "-"}
          </Text>
        ))}
      </Box>
    </Box>
  );
}

function SessionsPanel() {
  const sessions = useS((s) => s.sessions);
  return (
    <Box flexDirection="column">
      <Text color={ACCENT}>Recent sessions</Text>
      {sessions.length === 0 ? (
        <Text color={MUTED}>No sessions.</Text>
      ) : (
        sessions.slice(0, 8).map((s) => (
          <Text key={s.id} color={INFO}>
            {s.id} {truncate(s.title, 40)} {s.message_count} msg
          </Text>
        ))
      )}
    </Box>
  );
}

function PluginsPanel() {
  const plugins = useS((s) => s.plugins);
  return (
    <Box flexDirection="column">
      <Text color={ACCENT}>Plugins</Text>
      {plugins.length === 0 ? (
        <Text color={MUTED}>No plugins.</Text>
      ) : (
        plugins.slice(0, 8).map((p) => (
          <Box key={p.name} flexDirection="column" marginBottom={1}>
            <Text color={p.enabled ? SUCCESS : MUTED}>
              {p.enabled ? "●" : "○"} {p.name}
              {p.version ? `  v${p.version}` : ""}
            </Text>
            <Text color={MUTED}>{p.description || "No description."}</Text>
          </Box>
        ))
      )}
    </Box>
  );
}

function SkillsPanel() {
  const skills = useS((s) => s.skills);
  return (
    <Box flexDirection="column">
      <Text color={ACCENT}>Skills</Text>
      {skills.length === 0 ? (
        <Text color={MUTED}>No skills.</Text>
      ) : (
        skills.slice(0, 12).map((s) => (
          <Box key={s.name} flexDirection="column" marginBottom={1}>
            <Text color={INFO}>
              {s.name} <Text color={MUTED}>[{s.source}]</Text>
            </Text>
            <Text color={MUTED}>{s.description || ""}</Text>
          </Box>
        ))
      )}
    </Box>
  );
}

function SlashMenu({ items, selectedIndex }: { items: SlashItem[]; selectedIndex: number }) {
  let lastCat = "";
  return (
    <Box flexDirection="column" marginTop={1} marginBottom={1}>
      <Text color={ACCENT}>Slash palette</Text>
      {items.length === 0 ? (
        <Text color={MUTED}>No matches.</Text>
      ) : (
        items.map((item, i) => {
          const showCat = item.category !== lastCat;
          lastCat = item.category;
          return (
            <Box key={item.id} flexDirection="column" marginTop={showCat ? 1 : 0}>
              {showCat ? <Text color={MUTED}>{item.category}</Text> : null}
              <Box>
                <Text color={i === selectedIndex ? ACCENT : INFO}>
                  {i === selectedIndex ? ">" : " "} {item.command}
                </Text>
                <Text color={MUTED}>
                  {"  "}
                  {truncate(item.description, 60)}
                </Text>
              </Box>
            </Box>
          );
        })
      )}
    </Box>
  );
}

// ── Main App ───────────────────────────────────────────────

function SmithApp() {
  const { exit } = useApp();
  const g = () => store.getState();
  const suppressRef = useRef<string | null>(null);

  const mode = useS((s) => s.mode);
  const panel = useS((s) => s.panel);
  const busy = useS((s) => s.busy);
  const inputValue = useS((s) => s.inputValue);
  const statusLine = useS((s) => s.statusLine);
  const pendingSkill = useS((s) => s.pendingSkill);
  const viewMode = useS((s) => s.viewMode);
  const transcript = useS((s) => s.transcript);
  const tokenUsage = useS((s) => s.tokenUsage);
  const skills = useS((s) => s.skills);
  const plugins = useS((s) => s.plugins);
  const config = useS((s) => s.config);
  const currentSession = useS((s) => s.currentSession);
  const welcomeNotice = useS((s) => s.welcomeNotice);
  const setupIndex = useS((s) => s.setupIndex);
  const setupDraft = useS((s) => s.setupDraft);
  const slashIndex = useS((s) => s.slashIndex);
  const sessions = useS((s) => s.sessions);

  const activeSetupField = SETUP_FIELDS[setupIndex];
  const slashItems = useMemo(
    () => filterSlash(buildSlashItems(skills, plugins), inputValue),
    [inputValue, skills, plugins],
  );
  const slashMenuOpen = mode === "chat" && inputValue.startsWith("/");

  useEffect(() => {
    void bridge.boot();
  }, []);
  useEffect(() => {
    if (slashIndex >= slashItems.length) g().set({ slashIndex: 0 });
  }, [slashIndex, slashItems.length]);

  const handleInputChange = useCallback(
    (next: string) => {
      const sup = suppressRef.current;
      if (sup) {
        suppressRef.current = null;
        if (next === `${inputValue}${sup}`) return;
      }
      g().set({ inputValue: next });
    },
    [inputValue],
  );

  const handleCommand = useCallback(
    async (raw: string) => {
      const [cmd, ...rest] = raw.trim().split(/\s+/);
      switch (cmd) {
        case "/exit":
        case "/quit":
          exit();
          setTimeout(() => process.exit(0), 100);
          return;
        case "/new":
          g().resetChat();
          return;
        case "/config":
          g().set({
            mode: "setup",
            setupIndex: 0,
            setupDraft: {
              provider: config?.provider || "openai",
              base_url: config?.base_url || "",
              model: config?.model || "",
              api_key: "",
            },
            inputValue: config?.provider || "openai",
            statusLine: "Editing config.",
          });
          return;
        case "/plugins":
          g().set({ panel: "plugins", statusLine: `${plugins.length} plugin(s).` });
          return;
        case "/skills":
          g().set({ panel: "skills", statusLine: `${skills.length} skill(s).` });
          return;
        case "/sessions":
          g().set({ panel: "sessions", statusLine: `${sessions.length} session(s).` });
          return;
        case "/compact": {
          const before = g().transcript.reduce((n, e) => n + (e.kind === "turn" ? e.blocks.length : 0), 0);
          g().set({
            viewMode: "compact",
            panel: "chat",
            transcript: g().transcript.map((e) =>
              e.kind === "turn" ? { ...e, blocks: e.blocks.filter((b) => b.type !== "thinking") } : e,
            ),
          });
          const after = g().transcript.reduce((n, e) => n + (e.kind === "turn" ? e.blocks.length : 0), 0);
          g().set({ statusLine: `Compacted: removed ${before - after} thinking block(s).` });
          return;
        }
        case "/transcript":
          g().set({ viewMode: "transcript", panel: "chat", statusLine: "Transcript view." });
          return;
        case "/clear":
          g().set({
            transcript: [],
            currentSession: null,
            tokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
            panel: "chat",
            statusLine: "Conversation cleared. Next message starts a fresh session.",
          });
          return;
        case "/plugin": {
          const [action, name] = rest;
          if (!action || !name) {
            g().set({ statusLine: "Usage: /plugin <enable|disable> <name>" });
            return;
          }
          try {
            await bridge.togglePlugin(name, action === "enable");
          } catch (e: any) {
            g().set({ statusLine: `Plugin error: ${e.message}` });
          }
          return;
        }
        case "/resume": {
          const target = rest[0];
          if (!target) {
            g().set({ statusLine: "Usage: /resume <session-id>" });
            return;
          }
          const sess = sessions.find((ss) => ss.id.startsWith(target));
          if (!sess) {
            g().set({ statusLine: `Not found: ${target}` });
            return;
          }
          await bridge.resumeSession(sess);
          return;
        }
        case "/home":
          g().set({ panel: "welcome" });
          return;
        case "/help":
          g().pushSystemLine(
            [
              "- `/new` — fresh session",
              "- `/config` — edit LLM config",
              "- `/sessions` — recent sessions",
              "- `/skills` — inspect skills",
              "- `/plugins` — inspect plugins",
              "- `/resume <id>` — resume session",
              "- `/compact` / `/transcript` — switch view",
              "- `/plugin <enable|disable> <name>`",
              "- `/home` — welcome · `/exit` — quit",
            ].join("\n"),
          );
          g().set({ panel: "chat", statusLine: "Help." });
          return;
        default: {
          const skillName = cmd?.slice(1);
          const matched = skills.find((s) => s.name === skillName);
          if (matched) {
            const prompt = rest.join(" ").trim();
            if (prompt) {
              await bridge.sendMessage(prompt, matched.name);
            } else {
              g().set({ pendingSkill: matched, panel: "chat", statusLine: `Skill ${matched.name} armed.` });
            }
            return;
          }
          g().set({ statusLine: `Unknown: ${cmd}` });
        }
      }
    },
    [config, exit, plugins.length, sessions, skills],
  );

  const handleChatSubmit = useCallback(
    async (value: string) => {
      const trimmed = value.trim();
      if (!trimmed || busy) return;
      g().pushHistory(trimmed);
      const explicitSkill = parseSkill(trimmed, skills);
      g().set({ inputValue: "" });

      if (explicitSkill && !explicitSkill.prompt) {
        g().set({
          pendingSkill: explicitSkill.skill,
          panel: "chat",
          statusLine: `Skill ${explicitSkill.skill.name} armed.`,
        });
        return;
      }
      if (trimmed.startsWith("/") && !explicitSkill) {
        const sel = slashItems[slashIndex];
        if (slashMenuOpen && sel && trimmed.split(/\s+/).length === 1 && trimmed !== sel.command) {
          if (sel.kind === "skill" && sel.skill)
            g().set({
              pendingSkill: sel.skill,
              inputValue: "",
              panel: "chat",
              statusLine: `Skill ${sel.skill.name} armed.`,
            });
          else g().set({ inputValue: sel.command, statusLine: `Ready: ${sel.command}` });
          return;
        }
        await handleCommand(trimmed);
        return;
      }

      const activeSkill = explicitSkill?.skill ?? pendingSkill;
      const prompt = explicitSkill?.prompt || trimmed;
      if (activeSkill) g().set({ pendingSkill: null });
      await bridge.sendMessage(prompt, activeSkill?.name);
    },
    [busy, handleCommand, pendingSkill, skills, slashIndex, slashItems, slashMenuOpen],
  );

  const handleSetupSubmit = useCallback(
    async (value: string) => {
      if (activeSetupField === "save") {
        const d = g().setupDraft;
        if (!d.base_url.trim() || !d.model.trim()) {
          g().set({ statusLine: "Base URL and model required." });
          return;
        }
        if (!d.api_key.trim() && !config?.has_api_key) {
          g().set({ statusLine: "API key required." });
          return;
        }
        await bridge.saveConfig({
          provider: d.provider,
          api_key: d.api_key.trim() || undefined,
          base_url: d.base_url.trim(),
          model: d.model.trim(),
        });
        return;
      }
      const draft = { ...g().setupDraft };
      if (activeSetupField === "provider") {
        const p = value.trim().toLowerCase();
        if (!(p in PROVIDER_PRESETS)) {
          g().set({ statusLine: "Must be openai or anthropic." });
          return;
        }
        const preset = PROVIDER_PRESETS[p as keyof typeof PROVIDER_PRESETS];
        Object.assign(draft, { provider: p, base_url: preset.base_url, model: preset.model });
      } else {
        (draft as any)[activeSetupField] = value;
      }
      const nextIdx = Math.min(setupIndex + 1, SETUP_FIELDS.length - 1);
      const nextField = SETUP_FIELDS[nextIdx];
      g().set({
        setupDraft: draft,
        setupIndex: nextIdx,
        inputValue: nextField === "save" ? "" : fieldVal(draft, nextField),
      });
    },
    [activeSetupField, config?.has_api_key, setupIndex],
  );

  useInput((input, key) => {
    if (key.ctrl && input === "c") {
      exit();
      return;
    }
    if (mode === "setup") {
      if (key.tab || key.downArrow) {
        const draft = { ...g().setupDraft };
        if (activeSetupField !== "save") (draft as any)[activeSetupField] = inputValue;
        const ni = (setupIndex + 1) % SETUP_FIELDS.length;
        const nf = SETUP_FIELDS[ni];
        g().set({ setupDraft: draft, setupIndex: ni, inputValue: nf === "save" ? "" : fieldVal(draft, nf) });
        return;
      }
      if (key.upArrow) {
        const draft = { ...g().setupDraft };
        if (activeSetupField !== "save") (draft as any)[activeSetupField] = inputValue;
        const ni = (setupIndex - 1 + SETUP_FIELDS.length) % SETUP_FIELDS.length;
        const nf = SETUP_FIELDS[ni];
        g().set({ setupDraft: draft, setupIndex: ni, inputValue: nf === "save" ? "" : fieldVal(draft, nf) });
        return;
      }
      if (key.escape && config?.configured)
        g().set({ mode: "chat", panel: "welcome", inputValue: "", statusLine: "Back." });
      return;
    }
    if (key.ctrl && input === "o") {
      suppressRef.current = input;
      const nv = viewMode === "compact" ? "transcript" : "compact";
      g().set({ viewMode: nv, statusLine: `${nv} view.` });
      queueMicrotask(() => {
        const v = g().inputValue;
        if (v.endsWith(input)) g().set({ inputValue: v.slice(0, -input.length) });
      });
      return;
    }
    if (slashMenuOpen && slashItems.length > 0) {
      if (key.tab) {
        const sel = slashItems[slashIndex];
        if (sel) g().set({ inputValue: sel.command });
        return;
      }
      if (key.downArrow) {
        g().set({ slashIndex: (slashIndex + 1) % slashItems.length });
        return;
      }
      if (key.upArrow) {
        g().set({ slashIndex: (slashIndex - 1 + slashItems.length) % slashItems.length });
        return;
      }
    }
    if (key.escape) {
      if (busy) {
        bridge.cancelRequest();
        return;
      }
      if (slashMenuOpen) {
        g().set({ inputValue: "", slashIndex: 0 });
        return;
      }
      if (pendingSkill) {
        g().set({ pendingSkill: null, statusLine: "Cleared." });
        return;
      }
    }
    if (!slashMenuOpen && (key.upArrow || key.downArrow)) {
      const hist = g().inputHistory;
      if (hist.length > 0) {
        const cur = g().historyIndex;
        if (key.upArrow) {
          const next = cur === -1 ? hist.length - 1 : Math.max(0, cur - 1);
          g().set({ historyIndex: next, inputValue: hist[next] || "" });
        } else {
          const next = cur === -1 ? -1 : cur + 1;
          if (next >= hist.length) {
            g().set({ historyIndex: -1, inputValue: "" });
          } else {
            g().set({ historyIndex: next, inputValue: hist[next] || "" });
          }
        }
        return;
      }
    }
    if (key.tab && !slashMenuOpen) {
      const panels: Panel[] = ["welcome", "sessions", "skills", "plugins", "chat"];
      const i = panels.indexOf(panel);
      g().set({ panel: panels[(i + 1) % panels.length] });
    }
  });

  const visibleTranscript = panel === "welcome" ? [] : transcript;
  const placeholder =
    mode === "setup"
      ? activeSetupField === "save"
        ? "Enter to save"
        : `Edit ${activeSetupField}`
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
        {mode === "boot" ? (
          <Box>
            <Spinner type="dots" />
            <Text color={MUTED}> Booting…</Text>
          </Box>
        ) : mode === "setup" ? (
          <>
            <HeroPanel />
            <SetupPanel />
          </>
        ) : (
          <>
            <HeroPanel />
            {welcomeNotice ? (
              <Text color={welcomeNotice.tone === "error" ? "#e06c75" : MUTED}>{welcomeNotice.text}</Text>
            ) : null}
            {panel === "plugins" && <PluginsPanel />}
            {panel === "skills" && <SkillsPanel />}
            {panel === "sessions" && <SessionsPanel />}
            {visibleTranscript.length > 0 && <Transcript entries={visibleTranscript} viewMode={viewMode} />}
          </>
        )}
      </Box>
      <Box flexDirection="column" paddingX={2}>
        {mode !== "boot" && (
          <>
            <Text color={busy ? WARNING : MUTED}>{statusLine}</Text>
            {pendingSkill ? (
              <Box marginBottom={1}>
                <Text color={ACCENT}>Skill </Text>
                <Text color={ACCENT} bold>
                  {pendingSkill.name}
                </Text>
                <Text color={MUTED}> armed — Esc to clear</Text>
              </Box>
            ) : null}
            <Box borderStyle="round" borderColor={busy ? ACCENT : BORDER} paddingX={1}>
              <Text color={ACCENT}>{"❯ "}</Text>
              <TextInput
                value={inputValue}
                placeholder={placeholder}
                mask={mode === "setup" && activeSetupField === "api_key" ? "•" : undefined}
                onChange={handleInputChange}
                onSubmit={
                  mode === "setup"
                    ? (v) => {
                        void handleSetupSubmit(v);
                      }
                    : (v) => {
                        void handleChatSubmit(v);
                      }
                }
              />
            </Box>
            {slashMenuOpen ? <SlashMenu items={slashItems} selectedIndex={slashIndex} /> : null}
            <StatusHud
              model={config?.model || "-"}
              projectName={path.basename(process.cwd())}
              cwd={process.cwd()}
              sessionId={currentSession?.id}
              transcript={transcript}
              viewMode={viewMode}
              tokenUsage={tokenUsage}
            />
          </>
        )}
      </Box>
    </Box>
  );
}

render(<SmithApp />);
