import { type ListNavigation, moveListIndex } from "./list-navigation.js";

export type ModelPickerTarget = "primary" | "review";
export type ModelPickerStep = "model" | "target" | "confirm";

export type ModelPickerState = {
  step: ModelPickerStep;
  models: string[];
  selectedIndex: number;
  model?: string;
  target?: ModelPickerTarget;
};

export type ModelPickerSelection = {
  model: string;
  target: ModelPickerTarget;
};

export const MODEL_PICKER_VISIBLE_ITEMS = 8;

const TARGET_OPTIONS: readonly { label: string; value: ModelPickerTarget }[] = [
  { label: "Primary model (interactive)", value: "primary" },
  { label: "Review model (gate)", value: "review" },
];

export function createModelPicker(models: readonly string[]): ModelPickerState {
  return { step: "model", models: [...models], selectedIndex: 0 };
}

export function modelPickerOptions(picker: ModelPickerState): string[] {
  if (picker.step === "model") return picker.models;
  if (picker.step === "target") return TARGET_OPTIONS.map((option) => option.label);
  return ["Confirm change", "Cancel"];
}

export function modelPickerTargetLabel(target: ModelPickerTarget | undefined): string {
  return TARGET_OPTIONS.find((option) => option.value === target)?.label ?? "Selected model";
}

export function moveModelPicker(picker: ModelPickerState, navigation: ListNavigation): ModelPickerState {
  return {
    ...picker,
    selectedIndex: moveListIndex(
      picker.selectedIndex,
      modelPickerOptions(picker).length,
      navigation,
      MODEL_PICKER_VISIBLE_ITEMS,
    ),
  };
}

export function advanceModelPicker(picker: ModelPickerState): {
  picker: ModelPickerState | null;
  selection: ModelPickerSelection | null;
} {
  if (picker.step === "model") {
    const model = picker.models[picker.selectedIndex];
    return model
      ? { picker: { ...picker, step: "target", selectedIndex: 0, model }, selection: null }
      : { picker: null, selection: null };
  }
  if (picker.step === "target") {
    const target = TARGET_OPTIONS[picker.selectedIndex]?.value;
    return picker.model && target
      ? { picker: { ...picker, step: "confirm", selectedIndex: 0, target }, selection: null }
      : { picker: null, selection: null };
  }
  if (picker.selectedIndex !== 0 || !picker.model || !picker.target) return { picker: null, selection: null };
  return { picker, selection: { model: picker.model, target: picker.target } };
}
