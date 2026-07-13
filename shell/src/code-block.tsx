import { Box, Text, useWindowSize } from "ink";
import { useMemo } from "react";

import { BORDER, MUTED } from "./theme.js";

export type CodeHighlighter = (code: string, language?: string) => string;

export type CodeLine = {
  number: string;
  text: string;
};

export function formatCodeLines(code: string, highlighter?: CodeHighlighter, language?: string): CodeLine[] {
  let highlighted = code;
  try {
    if (highlighter) highlighted = highlighter(code, language);
  } catch {
    highlighted = code;
  }
  const lines = highlighted.split("\n");
  const width = String(lines.length).length;

  return lines.map((text, index) => ({
    number: String(index + 1).padStart(width, " "),
    text,
  }));
}

export function CodeBlock({
  code,
  language,
  highlighter,
}: {
  code: string;
  language?: string;
  highlighter?: CodeHighlighter;
}) {
  const { columns } = useWindowSize();
  const lines = useMemo(() => formatCodeLines(code, highlighter, language), [code, highlighter, language]);
  const displayLanguage = language || "text";
  const width = Math.max(1, columns - 4);

  return (
    <Box
      flexDirection="column"
      width={width}
      borderStyle="single"
      borderColor={BORDER}
      paddingX={1}
      marginTop={1}
      marginBottom={1}
    >
      <Text color={MUTED} dimColor>
        [{displayLanguage}] · {lines.length} 行
      </Text>
      {lines.map((line) => (
        <Text key={`${line.number}-${line.text}`} wrap="truncate">
          <Text color={MUTED} dimColor>
            {line.number} │{" "}
          </Text>
          {line.text}
        </Text>
      ))}
    </Box>
  );
}
