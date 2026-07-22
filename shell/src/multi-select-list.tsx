import { Box, Text } from "ink";

import { INFO, MUTED, SELECTED_BACKGROUND, SELECTED_FOREGROUND } from "./theme.js";

export type MultiSelectListItem = {
  id: string;
  label: string;
  description?: string;
  selected: boolean;
};

export type MultiSelectListProps = {
  items: readonly MultiSelectListItem[];
  focusedIndex: number;
  startIndex?: number;
  totalCount?: number;
  moreLabel?: string;
  emptyLabel?: string;
};

/** Renders a focused, multi-selectable visible window without owning selection state. */
export function MultiSelectList({
  items,
  focusedIndex,
  startIndex = 0,
  totalCount = items.length,
  moreLabel = "more",
  emptyLabel = "No items.",
}: MultiSelectListProps) {
  if (items.length === 0) return <Text color={MUTED}>{emptyLabel}</Text>;

  return (
    <Box flexDirection="column">
      {startIndex > 0 ? <Text color={MUTED}>↑ {moreLabel}</Text> : null}
      {items.map((item, offset) => {
        const index = startIndex + offset;
        const focused = index === focusedIndex;
        return (
          <Box key={item.id} width="100%" backgroundColor={focused ? SELECTED_BACKGROUND : undefined}>
            <Text color={focused ? SELECTED_FOREGROUND : INFO} bold={focused}>
              {focused ? ">" : " "} [{item.selected ? "✓" : " "}] {item.label}
            </Text>
            {item.description ? (
              <Text color={focused ? SELECTED_FOREGROUND : MUTED}>{`  ${item.description}`}</Text>
            ) : null}
          </Box>
        );
      })}
      {startIndex + items.length < totalCount ? <Text color={MUTED}>↓ {moreLabel}</Text> : null}
    </Box>
  );
}
