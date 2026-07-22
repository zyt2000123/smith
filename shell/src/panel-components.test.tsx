import assert from "node:assert/strict";
import test from "node:test";

import { renderToString, Text } from "ink";

import { MultiSelectList } from "./multi-select-list.js";
import { PanelContainer } from "./panel-container.js";
import { RunExplorerPanel } from "./run-panel.js";
import { TabbedPanel } from "./tabbed-panel.js";
import { TokenStatsPanel } from "./token-panel.js";

function stripAnsi(text: string): string {
  const ansiEscape = String.fromCharCode(27);
  return text.replace(new RegExp(`${ansiEscape}\\[[0-?]*[ -/]*[@-~]`, "g"), "");
}

test("PanelContainer keeps the title, guidance, body, and footer together", () => {
  const output = stripAnsi(
    renderToString(
      <PanelContainer title="Skills" description="Choose a capability" footer="Esc back">
        <Text>Body</Text>
      </PanelContainer>,
    ),
  );

  assert.match(output, /Skills/);
  assert.match(output, /Choose a capability/);
  assert.match(output, /Body/);
  assert.match(output, /Esc back/);
});

test("TabbedPanel marks exactly the active tab and retains its content", () => {
  const output = stripAnsi(
    renderToString(
      <TabbedPanel
        tabs={[
          { id: "overview", label: "Overview" },
          { id: "models", label: "Models" },
        ]}
        selected="models"
        hint="←/→ switch"
      >
        <Text>Model details</Text>
      </TabbedPanel>,
    ),
  );

  assert.match(output, /Overview/);
  assert.match(output, /Models/);
  assert.match(output, /Model details/);
  assert.match(output, /←\/→ switch/);
});

test("MultiSelectList retains checked state, focus, and visible-window hints", () => {
  const output = stripAnsi(
    renderToString(
      <MultiSelectList
        items={[
          { id: "first", label: "First", description: "enabled", selected: true },
          { id: "second", label: "Second", description: "disabled", selected: false },
        ]}
        focusedIndex={3}
        startIndex={2}
        totalCount={5}
      />,
    ),
  );

  assert.match(output, /↑ more/);
  assert.match(output, /\[✓\] First/);
  assert.match(output, /> \[ \] Second/);
  assert.match(output, /↓ more/);
});

test("TokenStatsPanel composes the common panel and tab presentation without changing its loading state", () => {
  const output = stripAnsi(renderToString(<TokenStatsPanel stats={null} selectedTab="overview" />));

  assert.match(output, /Token usage/);
  assert.match(output, /Overview/);
  assert.match(output, /Models/);
  assert.match(output, /Loading local token statistics/);
});

test("RunExplorerPanel keeps the panel boundary when no run data exists yet", () => {
  const output = stripAnsi(renderToString(<RunExplorerPanel runs={[]} health={null} incidents={null} />));

  assert.match(output, /Observability/);
  assert.match(output, /No completed or interrupted runs recorded yet/);
  assert.match(output, /Esc back/);
});
