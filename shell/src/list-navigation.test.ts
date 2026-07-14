import assert from "node:assert/strict";
import test from "node:test";

import { getVisibleList, moveListIndex } from "./list-navigation.js";

test("list navigation clamps at the first and last item", () => {
  assert.equal(moveListIndex(0, 5, "up", 4), 0);
  assert.equal(moveListIndex(4, 5, "down", 4), 4);
  assert.equal(moveListIndex(1, 5, "home", 4), 0);
  assert.equal(moveListIndex(1, 5, "end", 4), 4);
});

test("page navigation advances by the visible window size", () => {
  assert.equal(moveListIndex(0, 10, "pageDown", 4), 4);
  assert.equal(moveListIndex(8, 10, "pageDown", 4), 9);
  assert.equal(moveListIndex(9, 10, "pageUp", 4), 5);
  assert.equal(moveListIndex(2, 10, "pageUp", 4), 0);
});

test("visible list window follows the selected item without dropping data", () => {
  const items = ["a", "b", "c", "d", "e", "f"];

  assert.deepEqual(getVisibleList(items, 0, 4), { items: ["a", "b", "c", "d"], startIndex: 0 });
  assert.deepEqual(getVisibleList(items, 4, 4), { items: ["c", "d", "e", "f"], startIndex: 2 });
  assert.deepEqual(getVisibleList(items, 99, 4), { items: ["c", "d", "e", "f"], startIndex: 2 });
});
