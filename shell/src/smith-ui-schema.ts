import path from "node:path";
import { defineCatalog, validateSpec } from "@json-render/core";
import { standardComponentDefinitions } from "@json-render/ink/catalog";
import { schema } from "@json-render/ink/schema";

const MAX_ELEMENTS = 64;
const MAX_DEPTH = 8;
const MAX_IMAGES = 4;
const ELEMENT_ID = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/;
const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp"]);

const smithUiComponentDefinitions = {
  Box: { ...standardComponentDefinitions.Box, props: standardComponentDefinitions.Box.props.partial() },
  Text: {
    ...standardComponentDefinitions.Text,
    props: standardComponentDefinitions.Text.props
      .partial()
      .extend({ text: standardComponentDefinitions.Text.props.shape.text }),
  },
  Newline: { ...standardComponentDefinitions.Newline, props: standardComponentDefinitions.Newline.props.partial() },
  Spacer: { ...standardComponentDefinitions.Spacer, props: standardComponentDefinitions.Spacer.props.partial() },
  Heading: {
    ...standardComponentDefinitions.Heading,
    props: standardComponentDefinitions.Heading.props
      .partial()
      .extend({ text: standardComponentDefinitions.Heading.props.shape.text }),
  },
  Divider: { ...standardComponentDefinitions.Divider, props: standardComponentDefinitions.Divider.props.partial() },
  Badge: {
    ...standardComponentDefinitions.Badge,
    props: standardComponentDefinitions.Badge.props
      .partial()
      .extend({ label: standardComponentDefinitions.Badge.props.shape.label }),
  },
  ProgressBar: {
    ...standardComponentDefinitions.ProgressBar,
    props: standardComponentDefinitions.ProgressBar.props.partial().extend({
      progress: standardComponentDefinitions.ProgressBar.props.shape.progress,
    }),
  },
  Sparkline: {
    ...standardComponentDefinitions.Sparkline,
    props: standardComponentDefinitions.Sparkline.props
      .partial()
      .extend({ data: standardComponentDefinitions.Sparkline.props.shape.data }),
  },
  BarChart: {
    ...standardComponentDefinitions.BarChart,
    props: standardComponentDefinitions.BarChart.props
      .partial()
      .extend({ data: standardComponentDefinitions.BarChart.props.shape.data }),
  },
  Table: {
    ...standardComponentDefinitions.Table,
    props: standardComponentDefinitions.Table.props.partial().extend({
      columns: standardComponentDefinitions.Table.props.shape.columns,
      rows: standardComponentDefinitions.Table.props.shape.rows,
    }),
  },
  List: {
    ...standardComponentDefinitions.List,
    props: standardComponentDefinitions.List.props
      .partial()
      .extend({ items: standardComponentDefinitions.List.props.shape.items }),
  },
  ListItem: {
    ...standardComponentDefinitions.ListItem,
    props: standardComponentDefinitions.ListItem.props
      .partial()
      .extend({ title: standardComponentDefinitions.ListItem.props.shape.title }),
  },
  Card: { ...standardComponentDefinitions.Card, props: standardComponentDefinitions.Card.props.partial() },
  KeyValue: {
    ...standardComponentDefinitions.KeyValue,
    props: standardComponentDefinitions.KeyValue.props.partial().extend({
      label: standardComponentDefinitions.KeyValue.props.shape.label,
      value: standardComponentDefinitions.KeyValue.props.shape.value,
    }),
  },
  StatusLine: {
    ...standardComponentDefinitions.StatusLine,
    props: standardComponentDefinitions.StatusLine.props
      .partial()
      .extend({ text: standardComponentDefinitions.StatusLine.props.shape.text }),
  },
  Metric: {
    ...standardComponentDefinitions.Metric,
    props: standardComponentDefinitions.Metric.props.partial().extend({
      label: standardComponentDefinitions.Metric.props.shape.label,
      value: standardComponentDefinitions.Metric.props.shape.value,
    }),
  },
  Callout: {
    ...standardComponentDefinitions.Callout,
    props: standardComponentDefinitions.Callout.props
      .partial()
      .extend({ content: standardComponentDefinitions.Callout.props.shape.content }),
  },
} as const;

const smithUiCatalog = defineCatalog(schema, {
  components: smithUiComponentDefinitions,
  actions: {},
});

export type SmithUiElement = {
  type: keyof typeof smithUiComponentDefinitions;
  props: Record<string, unknown>;
  children: string[];
};

export type SmithUiSpec = {
  root: string;
  elements: Record<string, SmithUiElement>;
};

export type SmithUiImage = {
  path: string;
  alt: string;
  width?: number;
  height?: number;
};

export type SmithUiPayload = {
  version: 1;
  spec: SmithUiSpec;
  images: SmithUiImage[];
};

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function hasDynamicValue(value: unknown, depth = 0): boolean {
  if (depth > MAX_DEPTH) return true;
  if (Array.isArray(value))
    return value.length > MAX_ELEMENTS || value.some((item) => hasDynamicValue(item, depth + 1));
  const object = record(value);
  if (!object) return false;
  return Object.entries(object).some(([key, item]) => key.startsWith("$") || hasDynamicValue(item, depth + 1));
}

function parseElement(id: string, rawElement: unknown): SmithUiElement | null {
  if (!ELEMENT_ID.test(id)) return null;
  const element = record(rawElement);
  if (
    !element ||
    Object.keys(element).length !== 3 ||
    !("type" in element) ||
    !("props" in element) ||
    !("children" in element)
  ) {
    return null;
  }
  const props = record(element.props);
  if (typeof element.type !== "string" || !props || hasDynamicValue(props) || !Array.isArray(element.children))
    return null;
  if (
    element.children.length > MAX_ELEMENTS ||
    element.children.some((child) => typeof child !== "string" || !ELEMENT_ID.test(child))
  ) {
    return null;
  }
  const children = [...element.children] as string[];
  if (new Set(children).size !== children.length) return null;
  return { type: element.type as SmithUiElement["type"], props, children };
}

function hasValidGraph(root: string, elements: Record<string, SmithUiElement>, elementCount: number): boolean {
  if (Object.values(elements).some((element) => element.children.some((child) => !elements[child]))) return false;
  const visited = new Set<string>();
  const visiting = new Set<string>();
  const visit = (id: string, depth: number): boolean => {
    if (depth > MAX_DEPTH || visiting.has(id)) return false;
    if (visited.has(id)) return true;
    visiting.add(id);
    const valid = elements[id]?.children.every((child) => visit(child, depth + 1)) ?? false;
    visiting.delete(id);
    if (valid) visited.add(id);
    return valid;
  };
  return visit(root, 0) && visited.size === elementCount;
}

function validateStaticTree(spec: Record<string, unknown>): SmithUiSpec | null {
  if (Object.keys(spec).length !== 2 || !("root" in spec) || !("elements" in spec)) return null;
  const root = spec.root;
  const rawElements = record(spec.elements);
  if (typeof root !== "string" || !ELEMENT_ID.test(root) || !rawElements || !rawElements[root]) return null;
  const entries = Object.entries(rawElements);
  if (entries.length === 0 || entries.length > MAX_ELEMENTS) return null;

  const parsedEntries = entries.map(([id, rawElement]) => [id, parseElement(id, rawElement)] as const);
  if (parsedEntries.some(([, element]) => !element)) return null;
  const elements = Object.fromEntries(parsedEntries) as Record<string, SmithUiElement>;
  if (!hasValidGraph(root, elements, entries.length)) return null;
  return { root, elements };
}

function localProjectImagePath(value: unknown): string | null {
  if (typeof value !== "string" || !value || /^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(value)) return null;
  const projectRoot = path.resolve(process.env.SMITH_PROJECT_CWD?.trim() || process.cwd());
  const resolved = path.resolve(value);
  if (resolved !== projectRoot && !resolved.startsWith(`${projectRoot}${path.sep}`)) return null;
  return IMAGE_EXTENSIONS.has(path.extname(resolved).toLowerCase()) ? resolved : null;
}

function imageDimension(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isInteger(value) || !Number.isFinite(value) || value < 1 || value > 120)
    return null;
  return value;
}

function parseImage(value: unknown): SmithUiImage | null {
  const image = record(value);
  if (!image || Object.keys(image).some((key) => !["path", "alt", "width", "height"].includes(key))) return null;
  const source = localProjectImagePath(image.path);
  if (!source || typeof image.alt !== "string" || !image.alt || image.alt.length > 500) return null;
  const parsed: SmithUiImage = { path: source, alt: image.alt };
  for (const dimension of ["width", "height"] as const) {
    if (image[dimension] === undefined) continue;
    const size = imageDimension(image[dimension]);
    if (size === null) return null;
    parsed[dimension] = size;
  }
  return parsed;
}

function parseImages(value: unknown): SmithUiImage[] | null {
  if (!Array.isArray(value) || value.length > MAX_IMAGES) return null;
  const images = value.map(parseImage);
  return images.every((image): image is SmithUiImage => image !== null) ? images : null;
}

function catalogSpec(tree: SmithUiSpec) {
  return {
    root: tree.root,
    elements: Object.fromEntries(
      Object.entries(tree.elements).map(([id, element]) => [id, { ...element, visible: true }]),
    ),
  };
}

export function parseSmithUiPayload(value: unknown): SmithUiPayload | null {
  const payload = record(value);
  if (!payload) return null;
  if (payload.version !== 1 || Object.keys(payload).some((key) => !["version", "spec", "images"].includes(key))) {
    return null;
  }
  const staticSpec = record(payload.spec);
  if (!staticSpec) return null;
  const tree = validateStaticTree(staticSpec);
  if (!tree) return null;
  // json-render's core schema makes `visible` explicit.  smith-ui is
  // deliberately static, so populate it internally instead of accepting
  // model-supplied visibility expressions.
  const componentValidation = smithUiCatalog.validate(catalogSpec(tree));
  const structureValidation = validateSpec(tree, { checkOrphans: true });
  if (!componentValidation.success || !componentValidation.data || !structureValidation.valid) return null;
  const images = parseImages(payload.images);
  if (!images) return null;
  return {
    version: 1,
    spec: tree,
    images,
  };
}
