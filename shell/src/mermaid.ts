import { mermaidToAscii } from "mermaid-ascii";

export type MarkdownSegment =
  | { type: "markdown"; text: string }
  | { type: "mermaid"; text: string }
  | { type: "code"; language: string; text: string };

type OpenFence = {
  marker: "`" | "~";
  length: number;
  line: string;
  language: string;
  body: string[];
};

const FENCE_PATTERN = /^( {0,3})(`{3,}|~{3,})\s*([^\s`~]+)?\s*$/;
const NODE_PATTERN =
  /([A-Za-z_][\w-]*)\s*(\(\((?:\\.|[^)])*\)\)|\(\[(?:\\.|[^)])*\]\)|\[(?:\\.|[^\]])*\]|\{(?:\\.|[^}])*\}|\((?:\\.|[^)])*\))/g;

function pushMarkdown(segments: MarkdownSegment[], lines: string[]): void {
  const text = lines.join("\n");
  if (text.length > 0) segments.push({ type: "markdown", text });
}

function isClosingFence(line: string, fence: OpenFence): boolean {
  const match = line.match(/^( {0,3})(`{3,}|~{3,})\s*$/);
  return Boolean(match && match[2]?.[0] === fence.marker && match[2].length >= fence.length);
}

/** Splits fenced code blocks from surrounding Markdown. */
export function splitMarkdownBlocks(markdown: string): MarkdownSegment[] {
  const segments: MarkdownSegment[] = [];
  const pendingMarkdown: string[] = [];
  let fence: OpenFence | null = null;

  for (const line of markdown.split("\n")) {
    if (!fence) {
      const opening = line.match(FENCE_PATTERN);
      if (opening) {
        pushMarkdown(segments, pendingMarkdown.splice(0));
        fence = {
          marker: opening[2][0] as "`" | "~",
          length: opening[2].length,
          line,
          language: opening[3]?.toLowerCase() || "text",
          body: [],
        };
        continue;
      }

      pendingMarkdown.push(line);
      continue;
    }

    if (isClosingFence(line, fence)) {
      const text = fence.body.join("\n");
      segments.push(
        fence.language === "mermaid" ? { type: "mermaid", text } : { type: "code", language: fence.language, text },
      );
      fence = null;
      continue;
    }

    fence.body.push(line);
  }

  if (fence) {
    pendingMarkdown.push(fence.line, ...fence.body);
  }
  pushMarkdown(segments, pendingMarkdown);
  return segments;
}

/** Backward-compatible alias for callers that only need Mermaid handling. */
export function splitMermaidBlocks(markdown: string): MarkdownSegment[] {
  return splitMarkdownBlocks(markdown);
}

function unquote(value: string): string {
  const trimmed = value.trim();
  if (
    trimmed.length >= 2 &&
    ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'")))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function nodeLabel(shape: string): string {
  let body = shape;
  if (shape.startsWith("((") && shape.endsWith("))")) body = shape.slice(2, -2);
  else if (shape.startsWith("([") && shape.endsWith("])")) body = shape.slice(2, -2);
  else body = shape.slice(1, -1);

  return unquote(body).replace(/\\n/g, " / ").replace(/\s+/g, " ").trim();
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * mermaid-ascii intentionally supports a small flowchart grammar. Normalize
 * Mermaid's node-shape syntax to labels first so terminal output shows
 * `Start` instead of the source token `A[Start]`.
 */
function normalizeFlowchart(source: string): string | null {
  const lines = source.split(/\r?\n/);
  const firstIndex = lines.findIndex((line) => line.trim().length > 0 && !line.trim().startsWith("%%"));
  if (firstIndex < 0) return null;

  const direction = lines[firstIndex]?.trim().match(/^(graph|flowchart)\s+(TD|LR)$/i);
  if (!direction) return null;

  const definitions = new Map<string, string>();
  for (const line of lines) {
    for (const match of line.matchAll(NODE_PATTERN)) {
      const id = match[1];
      const shape = match[2];
      const label = nodeLabel(shape);
      if (id && label) definitions.set(id, label);
    }
  }

  const ids = [...definitions.keys()].sort((left, right) => right.length - left.length);
  let placeholderId = 0;
  const placeholders = new Map<string, string>();
  const placeholderFor = (id: string): string => {
    const token = `__SMITH_MERMAID_NODE_${placeholderId++}__`;
    placeholders.set(token, definitions.get(id) ?? id);
    return token;
  };

  const normalized = lines.map((line, index) => {
    if (index === firstIndex) return `${direction[1].toLowerCase()} ${direction[2].toUpperCase()}`;

    let result = line.replace(NODE_PATTERN, (_match, id: string) => placeholderFor(id));
    for (const id of ids) {
      result = result.replace(new RegExp(`\\b${escapeRegExp(id)}\\b`, "g"), () => placeholderFor(id));
    }
    return result;
  });

  return normalized.join("\n").replace(/__SMITH_MERMAID_NODE_\d+__/g, (token) => placeholders.get(token) ?? token);
}

/** Returns a terminal diagram, or null when the input is not supported. */
export function renderMermaidDiagram(source: string): string | null {
  const normalized = normalizeFlowchart(source);
  if (!normalized) return null;

  const previousDebug = console.debug;
  console.debug = () => undefined;
  try {
    const output = mermaidToAscii(normalized, {
      useAscii: process.env.SMITH_ASCII_DIAGRAMS === "1",
    });
    const compact = output
      .trimEnd()
      .split("\n")
      .map((line) => line.trimEnd())
      .join("\n");
    return compact || null;
  } catch {
    return null;
  } finally {
    console.debug = previousDebug;
  }
}
