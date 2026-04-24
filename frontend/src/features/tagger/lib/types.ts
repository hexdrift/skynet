export type AnnotationMode = "binary" | "multiclass" | "freetext";

export interface Category {
  id: string;
  label: string;
}

export interface TaggerConfig {
  mode: AnnotationMode;
  question?: string;
  categories?: Category[];
  prompt?: string;
  placeholder?: string;
}

export interface DataRow {
  id: string | number;
  text: string;
  [key: string]: unknown;
}

export type Annotation = string | string[] | undefined;

export interface TaggerState {
  phase: "setup" | "annotating";
  config: TaggerConfig | null;
  data: DataRow[];
  columns: string[];
  annotations: Record<string, Annotation>;
  currentIndex: number;
}
