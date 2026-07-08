import {spawn, type ChildProcess} from "node:child_process";
import {createServer} from "node:net";
import path from "node:path";
import {fileURLToPath} from "node:url";

const DEFAULT_SERVER_URL = "http://127.0.0.1:8140";
const REQUIRED_PATHS = [
  "/api/config/llm",
  "/api/employees",
  "/api/plugins",
  "/api/employees/{employee_id}/skills",
  "/api/employees/{employee_id}/sessions/{session_id}/messages/stream",
] as const;
let ownedServer: ChildProcess | null = null;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function cleanupOwnedServer(): void {
  if (ownedServer && ownedServer.exitCode === null) {
    ownedServer.kill("SIGTERM");
  }
  ownedServer = null;
}

function registerCleanup(): void {
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

async function isHealthy(baseUrl: string): Promise<boolean> {
  try {
    const response = await fetch(`${baseUrl}/api/health`);
    return response.ok;
  } catch {
    return false;
  }
}

async function compatibilityIssue(baseUrl: string): Promise<string | null> {
  try {
    const response = await fetch(`${baseUrl}/openapi.json`);
    if (!response.ok) {
      return `openapi responded with HTTP ${response.status}`;
    }

    const payload = await response.json() as {paths?: Record<string, unknown>};
    const paths = payload.paths ?? {};
    const missingPaths = REQUIRED_PATHS.filter((route) => !(route in paths));
    if (missingPaths.length === 0) {
      return null;
    }

    return `missing API routes: ${missingPaths.join(", ")}`;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return `could not inspect OpenAPI schema: ${message}`;
  }
}

async function canListenOnPort(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = createServer();
    server.unref();
    server.once("error", () => {
      resolve(false);
    });
    server.listen(port, "127.0.0.1", () => {
      server.close(() => {
        resolve(true);
      });
    });
  });
}

async function findAvailablePort(startPort: number, maxPort = startPort + 20): Promise<number> {
  for (let port = startPort; port <= maxPort; port += 1) {
    if (await canListenOnPort(port)) {
      return port;
    }
  }

  throw new Error(
    `Could not find a free local port between ${startPort} and ${maxPort}.`,
  );
}

export async function ensureLocalServer(): Promise<{
  baseUrl: string;
  started: boolean;
  note?: string;
}> {
  const baseUrl = process.env.SMITH_SERVER_URL ?? DEFAULT_SERVER_URL;
  const envOverride = Boolean(process.env.SMITH_SERVER_URL);
  const parsedUrl = new URL(baseUrl);
  const preferredPort = Number.parseInt(
    parsedUrl.port || (parsedUrl.protocol === "https:" ? "443" : "80"),
    10,
  );

  const healthy = await isHealthy(baseUrl);
  if (healthy) {
    const issue = await compatibilityIssue(baseUrl);
    if (!issue) {
      return {baseUrl, started: false};
    }

    if (envOverride) {
      throw new Error(
        `Configured SMITH_SERVER_URL points to an incompatible server: ${issue}`,
      );
    }
  }

  if (envOverride) {
    throw new Error(
      `Configured SMITH_SERVER_URL is unreachable: ${baseUrl}`,
    );
  }

  const launchPort = healthy
    ? await findAvailablePort(preferredPort + 1)
    : preferredPort;
  const launchUrl = new URL(baseUrl);
  launchUrl.port = String(launchPort);
  const launchedBaseUrl = launchUrl.toString().replace(/\/$/, "");

  const serverDir = path.join(resolveRepoRoot(), "server");
  ownedServer = spawn(
    "uv",
    ["run", "uvicorn", "app.main:app", "--port", String(launchPort)],
    {
      cwd: serverDir,
      stdio: "ignore",
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
      },
    },
  );

  registerCleanup();

  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (await isHealthy(launchedBaseUrl)) {
      const issue = await compatibilityIssue(launchedBaseUrl);
      if (!issue) {
        return {
          baseUrl: launchedBaseUrl,
          started: true,
          note: healthy
            ? `Found an older Smith server on ${baseUrl}; started an isolated shell server on ${launchedBaseUrl}.`
            : undefined,
        };
      }
    }

    if (ownedServer.exitCode !== null) {
      throw new Error("Local server exited before becoming healthy.");
    }

    await sleep(500);
  }

  cleanupOwnedServer();
  throw new Error("Timed out while starting the local Smith server.");
}
