import { type ChildProcess, spawn } from "node:child_process";
import { createServer } from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_SERVER_URL = "http://127.0.0.1:8140";
const REQUIRED_PATHS = [
  "/api/config/llm",
  "/api/agent",
  "/api/agent/ensure",
  "/api/plugins",
  "/api/agent/skills",
  "/api/agent/sessions/{session_id}/messages/stream",
] as const;

type ServerConnection = {
  baseUrl: string;
  started: boolean;
  note?: string;
};

type ServerTarget = {
  baseUrl: string;
  envOverride: boolean;
  preferredPort: number;
};

type LaunchedServer = {
  child: ChildProcess;
  getSpawnError: () => Error | undefined;
};

let ownedServer: ChildProcess | null = null;
let cleanupRegistered = false;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function cleanupOwnedServer(): void {
  if (ownedServer?.exitCode === null) ownedServer.kill("SIGTERM");
  ownedServer = null;
}

function registerCleanup(): void {
  if (cleanupRegistered) return;

  cleanupRegistered = true;
  process.once("exit", cleanupOwnedServer);
  process.once("SIGINT", () => {
    cleanupOwnedServer();
    process.exit(130);
  });
  process.once("SIGTERM", () => {
    cleanupOwnedServer();
    process.exit(143);
  });
}

export function resolveRepoRoot(): string {
  const distDir = path.dirname(fileURLToPath(import.meta.url));
  return path.resolve(distDir, "..", "..");
}

function serverTarget(): ServerTarget {
  const baseUrl = process.env.SMITH_SERVER_URL ?? DEFAULT_SERVER_URL;
  const parsedUrl = new URL(baseUrl);
  const fallbackPort = parsedUrl.protocol === "https:" ? "443" : "80";
  return {
    baseUrl,
    envOverride: Boolean(process.env.SMITH_SERVER_URL),
    preferredPort: Number.parseInt(parsedUrl.port || fallbackPort, 10),
  };
}

async function isHealthy(baseUrl: string): Promise<boolean> {
  try {
    return (await fetch(`${baseUrl}/api/health`)).ok;
  } catch {
    return false;
  }
}

async function compatibilityIssue(baseUrl: string): Promise<string | null> {
  try {
    const response = await fetch(`${baseUrl}/openapi.json`);
    if (!response.ok) return `openapi responded with HTTP ${response.status}`;

    const payload = (await response.json()) as { paths?: Record<string, unknown> };
    const paths = payload.paths ?? {};
    const missingPaths = REQUIRED_PATHS.filter((route) => !(route in paths));
    return missingPaths.length === 0 ? null : `missing API routes: ${missingPaths.join(", ")}`;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return `could not inspect OpenAPI schema: ${message}`;
  }
}

async function inspectExistingServer(
  target: ServerTarget,
): Promise<{ healthy: boolean; connection: ServerConnection | null }> {
  const healthy = await isHealthy(target.baseUrl);
  if (!healthy) return { healthy: false, connection: null };

  const issue = await compatibilityIssue(target.baseUrl);
  if (!issue) return { healthy: true, connection: { baseUrl: target.baseUrl, started: false } };
  if (target.envOverride) throw new Error(`Configured SMITH_SERVER_URL points to an incompatible server: ${issue}`);
  return { healthy: true, connection: null };
}

async function canListenOnPort(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = createServer();
    server.unref();
    server.once("error", () => resolve(false));
    server.listen(port, "127.0.0.1", () => {
      server.close(() => resolve(true));
    });
  });
}

async function findAvailablePort(startPort: number, maxPort = startPort + 20): Promise<number> {
  for (let port = startPort; port <= maxPort; port += 1) {
    if (await canListenOnPort(port)) return port;
  }
  throw new Error(`Could not find a free local port between ${startPort} and ${maxPort}.`);
}

async function launchUrl(target: ServerTarget, existingServerWasHealthy: boolean): Promise<string> {
  const port = existingServerWasHealthy ? await findAvailablePort(target.preferredPort + 1) : target.preferredPort;
  const url = new URL(target.baseUrl);
  url.port = String(port);
  return url.toString().replace(/\/$/, "");
}

function launchLocalServer(baseUrl: string): LaunchedServer {
  const port = new URL(baseUrl).port;
  const child = spawn("uv", ["run", "uvicorn", "app.main:app", "--port", port], {
    cwd: path.join(resolveRepoRoot(), "server"),
    stdio: "ignore",
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });
  let spawnError: Error | undefined;
  child.once("error", (error) => {
    spawnError = error;
  });

  ownedServer = child;
  registerCleanup();
  return { child, getSpawnError: () => spawnError };
}

async function waitForCompatibleServer(
  baseUrl: string,
  launch: LaunchedServer,
  priorServerWasHealthy: boolean,
): Promise<ServerConnection> {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (await isHealthy(baseUrl)) {
      const issue = await compatibilityIssue(baseUrl);
      if (!issue) {
        return {
          baseUrl,
          started: true,
          note: priorServerWasHealthy
            ? `Found an older Smith server; started an isolated shell server on ${baseUrl}.`
            : undefined,
        };
      }
    }

    if (launch.child.exitCode !== null) {
      const spawnError = launch.getSpawnError();
      throw new Error(
        spawnError
          ? `Could not launch the local Smith server: ${spawnError.message}`
          : "Local server exited before becoming healthy.",
      );
    }
    await sleep(500);
  }

  cleanupOwnedServer();
  throw new Error("Timed out while starting the local Smith server.");
}

export async function ensureLocalServer(): Promise<ServerConnection> {
  const target = serverTarget();
  const existing = await inspectExistingServer(target);
  if (existing.connection) return existing.connection;
  if (target.envOverride) throw new Error(`Configured SMITH_SERVER_URL is unreachable: ${target.baseUrl}`);

  const baseUrl = await launchUrl(target, existing.healthy);
  const launch = launchLocalServer(baseUrl);
  return waitForCompatibleServer(baseUrl, launch, existing.healthy);
}
