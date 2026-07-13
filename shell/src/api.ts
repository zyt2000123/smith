import { localAuthHeaders } from "./auth.js";

export type LlmUsage = "interactive" | "gate" | "background";
export type LlmTimeoutField = "connect" | "read" | "stream_read" | "write" | "pool";

export type LlmRoute = {
  provider?: string;
  base_url?: string;
  model?: string;
  stream?: boolean;
  max_output_tokens?: number;
  timeout_profile?: LlmUsage;
  has_api_key: boolean;
};

export type LlmTimeoutProfile = Partial<Record<LlmTimeoutField, number>>;

export type LlmConfig = {
  configured: boolean;
  has_api_key: boolean;
  provider: string;
  model: string;
  base_url: string;
  max_output_tokens: number | null;
  routes: Partial<Record<LlmUsage, LlmRoute>>;
  timeout_profiles: Partial<Record<LlmUsage, LlmTimeoutProfile>>;
};

export type AgentProfile = {
  id: string;
  name: string;
  role: string;
  description?: string;
};

export type Session = {
  id: string;
  agent_id: string;
  title: string;
  created_at: string;
  last_message_preview?: string | null;
  last_message_at?: string | null;
  message_count: number;
};

export type SkillSummary = {
  name: string;
  description: string;
  source: string;
  version: string;
  argument_hint: string;
};

export type TokenUsage = {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
};

export type StreamTerminalStatus = "completed" | "failed" | "incomplete";

export type StreamEvent =
  | { type: "message"; text: string }
  | { type: "run_started"; runId: string }
  | { type: "provisional_text_delta"; provisionId: string; text: string }
  | { type: "provisional_commit"; provisionId: string }
  | { type: "provisional_retract"; provisionId: string; reason: string }
  | { type: "thinking"; text: string; done: boolean }
  | { type: "tool_call"; id: string; name: string; hint: string }
  | { type: "tool_result"; id: string; error: boolean; blocked: boolean; preflight: boolean; summary: string }
  | { type: "skill"; name: string; status: string }
  | ({ type: "token_usage" } & TokenUsage)
  | { type: "done"; id?: string; status: StreamTerminalStatus };

type RequestOptions = {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
};

export const DEFAULT_REQUEST_TIMEOUT_MS = 15_000;
export const DEFAULT_STREAM_IDLE_TIMEOUT_MS = 120_000;

type TimeoutSignal = {
  signal: AbortSignal;
  didTimeout: () => boolean;
  touch: () => void;
  dispose: () => void;
};

export function createTimeoutSignal(timeoutMs: number, parentSignal?: AbortSignal): TimeoutSignal {
  const controller = new AbortController();
  let timedOut = false;

  const abortFromParent = () => {
    if (!controller.signal.aborted) {
      controller.abort(parentSignal?.reason ?? new DOMException("The request was aborted.", "AbortError"));
    }
  };

  const expire = () => {
    timedOut = true;
    controller.abort(new DOMException(`Request timed out after ${timeoutMs}ms.`, "TimeoutError"));
  };
  let timer = setTimeout(expire, timeoutMs);

  if (parentSignal?.aborted) {
    abortFromParent();
  } else {
    parentSignal?.addEventListener("abort", abortFromParent, { once: true });
  }

  return {
    signal: controller.signal,
    didTimeout: () => timedOut,
    touch: () => {
      if (controller.signal.aborted) return;
      clearTimeout(timer);
      timer = setTimeout(expire, timeoutMs);
    },
    dispose: () => {
      clearTimeout(timer);
      parentSignal?.removeEventListener("abort", abortFromParent);
    },
  };
}

function timeoutError(timeoutMs: number): Error {
  return new Error(`Request timed out after ${timeoutMs}ms.`);
}

export type LlmRouteInput = {
  provider?: string | null;
  api_key?: string | null;
  base_url?: string | null;
  model?: string | null;
  stream?: boolean | null;
  max_output_tokens?: number | null;
  timeout_profile?: LlmUsage | null;
};

export type LlmTimeoutProfileInput = Partial<Record<LlmTimeoutField, number | null>>;

export type LlmConfigInput = {
  provider: string;
  api_key?: string | null;
  base_url: string;
  model: string;
  max_output_tokens?: number | null;
  routes?: Partial<Record<LlmUsage, LlmRouteInput | null>>;
  timeout_profiles?: Partial<Record<LlmUsage, LlmTimeoutProfileInput | null>>;
};

function buildUrl(baseUrl: string, pathname: string): string {
  return new URL(pathname, `${baseUrl.replace(/\/$/, "")}/`).toString();
}

async function request<T>(baseUrl: string, pathname: string, options: RequestOptions = {}): Promise<T> {
  const authHeaders = await localAuthHeaders();
  const timeoutMs = options.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
  const timeout = createTimeoutSignal(timeoutMs, options.signal);
  try {
    const response = await fetch(buildUrl(baseUrl, pathname), {
      method: options.method ?? "GET",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...authHeaders,
      },
      signal: timeout.signal,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status}: ${text || response.statusText}`);
    }

    return (await response.json()) as T;
  } catch (error) {
    if (timeout.didTimeout()) throw timeoutError(timeoutMs);
    throw error;
  } finally {
    timeout.dispose();
  }
}

export async function getLlmConfig(baseUrl: string): Promise<LlmConfig> {
  return request<LlmConfig>(baseUrl, "/api/config/llm");
}

export async function setLlmConfig(baseUrl: string, payload: LlmConfigInput): Promise<LlmConfig> {
  return request<LlmConfig>(baseUrl, "/api/config/llm", {
    method: "POST",
    body: payload,
  });
}

export async function getAgentProfile(baseUrl: string): Promise<AgentProfile> {
  return request<AgentProfile>(baseUrl, "/api/agent");
}

export async function ensureAgentProfile(baseUrl: string): Promise<AgentProfile> {
  return request<AgentProfile>(baseUrl, "/api/agent/ensure", {
    method: "POST",
  });
}

export async function listSessions(baseUrl: string, options: Pick<RequestOptions, "signal"> = {}): Promise<Session[]> {
  return request<Session[]>(baseUrl, "/api/agent/sessions", options);
}

export async function createSession(
  baseUrl: string,
  title: string,
  options: Pick<RequestOptions, "signal"> = {},
): Promise<Session> {
  return request<Session>(baseUrl, "/api/agent/sessions", {
    method: "POST",
    body: { title },
    signal: options.signal,
  });
}

export type Message = {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export async function listMessages(baseUrl: string, sessionId: string): Promise<Message[]> {
  return request<Message[]>(baseUrl, `/api/agent/sessions/${sessionId}/messages`);
}

export async function listSkills(baseUrl: string): Promise<SkillSummary[]> {
  return request<SkillSummary[]>(baseUrl, "/api/agent/skills");
}

type StreamMessageOptions = {
  context?: string;
  skillName?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
};

type ParsedSseChunk = {
  eventName: string;
  payload: Record<string, unknown>;
};

function splitSseBuffer(buffer: string): { chunks: string[]; remainder: string } {
  const chunks: string[] = [];
  let remainder = buffer;
  let boundary = remainder.indexOf("\n\n");

  while (boundary !== -1) {
    chunks.push(remainder.slice(0, boundary));
    remainder = remainder.slice(boundary + 2);
    boundary = remainder.indexOf("\n\n");
  }

  return { chunks, remainder };
}

function parseSseChunk(rawChunk: string): ParsedSseChunk | null {
  let eventName = "message";
  const dataLines: string[] = [];

  for (const line of rawChunk.split("\n")) {
    const separator = line.indexOf(":");
    if (separator < 1) continue;

    const field = line.slice(0, separator);
    const value = line.slice(separator + 1).replace(/^ /, "");
    if (field === "event") eventName = value;
    if (field === "data") dataLines.push(value);
  }

  if (dataLines.length === 0) return null;

  try {
    const payload = JSON.parse(dataLines.join("\n"));
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new Error(`Invalid payload in SSE ${eventName} event.`);
    }
    return { eventName, payload: payload as Record<string, unknown> };
  } catch {
    throw new Error(`Invalid JSON in SSE ${eventName} event.`);
  }
}

type SseEventDecoder = (payload: Record<string, unknown>) => StreamEvent;

function terminalStatus(payload: Record<string, unknown>): StreamTerminalStatus {
  if (payload.status === "failed" || payload.status === "incomplete") return payload.status;
  return "completed";
}

const SSE_EVENT_DECODERS: Partial<Record<string, SseEventDecoder>> = {
  message: (payload) => ({ type: "message", text: String(payload.text ?? "") }),
  run_started: (payload) => ({ type: "run_started", runId: String(payload.run_id ?? "") }),
  provisional_text_delta: (payload) => ({
    type: "provisional_text_delta",
    provisionId: String(payload.provision_id ?? ""),
    text: String(payload.text ?? ""),
  }),
  provisional_commit: (payload) => ({
    type: "provisional_commit",
    provisionId: String(payload.provision_id ?? ""),
  }),
  provisional_retract: (payload) => ({
    type: "provisional_retract",
    provisionId: String(payload.provision_id ?? ""),
    reason: String(payload.reason ?? ""),
  }),
  thinking: (payload) => ({
    type: "thinking",
    text: String(payload.text ?? ""),
    done: Boolean(payload.done),
  }),
  tool_call: (payload) => ({
    type: "tool_call",
    id: String(payload.id ?? ""),
    name: String(payload.name ?? "tool"),
    hint: String(payload.hint ?? ""),
  }),
  tool_result: (payload) => ({
    type: "tool_result",
    id: String(payload.id ?? ""),
    error: Boolean(payload.error),
    blocked: Boolean(payload.blocked),
    preflight: Boolean(payload.preflight),
    summary: String(payload.summary ?? ""),
  }),
  skill: (payload) => ({
    type: "skill",
    name: String(payload.name ?? ""),
    status: String(payload.status ?? ""),
  }),
  token_usage: (payload) => ({
    type: "token_usage",
    input_tokens: Number(payload.input_tokens ?? 0),
    output_tokens: Number(payload.output_tokens ?? 0),
    total_tokens: Number(payload.total_tokens ?? 0),
  }),
  done: (payload) => ({
    type: "done",
    id: payload.id ? String(payload.id) : undefined,
    status: terminalStatus(payload),
  }),
};

export function decodeSseEvent(rawChunk: string): StreamEvent | null {
  const parsed = parseSseChunk(rawChunk);
  if (!parsed) return null;

  const { eventName, payload } = parsed;
  if (eventName === "error") throw new Error(String(payload.message ?? payload.error ?? "Server stream failed."));

  const decoder = SSE_EVENT_DECODERS[eventName];
  return decoder ? decoder(payload) : null;
}

function consumeSseChunks(chunks: string[], sawDone: boolean): { events: StreamEvent[]; sawDone: boolean } {
  const events: StreamEvent[] = [];
  let completed = sawDone;

  for (const chunk of chunks) {
    const event = decodeSseEvent(chunk);
    if (!event) continue;
    events.push(event);
    completed ||= event.type === "done";
  }

  return { events, sawDone: completed };
}

async function* readSseEvents(
  body: ReadableStream<Uint8Array>,
  onActivity?: () => void,
): AsyncGenerator<StreamEvent, void, void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawDone = false;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      onActivity?.();

      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      const parsed = splitSseBuffer(buffer);
      buffer = parsed.remainder;
      const consumed = consumeSseChunks(parsed.chunks, sawDone);
      sawDone = consumed.sawDone;
      yield* consumed.events;
      if (sawDone) return;
    }

    buffer += decoder.decode().replace(/\r\n/g, "\n");
    const parsed = splitSseBuffer(buffer);
    const chunks = parsed.remainder.trim() ? [...parsed.chunks, parsed.remainder] : parsed.chunks;
    const consumed = consumeSseChunks(chunks, sawDone);
    yield* consumed.events;
    if (!consumed.sawDone) {
      throw new Error("SSE stream ended before a done event was received.");
    }
  } finally {
    try {
      await reader.cancel();
    } catch {
      // The response may already be closed or aborted.
    }
    reader.releaseLock();
  }
}

export async function* streamMessage(
  baseUrl: string,
  sessionId: string,
  content: string,
  options: StreamMessageOptions = {},
): AsyncGenerator<StreamEvent, void, void> {
  const authHeaders = await localAuthHeaders();
  const timeoutMs = options.timeoutMs ?? DEFAULT_STREAM_IDLE_TIMEOUT_MS;
  const timeout = createTimeoutSignal(timeoutMs, options.signal);
  try {
    const response = await fetch(buildUrl(baseUrl, `/api/agent/sessions/${sessionId}/messages/stream`), {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
        ...authHeaders,
      },
      signal: timeout.signal,
      body: JSON.stringify({
        content,
        context: options.context,
        skill_name: options.skillName,
      }),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status}: ${text || response.statusText}`);
    }

    if (!response.body) {
      throw new Error("Streaming response body is missing.");
    }

    yield* readSseEvents(response.body, timeout.touch);
  } catch (error) {
    if (timeout.didTimeout()) throw timeoutError(timeoutMs);
    throw error;
  } finally {
    timeout.dispose();
  }
}
