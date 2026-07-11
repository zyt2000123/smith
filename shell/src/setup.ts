import type { LlmConfig, LlmConfigInput, LlmRouteInput, LlmTimeoutProfileInput, LlmUsage } from "./api.js";
import type { SetupDraft } from "./store.js";

export const PROVIDER_PRESETS = {
  openai: { base_url: "https://api.openai.com/v1", model: "gpt-4.1-mini" },
  anthropic: { base_url: "https://api.anthropic.com", model: "claude-sonnet-4-20250514" },
} as const;

const LLM_USAGES = ["interactive", "gate", "background"] as const satisfies readonly LlmUsage[];
const TIMEOUT_FIELDS = ["connect", "read", "stream_read", "write", "pool"] as const;

export const SETUP_FIELDS = [
  "provider",
  "base_url",
  "model",
  "max_output_tokens",
  "api_key",
  "routes",
  "interactive_api_key",
  "gate_api_key",
  "background_api_key",
  "timeout_profiles",
  "save",
] as const;
export type SetupField = (typeof SETUP_FIELDS)[number];
type EditableSetupField = Exclude<SetupField, "save">;
type RouteSecretField = "interactive_api_key" | "gate_api_key" | "background_api_key";
type JsonRecord = Record<string, unknown>;

const SETUP_FIELD_LABELS: Record<SetupField, string> = {
  provider: "provider",
  base_url: "base URL",
  model: "primary model",
  max_output_tokens: "max output tokens (blank=keep, -=provider default)",
  api_key: "primary API key",
  routes: "route overrides (JSON)",
  interactive_api_key: "interactive route API key",
  gate_api_key: "gate route API key",
  background_api_key: "background route API key",
  timeout_profiles: "timeout profiles (JSON)",
  save: "save and continue",
};

const ROUTE_SECRET_FIELDS = [
  ["interactive", "interactive_api_key"],
  ["gate", "gate_api_key"],
  ["background", "background_api_key"],
] as const satisfies readonly [LlmUsage, RouteSecretField][];

export function fieldValue(draft: SetupDraft, field: SetupField): string {
  if (field === "save") return "save and continue";
  return draft[field];
}

export function setupFieldLabel(field: SetupField): string {
  return SETUP_FIELD_LABELS[field];
}

export function isApiKeySetupField(field: SetupField): boolean {
  return field === "api_key" || field.endsWith("_api_key");
}

export function hasStoredApiKey(config: LlmConfig | null, field: SetupField): boolean {
  if (field === "api_key") return Boolean(config?.has_api_key);
  const route = ROUTE_SECRET_FIELDS.find(([, secretField]) => secretField === field)?.[0];
  return route ? Boolean(config?.routes?.[route]?.has_api_key) : false;
}

function jsonForRouteOverrides(config: LlmConfig | null): string {
  if (!config) return "";
  const routes: Partial<Record<LlmUsage, Omit<LlmRouteInput, "api_key">>> = {};
  for (const usage of LLM_USAGES) {
    const route = config.routes?.[usage];
    if (!route) continue;
    const { has_api_key: _hasApiKey, ...override } = route;
    if (Object.keys(override).length > 0) routes[usage] = override;
  }
  return Object.keys(routes).length > 0 ? JSON.stringify(routes) : "";
}

function jsonForTimeoutProfiles(config: LlmConfig | null): string {
  if (!config?.timeout_profiles || Object.keys(config.timeout_profiles).length === 0) return "";
  return JSON.stringify(config.timeout_profiles);
}

export function createSetupDraft(config: LlmConfig | null): SetupDraft {
  return {
    provider: config?.provider || "openai",
    base_url: config?.base_url || "",
    model: config?.model || "",
    max_output_tokens: config?.max_output_tokens?.toString() ?? "",
    api_key: "",
    routes: jsonForRouteOverrides(config),
    interactive_api_key: "",
    gate_api_key: "",
    background_api_key: "",
    timeout_profiles: jsonForTimeoutProfiles(config),
  };
}

export function isEditableSetupField(field: SetupField): field is EditableSetupField {
  return field !== "save";
}

export function setSetupField(draft: SetupDraft, field: EditableSetupField, value: string): SetupDraft {
  return { ...draft, [field]: value };
}

export function setProvider(draft: SetupDraft, value: string): SetupDraft | null {
  const provider = value.trim().toLowerCase();
  if (!(provider in PROVIDER_PRESETS)) return null;

  const preset = PROVIDER_PRESETS[provider as keyof typeof PROVIDER_PRESETS];
  return {
    ...draft,
    provider,
    base_url: preset.base_url,
    model: preset.model,
  };
}

export function setupFieldAt(index: number): SetupField {
  return SETUP_FIELDS[index] ?? "provider";
}

export function nextSetupIndex(index: number, direction: 1 | -1, wrap: boolean): number {
  if (wrap) return (index + direction + SETUP_FIELDS.length) % SETUP_FIELDS.length;
  return Math.min(Math.max(index + direction, 0), SETUP_FIELDS.length - 1);
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseOptionalObject(value: string, label: string): JsonRecord | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
  if (!isRecord(parsed)) throw new Error(`${label} must be a JSON object.`);
  return parsed;
}

function parseUsage(value: string, label: string): LlmUsage {
  if ((LLM_USAGES as readonly string[]).includes(value)) return value as LlmUsage;
  throw new Error(`${label} must use interactive, gate, or background.`);
}

function parseOptionalString(value: unknown, label: string): string | null {
  if (value === null) return null;
  if (typeof value !== "string" || !value.trim()) throw new Error(`${label} must be a non-empty string or null.`);
  return value.trim();
}

function parseOptionalPositiveInteger(value: unknown, label: string): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${label} must be a positive integer or null.`);
  }
  return value;
}

function parseMaxOutputTokens(value: string): number | null | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  if (trimmed === "-") return null;
  if (!/^\d+$/.test(trimmed)) {
    throw new Error("Max output tokens must be a positive integer, blank, or -.");
  }
  return parseOptionalPositiveInteger(Number(trimmed), "Max output tokens");
}

function parseRouteInput(value: unknown, usage: LlmUsage): LlmRouteInput | null {
  if (value === null) return null;
  if (!isRecord(value)) throw new Error(`routes.${usage} must be an object or null.`);

  const route: LlmRouteInput = {};
  for (const [field, override] of Object.entries(value)) {
    switch (field) {
      case "provider":
      case "base_url":
      case "model":
        route[field] = parseOptionalString(override, `routes.${usage}.${field}`);
        break;
      case "stream":
        if (override !== null && typeof override !== "boolean") {
          throw new Error(`routes.${usage}.stream must be true, false, or null.`);
        }
        route.stream = override;
        break;
      case "max_output_tokens":
        route.max_output_tokens = parseOptionalPositiveInteger(override, `routes.${usage}.max_output_tokens`);
        break;
      case "timeout_profile":
        route.timeout_profile =
          override === null ? null : parseUsage(String(override), `routes.${usage}.timeout_profile`);
        break;
      case "api_key":
        throw new Error(`Use the ${usage} route API key field instead of JSON.`);
      default:
        throw new Error(`routes.${usage}.${field} is not supported.`);
    }
  }
  return route;
}

function parseRoutes(value: string): Partial<Record<LlmUsage, LlmRouteInput | null>> | undefined {
  const parsed = parseOptionalObject(value, "Route overrides");
  if (!parsed) return undefined;
  const routes: Partial<Record<LlmUsage, LlmRouteInput | null>> = {};
  for (const [usageName, override] of Object.entries(parsed)) {
    const usage = parseUsage(usageName, "Route overrides");
    routes[usage] = parseRouteInput(override, usage);
  }
  return routes;
}

function parseTimeoutProfile(value: unknown, usage: LlmUsage): LlmTimeoutProfileInput | null {
  if (value === null) return null;
  if (!isRecord(value)) throw new Error(`timeout_profiles.${usage} must be an object or null.`);
  const profile: LlmTimeoutProfileInput = {};
  for (const [field, timeout] of Object.entries(value)) {
    if (!(TIMEOUT_FIELDS as readonly string[]).includes(field)) {
      throw new Error(`timeout_profiles.${usage}.${field} is not supported.`);
    }
    if (timeout === null) {
      profile[field as keyof LlmTimeoutProfileInput] = null;
      continue;
    }
    if (typeof timeout !== "number" || !Number.isFinite(timeout) || timeout <= 0) {
      throw new Error(`timeout_profiles.${usage}.${field} must be a positive number or null.`);
    }
    profile[field as keyof LlmTimeoutProfileInput] = timeout;
  }
  return profile;
}

function parseTimeoutProfiles(value: string): Partial<Record<LlmUsage, LlmTimeoutProfileInput | null>> | undefined {
  const parsed = parseOptionalObject(value, "Timeout profiles");
  if (!parsed) return undefined;
  const profiles: Partial<Record<LlmUsage, LlmTimeoutProfileInput | null>> = {};
  for (const [usageName, override] of Object.entries(parsed)) {
    const usage = parseUsage(usageName, "Timeout profiles");
    profiles[usage] = parseTimeoutProfile(override, usage);
  }
  return profiles;
}

function secretPatch(value: string): string | null | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return trimmed === "-" ? null : trimmed;
}

function routeForSecret(routes: Partial<Record<LlmUsage, LlmRouteInput | null>>, usage: LlmUsage): LlmRouteInput {
  const existing = routes[usage];
  if (existing && typeof existing === "object") return existing;
  const route: LlmRouteInput = {};
  routes[usage] = route;
  return route;
}

/** Build the API patch while keeping all secret fields out of the JSON editor. */
export function buildLlmConfigInput(draft: SetupDraft): LlmConfigInput {
  let routes = parseRoutes(draft.routes);
  for (const [usage, field] of ROUTE_SECRET_FIELDS) {
    const apiKey = secretPatch(draft[field]);
    if (apiKey === undefined) continue;
    routes ??= {};
    routeForSecret(routes, usage).api_key = apiKey;
  }

  const input: LlmConfigInput = {
    provider: draft.provider.trim(),
    base_url: draft.base_url.trim(),
    model: draft.model.trim(),
  };
  const maxOutputTokens = parseMaxOutputTokens(draft.max_output_tokens);
  if (maxOutputTokens !== undefined) input.max_output_tokens = maxOutputTokens;
  const primaryApiKey = secretPatch(draft.api_key);
  if (primaryApiKey !== undefined) input.api_key = primaryApiKey;
  if (routes !== undefined) input.routes = routes;

  const timeoutProfiles = parseTimeoutProfiles(draft.timeout_profiles);
  if (timeoutProfiles !== undefined) input.timeout_profiles = timeoutProfiles;
  return input;
}
