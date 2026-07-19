import { Box, Text } from "ink";

import type { ObservabilityRun } from "./api.js";
import { ACCENT, ERROR, INFO, MUTED, WARNING } from "./theme.js";
import { formatTokenCount } from "./token-stats.js";

function outcomeColor(outcome: string | null | undefined): string {
  if (outcome === "completed") return INFO;
  if (outcome === "failed") return ERROR;
  if (outcome === "incomplete" || outcome === "cancelled") return WARNING;
  return MUTED;
}

export function RunExplorerPanel({ runs }: { runs: ObservabilityRun[] | null }) {
  if (runs === null) return <Text color={MUTED}>Loading run history…</Text>;
  if (runs.length === 0) return <Text color={MUTED}>No completed or interrupted runs recorded yet.</Text>;
  return (
    <Box flexDirection="column">
      <Text bold color={ACCENT}>
        Run Explorer
      </Text>
      <Text color={MUTED}>Recent local runs · Esc back</Text>
      {runs.map((run) => (
        <Box key={run.run_id} flexDirection="column" marginTop={1}>
          <Box gap={1}>
            <Text color={outcomeColor(run.outcome)} bold>
              {run.outcome || "unknown"}
            </Text>
            <Text color={MUTED}>{run.finished_at.replace("T", " ").slice(0, 19)}</Text>
            <Text color={MUTED}>{run.run_id.slice(0, 10)}</Text>
          </Box>
          <Text color={MUTED}>
            {run.event_count} events · {run.tool_call_count} tools · {run.backtrack_count} backtracks ·{" "}
            {formatTokenCount(run.total_tokens)} tokens
            {run.forced_skill ? ` · skill ${run.forced_skill}` : ""}
            {run.reason ? ` · ${run.reason}` : ""}
          </Text>
        </Box>
      ))}
    </Box>
  );
}
