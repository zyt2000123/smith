/** Persistent input history — a JSON string array at ~/.agent-smith/shell_history.json. */

import { mkdirSync, readFileSync, writeFile } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";

export const HISTORY_LIMIT = 200;

function historyPath(): string {
  return path.join(homedir(), ".agent-smith", "shell_history.json");
}

export function loadHistory(): string[] {
  try {
    const parsed: unknown = JSON.parse(readFileSync(historyPath(), "utf8"));
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is string => typeof item === "string").slice(-HISTORY_LIMIT);
  } catch {
    return [];
  }
}

/** Fire-and-forget: history loss must never break input handling. */
export function saveHistory(history: string[]): void {
  try {
    const file = historyPath();
    mkdirSync(path.dirname(file), { recursive: true });
    writeFile(file, JSON.stringify(history.slice(-HISTORY_LIMIT)), () => {});
  } catch {
    // ignore — history is best-effort
  }
}
