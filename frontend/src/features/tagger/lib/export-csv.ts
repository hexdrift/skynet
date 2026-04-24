import * as XLSX from "xlsx";
import type { DataRow, Annotation, TaggerConfig } from "./types";

type ExportFormat = "csv" | "json" | "xlsx" | "xls";

function buildRows(
  data: DataRow[],
  columns: string[],
  annotations: Record<string, Annotation>,
  config: TaggerConfig,
): { allCols: string[]; rows: Record<string, string>[] } {
  const annotCol =
    config.mode === "binary"
      ? "binary_label"
      : config.mode === "multiclass"
        ? "selected_categories"
        : "extracted_text";

  const allCols = [...columns, annotCol];
  const rows: Record<string, string>[] = [];

  for (const item of data) {
    const row: Record<string, string> = {};
    for (const col of columns) {
      const v = item[col];
      row[col] = v !== undefined && v !== null ? String(v) : "";
    }

    const ann = annotations[String(item.id)];
    let annStr = "";
    if (config.mode === "multiclass" && Array.isArray(ann)) {
      const cats = config.categories ?? [];
      annStr = ann
        .map((catId) => cats.find((c) => c.id === catId)?.label ?? catId)
        .join("; ");
    } else if (typeof ann === "string") {
      annStr = ann;
    }
    row[annotCol] = annStr;
    rows.push(row);
  }

  return { allCols, rows };
}

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function escapeCSV(val: string): string {
  if (val.includes(",") || val.includes('"') || val.includes("\n")) {
    return '"' + val.replace(/"/g, '""') + '"';
  }
  return val;
}

function exportCSV(allCols: string[], rows: Record<string, string>[], filename: string) {
  const BOM = "\ufeff";
  let csv = BOM + allCols.map(escapeCSV).join(",") + "\n";
  for (const row of rows) {
    csv += allCols.map((col) => escapeCSV(row[col] ?? "")).join(",") + "\n";
  }
  download(new Blob([csv], { type: "text/csv;charset=utf-8" }), filename);
}

function exportJSON(rows: Record<string, string>[], filename: string) {
  const json = JSON.stringify(rows, null, 2);
  download(new Blob([json], { type: "application/json;charset=utf-8" }), filename);
}

function exportExcel(
  allCols: string[],
  rows: Record<string, string>[],
  filename: string,
  bookType: "xlsx" | "xlml",
) {
  const ws = XLSX.utils.json_to_sheet(rows, { header: allCols });
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Annotations");
  const buf = XLSX.write(wb, { type: "array", bookType });
  const mime =
    bookType === "xlsx"
      ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      : "application/vnd.ms-excel";
  download(new Blob([buf], { type: mime }), filename);
}

export function exportAnnotations(
  data: DataRow[],
  columns: string[],
  annotations: Record<string, Annotation>,
  config: TaggerConfig,
  format: ExportFormat,
) {
  const { allCols, rows } = buildRows(data, columns, annotations, config);
  const base = `tagging_${config.mode}_${new Date().toISOString().slice(0, 10)}`;

  switch (format) {
    case "csv":
      exportCSV(allCols, rows, `${base}.csv`);
      break;
    case "json":
      exportJSON(rows, `${base}.json`);
      break;
    case "xlsx":
      exportExcel(allCols, rows, `${base}.xlsx`, "xlsx");
      break;
    case "xls":
      exportExcel(allCols, rows, `${base}.xls`, "xlml");
      break;
  }
}
