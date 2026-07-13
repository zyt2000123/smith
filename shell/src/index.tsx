import { createRequire } from "node:module";
import path from "node:path";
import { useShikiHighlighter } from "@assistant-ui/react-ink-markdown";
import { Box, render, Static, Text, useApp, useWindowSize } from "ink";
import Spinner from "ink-spinner";
import TextInput from "ink-text-input";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useStore } from "zustand";

import type { SkillSummary } from "./api.js";
import { NodeBridge } from "./bridge.js";
import type { CodeHighlighter } from "./code-block.js";
import { buildSlashItems, filterSlash, parseSkill, runShellCommand, type SlashItem } from "./commands.js";
import { loadHistory, saveHistory } from "./history.js";
import { StatusHud } from "./hud.js";
import { useShellInput } from "./input.js";
import type { QueuedMessage } from "./queue.js";
import {
  buildLlmConfigInput,
  fieldValue,
  hasStoredApiKey,
  isApiKeySetupField,
  nextSetupIndex,
  setProvider,
  setSetupField,
  setupFieldAt,
  setupFieldLabel,
  setupFields,
} from "./setup.js";
import { type AppStore, createAppStore } from "./store.js";
import { ACCENT, BORDER, ERROR, INFO, MUTED } from "./theme.js";
import { TranscriptEntryView } from "./transcript.js";
import { splitTranscript, type TranscriptEntry, type TranscriptViewMode } from "./transcript-state.js";

const SHELL_VERSION = (createRequire(import.meta.url)("../package.json") as { version: string }).version;

const SMITH_LOGO = [
  "███████╗███╗   ███╗██╗████████╗██╗  ██╗",
  "██╔════╝████╗ ████║██║╚══██╔══╝██║  ██║",
  "███████╗██╔████╔██║██║   ██║   ███████║",
  "╚════██║██║╚██╔╝██║██║   ██║   ██╔══██║",
  "███████╗██║ ╚═╝ ██║██║   ██║   ██║  ██║",
];
const GHOST_BUDDY = ["  ─╥╥─  ", "▄██████▄", "██ ██ ██", " ██████ ", "╰╯╰╮╭╯╰╯"];

const store = createAppStore(loadHistory());
const bridge = new NodeBridge(store);
const getState = store.getState;

/** Items rendered once through <Static>: the hero banner plus every completed entry. */
type StaticItem = { kind: "hero"; id: string } | TranscriptEntry;

function useS<T>(selector: (state: AppStore) => T): T {
  return useStore(store, selector);
}

function truncate(text: string, max = 80): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}

function armSkill(skill: SkillSummary): void {
  getState().set({ pendingSkill: skill, panel: "chat", statusLine: `Skill ${skill.name} armed.` });
}

function hasTurnBefore(items: readonly { kind: string }[], index: number): boolean {
  for (let i = 0; i < index; i += 1) {
    if (items[i]?.kind === "turn") return true;
  }
  return false;
}

function HeroPanel() {
  const { columns } = useWindowSize();
  const compact = columns < 60;

  return (
    <Box flexDirection="column" marginBottom={1} paddingTop={1}>
      <Box gap={1} marginBottom={1}>
        <Text color={ACCENT}>Agent-Smith</Text>
        <Text color={MUTED}>v{SHELL_VERSION}</Text>
      </Box>
      {compact ? (
        <Text color={INFO}>Terminal view is compact. Type `/help` for commands.</Text>
      ) : (
        SMITH_LOGO.map((line, index) => (
          <Box key={line}>
            <Text color={ACCENT}>{line}</Text>
            <Text>{"   "}</Text>
            <Text color={ACCENT}>{GHOST_BUDDY[index]}</Text>
          </Box>
        ))
      )}
      <Text> </Text>
      <Text color={INFO}>Type `/` for commands · Ctrl+C/Esc cancels a running task · `/help` for all</Text>
    </Box>
  );
}

function SetupPanel() {
  const config = useS((state) => state.config);
  const draft = useS((state) => state.setupDraft);
  const flow = useS((state) => state.setupFlow);
  const index = useS((state) => state.setupIndex);
  const fields = setupFields(flow);
  const activeField = setupFieldAt(index, flow);

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text color={ACCENT}>{flow === "initial" ? "SMITH SETUP" : "LLM CONFIG"}</Text>
      <Text color={MUTED}>
        {flow === "initial"
          ? "Connect a model to get started."
          : "Tab/arrows to move. Advanced route and timeout fields are optional."}
      </Text>
      <Box flexDirection="column" marginTop={1}>
        {fields.map((field) => (
          <Text key={field} color={field === activeField ? ACCENT : INFO}>
            {field === activeField ? ">" : " "}{" "}
            {isApiKeySetupField(field) && hasStoredApiKey(config, field)
              ? `${setupFieldLabel(field)} (blank=keep)`
              : setupFieldLabel(field)}
            :{" "}
            {isApiKeySetupField(field)
              ? "•".repeat(fieldValue(draft, field).length) || "-"
              : truncate(fieldValue(draft, field), 104) || "-"}
          </Text>
        ))}
      </Box>
    </Box>
  );
}

function SessionsPanel() {
  const sessions = useS((state) => state.sessions);
  return (
    <Box flexDirection="column">
      <Text color={ACCENT}>Recent sessions</Text>
      {sessions.length === 0 ? (
        <Text color={MUTED}>No sessions.</Text>
      ) : (
        sessions.slice(0, 8).map((session) => (
          <Text key={session.id} color={INFO}>
            {session.id} {truncate(session.title, 40)} {session.message_count} msg
          </Text>
        ))
      )}
    </Box>
  );
}

function SkillsPanel() {
  const skills = useS((state) => state.skills);
  return (
    <Box flexDirection="column">
      <Text color={ACCENT}>Skills</Text>
      {skills.length === 0 ? (
        <Text color={MUTED}>No skills.</Text>
      ) : (
        skills.slice(0, 12).map((skill) => (
          <Box key={skill.name} flexDirection="column" marginBottom={1}>
            <Text color={INFO}>
              {skill.name} <Text color={MUTED}>[{skill.source}]</Text>
            </Text>
            <Text color={MUTED}>{skill.description || ""}</Text>
          </Box>
        ))
      )}
    </Box>
  );
}

function SlashMenu({ items, selectedIndex }: { items: SlashItem[]; selectedIndex: number }) {
  let category = "";
  return (
    <Box flexDirection="column" marginBottom={1} marginTop={1}>
      <Text color={ACCENT}>Slash palette</Text>
      {items.length === 0 ? (
        <Text color={MUTED}>No matches.</Text>
      ) : (
        items.map((item, index) => {
          const showCategory = item.category !== category;
          category = item.category;
          return (
            <Box key={item.id} flexDirection="column" marginTop={showCategory ? 1 : 0}>
              {showCategory ? <Text color={MUTED}>{item.category}</Text> : null}
              <Box>
                <Text color={index === selectedIndex ? ACCENT : INFO}>
                  {index === selectedIndex ? ">" : " "} {item.command}
                </Text>
                <Text color={MUTED}>{`  ${truncate(item.description, 60)}`}</Text>
              </Box>
            </Box>
          );
        })
      )}
    </Box>
  );
}

function ShellContent({
  mode,
  panel,
  active,
  hasPriorTurn,
  viewMode,
  welcomeNotice,
  highlighter,
}: Pick<AppStore, "mode" | "panel" | "viewMode" | "welcomeNotice"> & {
  active: TranscriptEntry[];
  hasPriorTurn: boolean;
  highlighter?: CodeHighlighter;
}) {
  if (mode === "boot") {
    return (
      <Box>
        <Spinner type="dots" />
        <Text color={MUTED}> Booting…</Text>
      </Box>
    );
  }

  if (mode === "setup") {
    return <SetupPanel />;
  }

  return (
    <>
      {welcomeNotice ? <Text color={welcomeNotice.tone === "error" ? ERROR : MUTED}>{welcomeNotice.text}</Text> : null}
      {panel === "skills" ? <SkillsPanel /> : null}
      {panel === "sessions" ? <SessionsPanel /> : null}
      {active.map((entry, index) => (
        <TranscriptEntryView
          key={entry.id}
          entry={entry}
          showDivider={entry.kind === "turn" && (hasPriorTurn || hasTurnBefore(active, index))}
          viewMode={viewMode}
          highlighter={highlighter}
        />
      ))}
    </>
  );
}

type ShellFooterProps = {
  mode: AppStore["mode"];
  busy: boolean;
  statusLine: string;
  pendingSkill: SkillSummary | null;
  queuedMessages: QueuedMessage[];
  inputValue: string;
  activeSetupField: ReturnType<typeof setupFieldAt>;
  slashMenuOpen: boolean;
  slashItems: SlashItem[];
  slashIndex: number;
  viewMode: TranscriptViewMode;
  config: AppStore["config"];
  currentSession: AppStore["currentSession"];
  turnTokenUsage: AppStore["turnTokenUsage"];
  tokenUsage: AppStore["tokenUsage"];
  turnCount: number;
  toolActivity: AppStore["toolActivity"];
  onInputChange: (value: string) => void;
  onChatSubmit: (value: string) => void;
  onSetupSubmit: (value: string) => void;
};

function ShellFooter(props: ShellFooterProps) {
  if (props.mode === "boot") return null;

  const placeholder =
    props.mode === "setup"
      ? props.activeSetupField === "save"
        ? "Enter to save"
        : `Edit ${setupFieldLabel(props.activeSetupField)}`
      : props.pendingSkill
        ? `Ask Smith to run ${props.pendingSkill.name}…`
        : "Tell Smith what to do…";

  return (
    <>
      {!props.busy ? <Text color={MUTED}>{props.statusLine}</Text> : null}
      {props.pendingSkill ? (
        <Box marginBottom={1}>
          <Text color={ACCENT}>Skill </Text>
          <Text color={ACCENT} bold>
            {props.pendingSkill.name}
          </Text>
          <Text color={MUTED}> armed — Esc to clear</Text>
        </Box>
      ) : null}
      <QueuePreview items={props.queuedMessages} />
      <Box borderColor={props.busy ? ACCENT : BORDER} borderStyle="round" paddingX={1}>
        <Text color={ACCENT}>{"❯ "}</Text>
        <TextInput
          value={props.inputValue}
          placeholder={placeholder}
          mask={props.mode === "setup" && isApiKeySetupField(props.activeSetupField) ? "•" : undefined}
          onChange={props.onInputChange}
          onSubmit={props.mode === "setup" ? props.onSetupSubmit : props.onChatSubmit}
        />
      </Box>
      {props.slashMenuOpen ? <SlashMenu items={props.slashItems} selectedIndex={props.slashIndex} /> : null}
      <StatusHud
        model={props.config?.model || "-"}
        projectName={path.basename(process.cwd())}
        cwd={process.cwd()}
        sessionId={props.currentSession?.id}
        turnTokenUsage={props.turnTokenUsage}
        tokenUsage={props.tokenUsage}
        toolActivity={props.toolActivity}
        turnCount={props.turnCount}
        viewMode={props.viewMode}
      />
    </>
  );
}

function completeSlashSelection(input: string, slashMenuOpen: boolean, items: SlashItem[], index: number): boolean {
  const selected = items[index];
  if (!slashMenuOpen || !selected || input.split(/\s+/).length !== 1 || input === selected.command) return false;

  if (selected.kind === "skill" && selected.skill) {
    armSkill(selected.skill);
  } else {
    getState().set({ inputValue: selected.command, statusLine: `Ready: ${selected.command}` });
  }
  return true;
}

function QueuePreview({ items }: { items: QueuedMessage[] }) {
  if (items.length === 0) return null;

  return (
    <Box flexDirection="column" marginBottom={1} paddingX={1}>
      <Box>
        <Text color={MUTED}>• </Text>
        <Text color={INFO}>Queued follow-up inputs</Text>
      </Box>
      {items.map((item) => (
        <Box key={item.id}>
          <Text color={MUTED}>{"  ↳ "}</Text>
          <Text color={MUTED}>{truncate(item.text, 120)}</Text>
        </Box>
      ))}
      <Text color={MUTED}>{"    shift + ← edit last queued message"}</Text>
    </Box>
  );
}

function rememberSubmittedInput(input: string): void {
  const state = getState();
  state.pushHistory(input);
  saveHistory(getState().inputHistory);
  state.set({ inputValue: "" });
}

async function submitWhileBusy(
  input: string,
  payload: string,
  skill: SkillSummary | null,
  slashMenuOpen: boolean,
  slashItems: SlashItem[],
  slashIndex: number,
): Promise<void> {
  if (input.startsWith("/")) {
    completeSlashSelection(input, slashMenuOpen, slashItems, slashIndex);
    return;
  }
  if (!bridge.enqueueMessage(payload, skill?.name)) return;

  rememberSubmittedInput(input);
  if (skill) getState().set({ pendingSkill: null });
}

async function submitChat(
  value: string,
  busy: boolean,
  pendingSkill: SkillSummary | null,
  skills: SkillSummary[],
  slashMenuOpen: boolean,
  slashItems: SlashItem[],
  slashIndex: number,
  exit: () => void,
): Promise<void> {
  const input = value.trim();
  if (!input) return;

  const explicitSkill = parseSkill(input, skills);
  const skill = explicitSkill?.skill ?? pendingSkill;
  const payload = explicitSkill?.prompt || input;

  if (busy) {
    await submitWhileBusy(input, payload, skill, slashMenuOpen, slashItems, slashIndex);
    return;
  }

  rememberSubmittedInput(input);
  if (explicitSkill && !explicitSkill.prompt) {
    armSkill(explicitSkill.skill);
    return;
  }
  if (input.startsWith("/") && !explicitSkill) {
    if (completeSlashSelection(input, slashMenuOpen, slashItems, slashIndex)) return;
    await runShellCommand(input, { bridge, exit, getState });
    return;
  }

  if (skill) getState().set({ pendingSkill: null });
  const accepted = await bridge.sendMessage(payload, skill?.name);
  if (!accepted) getState().set({ inputValue: input });
}

async function submitSetup(
  value: string,
  activeField: ReturnType<typeof setupFieldAt>,
  configHasApiKey: boolean,
  setupIndex: number,
  setupFlow: AppStore["setupFlow"],
): Promise<void> {
  const state = getState();
  if (activeField === "save") {
    const draft = state.setupDraft;
    if (!draft.base_url.trim() || !draft.model.trim()) {
      state.set({ statusLine: "Base URL and model required." });
      return;
    }
    if (!draft.api_key.trim() && !configHasApiKey) {
      state.set({ statusLine: "API key required." });
      return;
    }
    try {
      await bridge.saveConfig(buildLlmConfigInput(draft));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      state.set({ statusLine: `Configuration error: ${message}` });
    }
    return;
  }

  const draft =
    activeField === "provider"
      ? setProvider(state.setupDraft, value)
      : setSetupField(state.setupDraft, activeField, value);
  if (!draft) {
    state.set({ statusLine: "Must be openai or anthropic." });
    return;
  }

  const nextIndex = nextSetupIndex(setupIndex, 1, false, setupFlow);
  const nextField = setupFieldAt(nextIndex, setupFlow);
  state.set({
    setupDraft: draft,
    setupIndex: nextIndex,
    inputValue: nextField === "save" ? "" : fieldValue(draft, nextField),
  });
}

function SmithApp() {
  const { exit } = useApp();
  const suppressRef = useRef<string | null>(null);
  const highlighter = useShikiHighlighter({ theme: "github-dark" });

  const mode = useS((state) => state.mode);
  const panel = useS((state) => state.panel);
  const busy = useS((state) => state.busy);
  const inputValue = useS((state) => state.inputValue);
  const statusLine = useS((state) => state.statusLine);
  const pendingSkill = useS((state) => state.pendingSkill);
  const queuedMessages = useS((state) => state.queuedMessages);
  const viewMode = useS((state) => state.viewMode);
  const transcript = useS((state) => state.transcript);
  const transcriptEpoch = useS((state) => state.transcriptEpoch);
  const turnCount = useS((state) => state.turnCount);
  const toolActivity = useS((state) => state.toolActivity);
  const turnTokenUsage = useS((state) => state.turnTokenUsage);
  const tokenUsage = useS((state) => state.tokenUsage);
  const skills = useS((state) => state.skills);
  const config = useS((state) => state.config);
  const currentSession = useS((state) => state.currentSession);
  const welcomeNotice = useS((state) => state.welcomeNotice);
  const setupIndex = useS((state) => state.setupIndex);
  const setupFlow = useS((state) => state.setupFlow);
  const slashIndex = useS((state) => state.slashIndex);

  const activeSetupField = setupFieldAt(setupIndex, setupFlow);
  const slashItems = useMemo(() => filterSlash(buildSlashItems(skills), inputValue), [inputValue, skills]);
  const slashMenuOpen = mode === "chat" && inputValue.startsWith("/");

  const { done, active } = useMemo(() => splitTranscript(transcript), [transcript]);
  const staticItems = useMemo<StaticItem[]>(() => [{ kind: "hero", id: "hero" }, ...done], [done]);
  const hasPriorTurn = useMemo(() => hasTurnBefore(staticItems, staticItems.length), [staticItems]);

  useEffect(() => {
    void bridge.boot();
  }, []);
  useEffect(() => {
    if (slashIndex >= slashItems.length) getState().set({ slashIndex: 0 });
  }, [slashIndex, slashItems.length]);

  const handleInputChange = useCallback(
    (value: string) => {
      const suppressed = suppressRef.current;
      if (suppressed) {
        suppressRef.current = null;
        if (value === `${inputValue}${suppressed}`) return;
      }
      getState().set({ inputValue: value });
    },
    [inputValue],
  );
  const handleChatSubmit = useCallback(
    (value: string) => {
      void submitChat(value, busy, pendingSkill, skills, slashMenuOpen, slashItems, slashIndex, exit);
    },
    [busy, exit, pendingSkill, skills, slashIndex, slashItems, slashMenuOpen],
  );
  const handleSetupSubmit = useCallback(
    (value: string) => {
      void submitSetup(
        value,
        activeSetupField,
        Boolean(config?.has_api_key || config?.routes?.interactive?.has_api_key),
        setupIndex,
        setupFlow,
      );
    },
    [activeSetupField, config?.has_api_key, config?.routes?.interactive?.has_api_key, setupFlow, setupIndex],
  );

  useShellInput({
    mode,
    setupFlow,
    busy,
    viewMode,
    slashMenuOpen,
    slashItems,
    slashIndex,
    panel,
    pendingSkill,
    configConfigured: Boolean(config?.configured),
    exit,
    bridge,
    getState,
    suppressRef,
  });

  return (
    <Box flexDirection="column">
      <Static key={`transcript-${transcriptEpoch}`} items={staticItems}>
        {(item, index) => (
          <Box key={item.id} flexDirection="column" paddingX={2}>
            {item.kind === "hero" ? (
              <HeroPanel />
            ) : (
              <TranscriptEntryView
                entry={item}
                showDivider={hasTurnBefore(staticItems, index)}
                viewMode={viewMode}
                highlighter={highlighter}
              />
            )}
          </Box>
        )}
      </Static>
      <Box flexDirection="column" paddingX={2}>
        <ShellContent
          mode={mode}
          panel={panel}
          active={active}
          hasPriorTurn={hasPriorTurn}
          viewMode={viewMode}
          welcomeNotice={welcomeNotice}
          highlighter={highlighter}
        />
      </Box>
      <Box flexDirection="column" paddingBottom={1} paddingX={2}>
        <ShellFooter
          activeSetupField={activeSetupField}
          busy={busy}
          config={config}
          currentSession={currentSession}
          inputValue={inputValue}
          mode={mode}
          onChatSubmit={handleChatSubmit}
          onInputChange={handleInputChange}
          onSetupSubmit={handleSetupSubmit}
          pendingSkill={pendingSkill}
          queuedMessages={queuedMessages}
          slashIndex={slashIndex}
          slashItems={slashItems}
          slashMenuOpen={slashMenuOpen}
          statusLine={statusLine}
          turnTokenUsage={turnTokenUsage}
          tokenUsage={tokenUsage}
          toolActivity={toolActivity}
          turnCount={turnCount}
          viewMode={viewMode}
        />
      </Box>
    </Box>
  );
}

const app = render(<SmithApp />, { exitOnCtrlC: false });
void app.waitUntilExit().then(
  () => process.exit(0),
  () => process.exit(1),
);
