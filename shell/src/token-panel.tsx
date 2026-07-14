import { Box, Text } from "ink";

import type { TokenDay, TokenStats } from "./api.js";
import { ACCENT, INFO, MUTED, WARNING } from "./theme.js";
import { buildHeatmapWeeks, formatTokenCount, TOKEN_TAB_LABELS, TOKEN_TABS, type TokenTab } from "./token-stats.js";

const HEAT_COLORS = ["#30343b", "#9be7a5", "#63d97b", "#32b85a", "#16853b", "#0b5d2a"];
const DAY_ROWS = [
  { key: "mon", label: "Mon" },
  { key: "tue", label: "" },
  { key: "wed", label: "Wed" },
  { key: "thu", label: "" },
  { key: "fri", label: "Fri" },
  { key: "sat", label: "" },
  { key: "sun", label: "Sun" },
] as const;

function heatColor(level: number): string {
  return HEAT_COLORS[Math.max(0, Math.min(HEAT_COLORS.length - 1, level))] ?? HEAT_COLORS[0];
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <Box width={32}>
      <Text color={MUTED}>{label}: </Text>
      <Text color={INFO}>{value}</Text>
    </Box>
  );
}

function Tabs({ selected }: { selected: TokenTab }) {
  return (
    <Box gap={2} marginBottom={1}>
      {TOKEN_TABS.map((tab) => (
        <Text key={tab} color={tab === selected ? ACCENT : MUTED} bold={tab === selected}>
          {TOKEN_TAB_LABELS[tab]}
        </Text>
      ))}
      <Text color={MUTED}>←/→ switch · Esc back</Text>
    </Box>
  );
}

function Summary({ stats }: { stats: TokenStats }) {
  return (
    <Box flexDirection="column" marginTop={1}>
      <Box>
        <Stat label="Favorite model" value={stats.favorite_model || "-"} />
        <Stat label="Total tokens" value={formatTokenCount(stats.total_tokens)} />
      </Box>
      <Box>
        <Stat label="Sessions" value={stats.session_count} />
        <Stat label="Active days" value={`${stats.active_days}/${stats.daily.length}`} />
      </Box>
      <Box>
        <Stat label="Current streak" value={`${stats.current_streak} days`} />
        <Stat label="Longest streak" value={`${stats.longest_streak} days`} />
      </Box>
      <Box>
        <Stat label="Peak hour" value={stats.peak_hour === null ? "-" : `${stats.peak_hour}:00`} />
        <Stat
          label="Input / output"
          value={`${formatTokenCount(stats.input_tokens)} / ${formatTokenCount(stats.output_tokens)}`}
        />
      </Box>
    </Box>
  );
}

function StatsView({ stats }: { stats: TokenStats }) {
  const weeks = buildHeatmapWeeks(stats.year, stats.daily);
  return (
    <Box flexDirection="column">
      <Text color={INFO}>
        Token activity · {stats.year}
        {stats.estimated ? " · local estimate" : ""}
      </Text>
      {DAY_ROWS.map(({ key: dayKey, label }, row) => (
        <Box key={dayKey}>
          <Text color={MUTED}>{label.padEnd(3)} </Text>
          {weeks.map((week) => {
            const cell = week[row];
            const weekKey = week.find((item) => item !== null)?.date ?? `empty-${dayKey}`;
            return (
              <Text key={`${weekKey}-${dayKey}`} color={cell ? heatColor(cell.level) : HEAT_COLORS[0]}>
                {cell ? "■" : "·"}
              </Text>
            );
          })}
        </Box>
      ))}
      <Box marginTop={1}>
        <Text color={MUTED}>Less </Text>
        {HEAT_COLORS.slice(1).map((color) => (
          <Text key={color} color={color}>
            ■
          </Text>
        ))}
        <Text color={MUTED}> More</Text>
      </Box>
      <Summary stats={stats} />
    </Box>
  );
}

function OverviewView({ stats }: { stats: TokenStats }) {
  const days = stats.daily.filter((item) => item.total_tokens > 0).slice(-14);
  const max = Math.max(1, ...days.map((item) => item.total_tokens));
  return (
    <Box flexDirection="column">
      <Text color={INFO}>Tokens per day · recent activity</Text>
      {days.length === 0 ? (
        <Text color={MUTED}>No token usage recorded yet.</Text>
      ) : (
        days.map((day) => (
          <Box key={day.date}>
            <Text color={MUTED}>{day.date} </Text>
            <Text color={WARNING}>{"█".repeat(Math.max(1, Math.round((day.total_tokens / max) * 32)))}</Text>
            <Text color={MUTED}> {formatTokenCount(day.total_tokens)}</Text>
          </Box>
        ))
      )}
      <Summary stats={stats} />
    </Box>
  );
}

function ModelsView({ stats }: { stats: TokenStats }) {
  return (
    <Box flexDirection="column">
      <Text color={INFO}>Models · {stats.year}</Text>
      {stats.models.length === 0 ? (
        <Text color={MUTED}>No token usage recorded yet.</Text>
      ) : (
        stats.models.map((model) => (
          <Box key={model.model}>
            <Text color={ACCENT}>{model.model.padEnd(28).slice(0, 28)}</Text>
            <Text color={INFO}>{formatTokenCount(model.total_tokens).padStart(8)}</Text>
            <Text color={MUTED}>{`  ${model.sessions} session(s)`}</Text>
          </Box>
        ))
      )}
    </Box>
  );
}

function DailyView({ stats }: { stats: TokenStats }) {
  const days = stats.daily
    .filter((item) => item.total_tokens > 0)
    .slice(-20)
    .reverse();
  return (
    <Box flexDirection="column">
      <Text color={INFO}>Daily breakdown · {stats.year}</Text>
      {days.length === 0 ? (
        <Text color={MUTED}>No token usage recorded yet.</Text>
      ) : (
        days.map((day) => <DailyRow key={day.date} day={day} />)
      )}
    </Box>
  );
}

function DailyRow({ day }: { day: TokenDay }) {
  return (
    <Box>
      <Text color={MUTED}>{day.date} </Text>
      <Text color={INFO}>{formatTokenCount(day.total_tokens).padStart(8)}</Text>
      <Text
        color={MUTED}
      >{`  in ${formatTokenCount(day.input_tokens)} · out ${formatTokenCount(day.output_tokens)} · ${day.sessions} session(s)`}</Text>
    </Box>
  );
}

export function TokenStatsPanel({ stats, selectedTab }: { stats: TokenStats | null; selectedTab: TokenTab }) {
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Tabs selected={selectedTab} />
      {!stats ? (
        <Text color={MUTED}>Loading local token statistics…</Text>
      ) : selectedTab === "overview" ? (
        <OverviewView stats={stats} />
      ) : selectedTab === "models" ? (
        <ModelsView stats={stats} />
      ) : selectedTab === "daily" ? (
        <DailyView stats={stats} />
      ) : (
        <StatsView stats={stats} />
      )}
    </Box>
  );
}
