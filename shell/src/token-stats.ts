import type { TokenDay } from "./api.js";

export type TokenTab = "overview" | "models" | "daily" | "stats";

export const TOKEN_TABS: readonly TokenTab[] = ["overview", "models", "daily", "stats"];

export const TOKEN_TAB_LABELS: Record<TokenTab, string> = {
  overview: "Overview",
  models: "Models",
  daily: "Daily",
  stats: "Stats",
};

export type HeatmapCell = TokenDay & { level: number };

export function tokenLevel(totalTokens: number, maxTokens: number): number {
  if (totalTokens <= 0 || maxTokens <= 0) return 0;
  const ratio = totalTokens / maxTokens;
  if (ratio <= 0.25) return 1;
  if (ratio <= 0.5) return 2;
  if (ratio <= 0.75) return 3;
  if (ratio < 1) return 4;
  return 5;
}

export function buildHeatmapWeeks(year: number, daily: TokenDay[]): Array<Array<HeatmapCell | null>> {
  const byDate = new Map(daily.map((item) => [item.date, item]));
  const maxTokens = Math.max(0, ...daily.map((item) => item.total_tokens));
  const start = new Date(Date.UTC(year, 0, 1));
  const end = new Date(Date.UTC(year + 1, 0, 1));
  const daysInYear = Math.round((end.getTime() - start.getTime()) / 86_400_000);
  const mondayOffset = (start.getUTCDay() + 6) % 7;
  const weeks: Array<Array<HeatmapCell | null>> = [];

  for (let cursor = 0; cursor < mondayOffset + daysInYear; cursor += 1) {
    const week = Math.floor(cursor / 7);
    const dayIndex = cursor % 7;
    weeks[week] ??= Array.from({ length: 7 }, () => null);
    if (cursor < mondayOffset) continue;

    const current = new Date(start.getTime() + (cursor - mondayOffset) * 86_400_000);
    const item = byDate.get(current.toISOString().slice(0, 10));
    if (item) weeks[week][dayIndex] = { ...item, level: tokenLevel(item.total_tokens, maxTokens) };
  }

  return weeks;
}

export function formatTokenCount(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}
