import { Box, Text } from "ink";
import type { ReactNode } from "react";

import { ACCENT, MUTED } from "./theme.js";

export type TabbedPanelItem<T extends string> = {
  id: T;
  label: string;
};

export type TabbedPanelProps<T extends string> = {
  tabs: readonly TabbedPanelItem<T>[];
  selected: T;
  hint?: string;
  children: ReactNode;
};

/** Shared tab presentation. Keyboard routing remains in input.ts. */
export function TabbedPanel<T extends string>({ tabs, selected, hint, children }: TabbedPanelProps<T>) {
  return (
    <Box flexDirection="column">
      <Box flexWrap="wrap" gap={2} marginBottom={1}>
        {tabs.map((tab) => (
          <Text key={tab.id} color={tab.id === selected ? ACCENT : MUTED} bold={tab.id === selected}>
            {tab.label}
          </Text>
        ))}
        {hint ? <Text color={MUTED}>{hint}</Text> : null}
      </Box>
      {children}
    </Box>
  );
}
