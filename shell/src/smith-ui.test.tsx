import assert from "node:assert/strict";
import test from "node:test";
import { renderToString } from "ink";

import { SmithUiBlock } from "./smith-ui.js";

test("smith-ui renders a validated json-render Ink component tree", () => {
  const output = renderToString(
    <SmithUiBlock
      payload={{
        version: 1,
        spec: {
          root: "summary",
          elements: {
            summary: {
              type: "Heading",
              props: { text: "Deployment", level: "h1" },
              children: [],
            },
          },
        },
        images: [],
      }}
    />,
  );

  assert.match(output, /Deployment/);
});
