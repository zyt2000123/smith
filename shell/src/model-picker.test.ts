import assert from "node:assert/strict";
import test from "node:test";

import { advanceModelPicker, createModelPicker, moveModelPicker } from "./model-picker.js";

test("model picker advances from a model to its target and then confirmation", () => {
  let picker = createModelPicker(["GLM-5.2", "gpt-4.1"]);
  picker = moveModelPicker(picker, "down");
  const modelStep = advanceModelPicker(picker);
  assert.ok(modelStep.picker);
  picker = modelStep.picker;

  assert.equal(picker.step, "target");
  assert.equal(picker.model, "gpt-4.1");

  const targetStep = advanceModelPicker(picker);
  assert.ok(targetStep.picker);
  picker = targetStep.picker;
  assert.equal(picker.step, "confirm");
  assert.equal(picker.target, "primary");
});
