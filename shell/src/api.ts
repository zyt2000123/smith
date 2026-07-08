export type LlmConfig = {
  configured: boolean;
  has_api_key: boolean;
  provider: string;
  model: string;
  base_url: string;
};

export type Employee = {
  id: string;
  name: string;
  role: string;
  description?: string;
};

export type Session = {
  id: string;
  employee_id: string;
  title: string;
  created_at: string;
  last_message_preview?: string | null;
  last_message_at?: string | null;
  message_count: number;
};

export type PluginManifest = {
  name: string;
  enabled?: boolean;
  installed?: boolean;
  status?: string;
  version?: string;
  description?: string;
  trigger_type?: string;
  skill_count?: number;
  skills?: Array<{path?: string}>;
};

export type SkillSummary = {
  name: string;
  description: string;
  source: string;
  version: string;
  argument_hint: string;
};

export type StreamEvent =
  | {type: "message"; text: string}
  | {type: "thinking"; text: string; done: boolean}
  | {type: "tool_call"; id: string; name: string; hint: string}
  | {type: "tool_result"; id: string; error: boolean; blocked: boolean; summary: string}
  | {type: "skill"; name: string; status: string}
  | {type: "done"; id?: string};

type RequestOptions = {
  method?: string;
  body?: unknown;
};

export type LlmConfigInput = {
  provider: string;
  api_key?: string;
  base_url: string;
  model: string;
};

function buildUrl(baseUrl: string, pathname: string): string {
  return new URL(pathname, `${baseUrl.replace(/\/$/, "")}/`).toString();
}

async function request<T>(
  baseUrl: string,
  pathname: string,
  options: RequestOptions = {},
): Promise<T> {
  const response = await fetch(buildUrl(baseUrl, pathname), {
    method: options.method ?? "GET",
    headers: {
      "Accept": "application/json",
      "Content-Type": "application/json",
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text || response.statusText}`);
  }

  return response.json() as Promise<T>;
}

export async function getLlmConfig(baseUrl: string): Promise<LlmConfig> {
  return request<LlmConfig>(baseUrl, "/api/config/llm");
}

export async function setLlmConfig(
  baseUrl: string,
  payload: LlmConfigInput,
): Promise<LlmConfig> {
  return request<LlmConfig>(baseUrl, "/api/config/llm", {
    method: "POST",
    body: payload,
  });
}

export async function listEmployees(baseUrl: string): Promise<Employee[]> {
  return request<Employee[]>(baseUrl, "/api/employees");
}

export async function createEmployee(
  baseUrl: string,
  payload: Pick<Employee, "name" | "role" | "description">,
): Promise<Employee> {
  return request<Employee>(baseUrl, "/api/employees", {
    method: "POST",
    body: payload,
  });
}

export async function ensureSmithAgent(baseUrl: string): Promise<Employee> {
  const employees = await listEmployees(baseUrl);
  const existing = employees.find(
    (employee) => employee.name === "Smith" && employee.role === "personal-assistant",
  );

  if (existing) {
    return existing;
  }

  return createEmployee(baseUrl, {
    name: "Smith",
    role: "personal-assistant",
    description:
      "面向个人工作流的常驻本地 Agent，负责理解目标、整理上下文、检索信息、规划执行并交付可落地结果。",
  });
}

export async function listSessions(
  baseUrl: string,
  employeeId: string,
): Promise<Session[]> {
  return request<Session[]>(baseUrl, `/api/employees/${employeeId}/sessions`);
}

export async function createSession(
  baseUrl: string,
  employeeId: string,
  title: string,
): Promise<Session> {
  return request<Session>(baseUrl, `/api/employees/${employeeId}/sessions`, {
    method: "POST",
    body: {title},
  });
}

export async function listPlugins(baseUrl: string): Promise<PluginManifest[]> {
  try {
    return await request<PluginManifest[]>(baseUrl, "/api/plugins");
  } catch {
    return [];
  }
}

export async function enablePlugin(baseUrl: string, name: string): Promise<{status: string; plugin: string}> {
  return request<{status: string; plugin: string}>(baseUrl, `/api/plugins/${name}/enable`, {
    method: "POST",
  });
}

export async function disablePlugin(baseUrl: string, name: string): Promise<{status: string; plugin: string}> {
  return request<{status: string; plugin: string}>(baseUrl, `/api/plugins/${name}/disable`, {
    method: "POST",
  });
}

export async function listSkills(
  baseUrl: string,
  employeeId: string,
): Promise<SkillSummary[]> {
  return request<SkillSummary[]>(baseUrl, `/api/employees/${employeeId}/skills`);
}

type StreamMessageOptions = {
  context?: string;
  skillName?: string;
};

export async function *streamMessage(
  baseUrl: string,
  employeeId: string,
  sessionId: string,
  content: string,
  options: StreamMessageOptions = {},
): AsyncGenerator<StreamEvent, void, void> {
  const response = await fetch(
    buildUrl(baseUrl, `/api/employees/${employeeId}/sessions/${sessionId}/messages/stream`),
    {
      method: "POST",
      headers: {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        content,
        context: options.context,
        skill_name: options.skillName,
      }),
    },
  );

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text || response.statusText}`);
  }

  if (!response.body) {
    throw new Error("Streaming response body is missing.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const {done, value} = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, {stream: true}).replace(/\r\n/g, "\n");

    while (true) {
      const boundary = buffer.indexOf("\n\n");
      if (boundary === -1) {
        break;
      }

      const rawChunk = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      let eventName = "message";
      const dataLines: string[] = [];

      for (const line of rawChunk.split("\n")) {
        if (line.startsWith("event: ")) {
          eventName = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          dataLines.push(line.slice(6));
        }
      }

      if (dataLines.length === 0) {
        continue;
      }

      const payloadText = dataLines.join("\n");
      let payload: Record<string, unknown> = {};
      try {
        payload = JSON.parse(payloadText) as Record<string, unknown>;
      } catch {
        payload = {};
      }

      switch (eventName) {
        case "message":
          yield {type: "message", text: String(payload.text ?? "")};
          break;
        case "thinking":
          yield {
            type: "thinking",
            text: String(payload.text ?? ""),
            done: Boolean(payload.done),
          };
          break;
        case "tool_call":
          yield {
            type: "tool_call",
            id: String(payload.id ?? ""),
            name: String(payload.name ?? "tool"),
            hint: String(payload.hint ?? ""),
          };
          break;
        case "tool_result":
          yield {
            type: "tool_result",
            id: String(payload.id ?? ""),
            error: Boolean(payload.error),
            blocked: Boolean(payload.blocked),
            summary: String(payload.summary ?? ""),
          };
          break;
        case "skill":
          yield {
            type: "skill",
            name: String(payload.name ?? ""),
            status: String(payload.status ?? ""),
          };
          break;
        case "done":
          yield {type: "done", id: payload.id ? String(payload.id) : undefined};
          break;
        default:
          break;
      }
    }
  }
}
