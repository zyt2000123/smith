import type { TokenDay } from "./api.js";

export type TokenTab = "overview" | "models" | "stats";

export const TOKEN_TABS: readonly TokenTab[] = ["overview", "models", "stats"];

export const TOKEN_TAB_LABELS: Record<TokenTab, string> = {
  overview: "Overview",
  models: "Models",
  stats: "Stats",
};

// server 按 UTC 聚合日期桶（token_stats_service.py），这里必须同样取 UTC 的"今天"
function todayInUtc(): string {
  return new Date().toISOString().slice(0, 10);
}

function emptyTokenDay(date: string): TokenDay {
  return { date, input_tokens: 0, output_tokens: 0, total_tokens: 0, sessions: 0 };
}

export function buildRecentDays(daily: TokenDay[], asOfDate = todayInUtc()): TokenDay[] {
  const byDate = new Map(daily.map((item) => [item.date, item]));
  const asOf = new Date(`${asOfDate}T00:00:00.000Z`);

  return Array.from({ length: 7 }, (_, index) => {
    const current = new Date(asOf.getTime() - (6 - index) * 86_400_000);
    const date = current.toISOString().slice(0, 10);
    return byDate.get(date) ?? emptyTokenDay(date);
  });
}

export function formatTokenCount(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}
