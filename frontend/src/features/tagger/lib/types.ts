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

export interface DataRow {
  id: string | number;
  text: string;
  [key: string]: unknown;
}

export type Annotation = string | string[] | undefined;
