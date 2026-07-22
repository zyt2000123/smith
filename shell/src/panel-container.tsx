import { Box, Text } from "ink";
import type { ReactNode } from "react";

import { ACCENT, MUTED } from "./theme.js";

export type PanelContainerProps = {
  title: string;
  description?: string;
  footer?: string;
  children: ReactNode;
};

/** Shared visual boundary for Shell panels; it owns presentation, not navigation. */
export function PanelContainer({ title, description, footer, children }: PanelContainerProps) {
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text color={ACCENT} bold>
        {title}
      </Text>
      {description ? <Text color={MUTED}>{description}</Text> : null}
      <Box flexDirection="column" marginTop={description ? 1 : 0}>
        {children}
      </Box>
      {footer ? <Text color={MUTED}>{footer}</Text> : null}
    </Box>
  );
}
