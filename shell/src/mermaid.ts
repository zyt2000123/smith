import { renderMermaidASCII } from "beautiful-mermaid";
import stringWidth from "string-width";

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
const PLACEHOLDER_START = 0xe000;
const MAX_INLINE_EDGE_LABEL_WIDTH = 24;
const EDGE_ANNOTATION_WIDTH = 80;

type NormalizedFlowchart = {
  text: string;
  annotations: string[];
};

type EncodedDiagram = {
  text: string;
  restore: (rendered: string) => string | null;
};

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

function normalizeDiagramText(value: string): string {
  return value
    .replace(/<br\s*\/?\s*>/gi, " / ")
    .replace(/\\n/g, " / ")
    .replace(/\s+/g, " ")
    .trim();
}

function graphemes(value: string): string[] {
  if (typeof Intl.Segmenter === "function") {
    const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });
    return Array.from(segmenter.segment(value), ({ segment }) => segment);
  }
  return Array.from(value);
}

/**
 * Mermaid ASCII renderers measure labels with String.length, while terminals measure
 * their visual width in cells. Expand wide graphemes to one-cell placeholders
 * for layout, then restore the original graphemes after drawing.
 */
function encodeTerminalWidths(source: string): EncodedDiagram {
  const encodedByGrapheme = new Map<string, { token: string; value: string }>();
  const replacements = new Map<string, { token: string; value: string }>();
  let nextCodePoint = PLACEHOLDER_START;
  let encoded = "";

  for (const grapheme of graphemes(source)) {
    const width = stringWidth(grapheme);
    if (width <= 1) {
      encoded += grapheme;
      continue;
    }

    let replacement = encodedByGrapheme.get(grapheme);
    if (!replacement) {
      let placeholder = String.fromCodePoint(nextCodePoint++);
      while (source.includes(placeholder) || replacements.has(placeholder)) {
        placeholder = String.fromCodePoint(nextCodePoint++);
      }

      replacement = {
        token: placeholder.repeat(width),
        value: grapheme,
      };
      encodedByGrapheme.set(grapheme, replacement);
      replacements.set(placeholder, replacement);
    }

    encoded += replacement.token;
  }

  return {
    text: encoded,
    restore: (rendered) => {
      let restored = rendered;
      for (const { token, value } of replacements.values()) {
        restored = restored.replaceAll(token, value);
      }
      return [...replacements.keys()].some((placeholder) => restored.includes(placeholder)) ? null : restored;
    },
  };
}

function extractLongEdgeLabels(source: string): { text: string; annotations: string[] } {
  const annotations: string[] = [];
  const text = source.replace(/-->\|((?:\\.|[^|])*)\|/g, (_match: string, rawLabel: string) => {
    const label = normalizeDiagramText(rawLabel);
    if (stringWidth(label) <= MAX_INLINE_EDGE_LABEL_WIDTH) return `-->|${label}|`;

    annotations.push(label);
    return "-->";
  });

  return { text, annotations };
}

function wrapTerminalText(value: string, maxWidth: number): string[] {
  const lines: string[] = [];
  let line = "";
  let width = 0;

  for (const grapheme of graphemes(value)) {
    const graphemeWidth = stringWidth(grapheme);
    if (line && width + graphemeWidth > maxWidth) {
      lines.push(line.trimEnd());
      line = "";
      width = 0;
    }
    if (!line && grapheme === " ") continue;
    line += grapheme;
    width += graphemeWidth;
  }

  if (line) lines.push(line.trimEnd());
  return lines;
}

/**
 * The terminal renderer intentionally supports a small flowchart grammar. Keep
 * Mermaid node IDs and shapes intact so the renderer can preserve the graph
 * structure and lay out CJK labels correctly.
 */
function normalizeFlowchart(source: string): NormalizedFlowchart | null {
  const extracted = extractLongEdgeLabels(source);
  const lines = extracted.text.split(/\r?\n/);
  const firstIndex = lines.findIndex((line) => line.trim().length > 0 && !line.trim().startsWith("%%"));
  if (firstIndex < 0) return null;

  const direction = lines[firstIndex]?.trim().match(/^(graph|flowchart)\s+(TD|LR)$/i);
  if (!direction) return null;

  return {
    text: lines
      .map((line, index) =>
        index === firstIndex ? `${direction[1].toLowerCase()} ${direction[2].toUpperCase()}` : line,
      )
      .join("\n"),
    annotations: extracted.annotations,
  };
}

/** Returns a terminal diagram, or null when the input is not supported. */
export function renderMermaidDiagram(source: string): string | null {
  const normalized = normalizeFlowchart(source);
  if (!normalized) return null;
  const encoded = encodeTerminalWidths(normalized.text);

  const previousDebug = console.debug;
  console.debug = () => undefined;
  try {
    const output = renderMermaidASCII(encoded.text, {
      useAscii: process.env.SMITH_ASCII_DIAGRAMS === "1",
      colorMode: "none",
    });
    const compact = output
      .trimEnd()
      .split("\n")
      .map((line) => line.trimEnd())
      .join("\n");
    const restored = compact ? encoded.restore(compact) : null;
    if (!restored) return null;

    if (normalized.annotations.length === 0) return restored;

    const annotations = normalized.annotations
      .flatMap((annotation) => wrapTerminalText(`↳ ${annotation}`, EDGE_ANNOTATION_WIDTH))
      .join("\n");
    return annotations ? `${restored}\n\n${annotations}` : restored;
  } catch {
    return null;
  } finally {
    console.debug = previousDebug;
  }
}
