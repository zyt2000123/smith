import stringWidth from "string-width";

export type TextAlignment = "left" | "center" | "right";

export type WrapDisplayTextOptions = {
  width: number;
  /** Break an unspaced token instead of letting it exceed the available width. */
  breakLongTokens?: boolean;
  /** Keep indentation and repeated whitespace, used by code and diff content. */
  preserveWhitespace?: boolean;
};

const graphemeSegmenter =
  typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, { granularity: "grapheme" }) : null;

/** Returns the number of terminal cells required to display a string. */
export function displayWidth(value: string): number {
  return stringWidth(value);
}

function graphemes(value: string): string[] {
  if (graphemeSegmenter) {
    return Array.from(graphemeSegmenter.segment(value), ({ segment }) => segment);
  }
  return Array.from(value);
}

function splitLongToken(value: string, width: number): string[] {
  const lines: string[] = [];
  let line = "";
  let lineWidth = 0;

  for (const grapheme of graphemes(value)) {
    const graphemeWidth = displayWidth(grapheme);
    if (line && lineWidth + graphemeWidth > width) {
      lines.push(line);
      line = "";
      lineWidth = 0;
    }
    line += grapheme;
    lineWidth += graphemeWidth;
  }

  if (line || lines.length === 0) lines.push(line);
  return lines;
}

function normalizedLine(value: string, preserveWhitespace: boolean): string {
  return preserveWhitespace ? value : value.trim().replace(/\s+/g, " ");
}

type WrapState = {
  lines: string[];
  current: string;
  currentWidth: number;
};

function flush(state: WrapState, preserveWhitespace: boolean): void {
  if (!state.current) return;
  state.lines.push(preserveWhitespace ? state.current : state.current.trimEnd());
  state.current = "";
  state.currentWidth = 0;
}

function addStandaloneToken(state: WrapState, token: string, options: Required<WrapDisplayTextOptions>): void {
  if (displayWidth(token) <= options.width || !options.breakLongTokens) {
    state.current = token;
    state.currentWidth = displayWidth(token);
    return;
  }

  const fragments = splitLongToken(token, options.width);
  state.lines.push(...fragments.slice(0, -1));
  state.current = fragments[fragments.length - 1] ?? "";
  state.currentWidth = displayWidth(state.current);
}

function addWhitespace(state: WrapState, token: string, options: Required<WrapDisplayTextOptions>): void {
  if (!state.current && !options.preserveWhitespace) return;
  if (options.breakLongTokens && displayWidth(token) > options.width) {
    if (state.current) flush(state, options.preserveWhitespace);
    addStandaloneToken(state, token, options);
    return;
  }
  if (!state.current || state.currentWidth + displayWidth(token) <= options.width) {
    state.current += token;
    state.currentWidth += displayWidth(token);
    return;
  }

  flush(state, options.preserveWhitespace);
  if (options.preserveWhitespace) {
    state.current = token;
    state.currentWidth = displayWidth(token);
  }
}

function addWord(state: WrapState, token: string, options: Required<WrapDisplayTextOptions>): void {
  if (state.current && state.currentWidth + displayWidth(token) <= options.width) {
    state.current += token;
    state.currentWidth += displayWidth(token);
    return;
  }

  if (state.current) flush(state, options.preserveWhitespace);
  addStandaloneToken(state, token, options);
}

function wrapLine(value: string, options: Required<WrapDisplayTextOptions>): string[] {
  if (!value) return [""];
  const state: WrapState = { lines: [], current: "", currentWidth: 0 };
  for (const token of value.match(/\s+|\S+/gu) ?? []) {
    if (/^\s+$/u.test(token)) addWhitespace(state, token, options);
    else addWord(state, token, options);
  }
  flush(state, options.preserveWhitespace);
  return state.lines.length > 0 ? state.lines : [""];
}

/**
 * Wrap text using terminal display cells rather than JavaScript string length.
 * The default preserves whole URLs and identifiers; grid-like renderers opt
 * into hard breaks to keep their geometry inside the available width.
 */
export function wrapDisplayText(value: string, options: WrapDisplayTextOptions): string[] {
  const resolved: Required<WrapDisplayTextOptions> = {
    width: Math.max(1, Math.floor(options.width)),
    breakLongTokens: options.breakLongTokens ?? false,
    preserveWhitespace: options.preserveWhitespace ?? false,
  };

  return value
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .flatMap((line) => wrapLine(normalizedLine(line, resolved.preserveWhitespace), resolved));
}

/** Pads text to a terminal-cell width without truncating it. */
export function padDisplayText(value: string, width: number, alignment: TextAlignment = "left"): string {
  const remaining = Math.max(0, Math.floor(width) - displayWidth(value));
  if (alignment === "right") return `${" ".repeat(remaining)}${value}`;
  if (alignment === "center") {
    const left = Math.floor(remaining / 2);
    return `${" ".repeat(left)}${value}${" ".repeat(remaining - left)}`;
  }
  return `${value}${" ".repeat(remaining)}`;
}
