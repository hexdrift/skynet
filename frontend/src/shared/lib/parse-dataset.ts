export interface ParsedDataset {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  rowCount: number;
}

/**
 * Parse CSV text into rows of fields per RFC 4180.
 * Handles \r\n / \n / \r line endings, quoted fields containing commas
 * or embedded newlines, and escaped quotes ("").
 */
function parseCSV(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (i + 1 < text.length && text[i + 1] === '"') {
          current += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        current += ch;
      }
      continue;
    }
    if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(current.trim());
      current = "";
    } else if (ch === "\r" || ch === "\n") {
      row.push(current.trim());
      current = "";
      rows.push(row);
      row = [];
      if (ch === "\r" && text[i + 1] === "\n") i++;
    } else {
      current += ch;
    }
  }
  if (current.length > 0 || row.length > 0) {
    row.push(current.trim());
    rows.push(row);
  }
  return rows.filter((r) => r.length > 0 && !(r.length === 1 && r[0] === ""));
}

export async function parseDatasetFile(file: File): Promise<ParsedDataset> {
  const text = await file.text();
  const ext = file.name.split(".").pop()?.toLowerCase();

  if (ext === "json") {
    const data = JSON.parse(text);
    const rows = Array.isArray(data) ? data : [data];
    const columns = rows.length > 0 ? Object.keys(rows[0] ?? {}) : [];
    return { columns, rows, rowCount: rows.length };
  }

  if (ext === "csv") {
    const parsed = parseCSV(text);
    if (parsed.length < 2) throw new Error("CSV must have a header row and at least one data row");
    const headers = parsed[0]!;
    const rows = parsed.slice(1).map((values) => {
      const row: Record<string, unknown> = {};
      headers.forEach((h, i) => {
        row[h] = values[i] ?? "";
      });
      return row;
    });
    return { columns: headers, rows, rowCount: rows.length };
  }

  if (ext === "xlsx" || ext === "xls") {
    // Lazy-load xlsx (~900KB) so it stays out of the initial dataset-route
    // chunk — only pulled in when a spreadsheet is actually parsed.
    const XLSX = await import("xlsx");
    const buffer = await file.arrayBuffer();
    const workbook = XLSX.read(buffer, { type: "array" });
    const sheetName = workbook.SheetNames[0];
    if (!sheetName) throw new Error("Excel file has no sheets");
    const sheet = workbook.Sheets[sheetName]!;
    const rows: Array<Record<string, unknown>> = XLSX.utils.sheet_to_json(sheet);
    const columns = rows.length > 0 ? Object.keys(rows[0] ?? {}) : [];
    return { columns, rows, rowCount: rows.length };
  }

  throw new Error(`Unsupported file format: .${ext}. Use .json, .csv, .xlsx, or .xls`);
}
