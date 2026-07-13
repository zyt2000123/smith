import { readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const AUTH_TOKEN_PATH = path.join(os.homedir(), ".agent-smith", "auth_token");

export function buildAuthHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

export async function localAuthHeaders(): Promise<Record<string, string>> {
  let token: string;
  try {
    token = (await readFile(AUTH_TOKEN_PATH, "utf8")).trim();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Local Smith auth token is unavailable: ${message}`);
  }

  if (!token) throw new Error("Local Smith auth token is empty.");
  return buildAuthHeaders(token);
}
