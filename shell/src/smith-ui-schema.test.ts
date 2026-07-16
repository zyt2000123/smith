import assert from "node:assert/strict";
import test from "node:test";

import { parseSmithUiPayload } from "./smith-ui-schema.js";

const headingSpec = {
  root: "summary",
  elements: {
    summary: {
      type: "Heading",
      props: { text: "Deployment", level: "h1" },
      children: [],
    },
  },
};

test("smith-ui payload parser keeps only a bounded declarative component tree", () => {
  assert.deepEqual(parseSmithUiPayload({ version: 1, spec: headingSpec, images: [] }), {
    version: 1,
    spec: headingSpec,
    images: [],
  });
});

test("smith-ui payload parser rejects remote image sources and non-presentation components", () => {
  assert.equal(
    parseSmithUiPayload({
      version: 1,
      spec: {
        root: "input",
        elements: { input: { type: "TextInput", props: {}, children: [] } },
      },
      images: [],
    }),
    null,
  );
  assert.equal(
    parseSmithUiPayload({
      version: 1,
      spec: headingSpec,
      images: [{ path: "https://example.test/chart.png", alt: "chart" }],
    }),
    null,
  );
  assert.equal(
    parseSmithUiPayload({
      version: 1,
      spec: {
        root: "link",
        elements: { link: { type: "Link", props: { url: "https://example.test" }, children: [] } },
      },
      images: [],
    }),
    null,
  );
});
