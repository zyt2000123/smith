export type ListNavigation = "up" | "down" | "pageUp" | "pageDown" | "home" | "end";

export const SLASH_MENU_VISIBLE_ITEMS = 8;
export const SKILLS_PANEL_VISIBLE_ITEMS = 4;

export function moveListIndex(
  currentIndex: number,
  itemCount: number,
  navigation: ListNavigation,
  pageSize: number,
): number {
  if (itemCount <= 0) return 0;

  const current = Math.min(Math.max(currentIndex, 0), itemCount - 1);
  const step = Math.max(pageSize, 1);
  switch (navigation) {
    case "up":
      return Math.max(current - 1, 0);
    case "down":
      return Math.min(current + 1, itemCount - 1);
    case "pageUp":
      return Math.max(current - step, 0);
    case "pageDown":
      return Math.min(current + step, itemCount - 1);
    case "home":
      return 0;
    case "end":
      return itemCount - 1;
  }
}

export function getVisibleList<T>(
  items: readonly T[],
  selectedIndex: number,
  visibleCount: number,
): { items: T[]; startIndex: number } {
  const count = Math.max(visibleCount, 1);
  if (items.length <= count) return { items: [...items], startIndex: 0 };

  const selected = Math.min(Math.max(selectedIndex, 0), items.length - 1);
  const maxStart = items.length - count;
  const centeredStart = selected - Math.floor(count / 2);
  const startIndex = Math.min(Math.max(centeredStart, 0), maxStart);
  return { items: items.slice(startIndex, startIndex + count), startIndex };
}
