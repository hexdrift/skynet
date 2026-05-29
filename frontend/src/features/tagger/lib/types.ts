export type AnnotationMode = "binary" | "multiclass" | "freetext";

export interface Category {
  id: string;
  label: string;
}

export interface TaggerConfig {
  mode: AnnotationMode;
  inputColumns: string[];
  question?: string;
  categories?: Category[];
  prompt?: string;
}

export interface DataField {
  column: string;
  value: unknown;
}

export interface DataRow {
  id: string | number;
  text: string;
  // Multi-column annotation: per-column raw values so the UI can render
  // each field with type-aware formatting (lists, objects) instead of
  // collapsing everything into a single JSON-flavoured string.
  fields?: DataField[];
  [key: string]: unknown;
}

export type Annotation = string | string[] | undefined;
