import { Box, Text } from "ink";

import { type WrapDisplayTextOptions, wrapDisplayText } from "./text-layout.js";

export type DisplayTextProps = WrapDisplayTextOptions & {
  text: string;
  color?: string;
  bold?: boolean;
  dimColor?: boolean;
};

/** A content-preserving terminal text primitive. Truncation is never implicit. */
export function DisplayText({
  text,
  width,
  breakLongTokens,
  preserveWhitespace,
  color,
  bold,
  dimColor,
}: DisplayTextProps) {
  const lines = wrapDisplayText(text, { width, breakLongTokens, preserveWhitespace });
  const lineCounts = new Map<string, number>();

  return (
    <Box flexDirection="column">
      {lines.map((line) => {
        const occurrence = lineCounts.get(line) ?? 0;
        lineCounts.set(line, occurrence + 1);
        return (
          <Text key={`${line}\u0000${occurrence}`} color={color} bold={bold} dimColor={dimColor}>
            {line || " "}
          </Text>
        );
      })}
    </Box>
  );
}
