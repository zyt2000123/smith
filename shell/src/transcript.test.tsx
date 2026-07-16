import assert from "node:assert/strict";
import test from "node:test";

import { skillPresentation } from "./skill-presentation.js";

test("workflow cards expose non-success terminal labels without mounting Ink", () => {
  assert.deepEqual(skillPresentation("running"), { heading: "Running Agent...", tone: "warning" });
  assert.deepEqual(skillPresentation("retry"), { heading: "Retrying Agent...", tone: "warning" });
  assert.deepEqual(skillPresentation("blocked"), { heading: "Agent blocked", tone: "warning" });
  assert.deepEqual(skillPresentation("error"), { heading: "Agent failed", tone: "error" });
  assert.deepEqual(skillPresentation("done"), { heading: "Agent complete", tone: "success" });
});
