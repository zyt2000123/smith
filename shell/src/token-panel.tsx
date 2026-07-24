import { Box, Text, useWindowSize } from "ink";

import type { TokenDay, TokenStats } from "./api.js";
import { PanelContainer } from "./panel-container.js";
import { TabbedPanel } from "./tabbed-panel.js";
import { ACCENT, ASSISTANT, INFO, MUTED, WARNING } from "./theme.js";
import { buildRecentDays, formatTokenCount, TOKEN_TAB_LABELS, TOKEN_TABS, type TokenTab } from "./token-stats.js";

const BAR_HEIGHT = 6;
const BAR_WIDTH = 10;
const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function Detail({ label, value, tone = INFO }: { label: string; value: string | number; tone?: string }) {
  return (
    <Box>
      <Text color={MUTED}>{label.padEnd(15)}</Text>
      <Text color={tone}>{value}</Text>
    </Box>
  );
}

function Summary({ stats }: { stats: TokenStats }) {
  const recentDays = buildRecentDays(stats.daily);
  const total = recentDays.reduce((sum, day) => sum + day.total_tokens, 0);
  const input = recentDays.reduce((sum, day) => sum + day.input_tokens, 0);
  const output = recentDays.reduce((sum, day) => sum + day.output_tokens, 0);
  const inputPercent = total > 0 ? Math.round((input / total) * 100) : 0;
  const outputPercent = total > 0 ? Math.round((output / total) * 100) : 0;
  const peakDay = recentDays.reduce((peak, day) => (day.total_tokens > peak.total_tokens ? day : peak), recentDays[0]);
  return (
    <Box flexDirection="column" marginTop={1}>
      <Detail label="7-day total" value={formatTokenCount(total)} tone={ACCENT} />
      <Detail label="Year total" value={formatTokenCount(stats.total_tokens)} />
      <Detail label="Input" value={`${formatTokenCount(input)} · ${inputPercent}%`} tone={ASSISTANT} />
      <Detail label="Output" value={`${formatTokenCount(output)} · ${outputPercent}%`} tone={WARNING} />
      <Detail
        label="7-day peak"
        value={peakDay ? `${formatRecentDay(peakDay.date)} · ${formatTokenCount(peakDay.total_tokens)}` : "-"}
      />
      <Detail label="Favorite model" value={stats.favorite_model || "-"} />
    </Box>
  );
}

function formatRecentDay(date: string): string {
  const day = new Date(`${date}T00:00:00.000Z`);
  return `${WEEKDAY_LABELS[day.getUTCDay()]} ${date.slice(-2)}`;
}

function barSegments(day: TokenDay, maxTokens: number): { filled: number; input: number } {
  if (day.total_tokens <= 0 || maxTokens <= 0) return { filled: 0, input: 0 };

  const filled = Math.max(1, Math.round((day.total_tokens / maxTokens) * BAR_HEIGHT));
  let input = Math.round((day.input_tokens / day.total_tokens) * filled);
  if (day.input_tokens > 0) input = Math.max(1, input);
  if (day.output_tokens > 0 && input === filled && filled > 1) input -= 1;
  return { filled, input };
}

function RollingBarChart({ days }: { days: TokenDay[] }) {
  const { columns } = useWindowSize();
  const maxTokens = Math.max(1, ...days.map((day) => day.total_tokens));
  const width = Math.max(2, Math.min(BAR_WIDTH, Math.floor((columns - 4) / days.length)));
  return (
    <Box flexDirection="column">
      <Box>
        <Text color={MUTED}>Input </Text>
        <Text color={ASSISTANT}>■</Text>
        <Text color={MUTED}> Output </Text>
        <Text color={WARNING}>■</Text>
      </Box>
      <Box flexDirection="column" marginTop={1}>
        {Array.from({ length: BAR_HEIGHT }, (_, index) => {
          const level = BAR_HEIGHT - index;
          return (
            <Box key={`bar-row-${level}`}>
              {days.map((day) => {
                const segments = barSegments(day, maxTokens);
                const filled = level <= segments.filled;
                const color = level <= segments.input ? ASSISTANT : WARNING;
                return (
                  <Box key={`${day.date}-${level}`} width={width} justifyContent="center">
                    <Text color={filled ? color : MUTED}>{filled ? "██" : "  "}</Text>
                  </Box>
                );
              })}
            </Box>
          );
        })}
      </Box>
      <Box>
        {days.map((day) => (
          <Box key={day.date} width={width} justifyContent="center">
            <Text color={MUTED}>{formatRecentDay(day.date)}</Text>
          </Box>
        ))}
      </Box>
      <Box>
        {days.map((day) => (
          <Box key={day.date} width={width} justifyContent="center">
            <Text color={day.total_tokens > 0 ? INFO : MUTED}>{formatTokenCount(day.total_tokens)}</Text>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

function StatsView({ stats }: { stats: TokenStats }) {
  const days = buildRecentDays(stats.daily);
  return (
    <Box flexDirection="column">
      <RollingBarChart days={days} />
      <Summary stats={stats} />
    </Box>
  );
}

function OverviewView({ stats }: { stats: TokenStats }) {
  const days = stats.daily.filter((item) => item.total_tokens > 0).slice(-14);
  const max = Math.max(1, ...days.map((item) => item.total_tokens));
  return (
    <Box flexDirection="column">
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

export function TokenStatsPanel({ stats, selectedTab }: { stats: TokenStats | null; selectedTab: TokenTab }) {
  const { columns } = useWindowSize();
  return (
    <PanelContainer title="Token usage">
      <TabbedPanel
        tabs={TOKEN_TABS.map((tab) => ({ id: tab, label: TOKEN_TAB_LABELS[tab] }))}
        selected={selectedTab}
        hint={columns < 64 ? "←/→ · Esc" : "←/→ switch · Esc back"}
      >
        {!stats ? (
          <Text color={MUTED}>Loading local token statistics…</Text>
        ) : selectedTab === "overview" ? (
          <OverviewView stats={stats} />
        ) : selectedTab === "models" ? (
          <ModelsView stats={stats} />
        ) : (
          <StatsView stats={stats} />
        )}
      </TabbedPanel>
    </PanelContainer>
  );
}
