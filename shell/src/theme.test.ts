import assert from "node:assert/strict";
import test from "node:test";

import { ACCENT, SELECTED_BACKGROUND, SELECTED_FOREGROUND } from "./theme.js";

function relativeLuminance(hex: string): number {
  const channels = hex
    .slice(1)
    .match(/.{2}/g)
    ?.map((channel) => Number.parseInt(channel, 16) / 255);
  if (channels?.length !== 3) throw new Error(`Expected a six-digit hex color, got ${hex}`);

  const [red, green, blue] = channels.map((channel) =>
    channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

test("selected menu colors keep terminal options readable", () => {
  const foreground = relativeLuminance(SELECTED_FOREGROUND);
  const background = relativeLuminance(SELECTED_BACKGROUND);
  const contrast = (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05);

  assert.ok(contrast >= 4.5, `expected WCAG AA text contrast, received ${contrast.toFixed(2)}:1`);
});

test("selected menu foreground uses the Smith brand accent", () => {
  assert.equal(SELECTED_FOREGROUND, ACCENT);
});
