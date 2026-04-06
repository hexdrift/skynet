export interface ParsedDataset {
  columns: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
}

/**
 * Parse a single CSV field that may be quoted.
 * Handles commas inside quotes and escaped quotes ("").
 */
function parseCSVLine(line: string): string[] {
  const fields: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (i + 1 < line.length && line[i + 1] === '"') {
          current += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        current += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      fields.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  fields.push(current.trim());
  return fields;
}

export async function parseDatasetFile(file: File): Promise<ParsedDataset> {
  const text = await file.text();
  const ext = file.name.split(".").pop()?.toLowerCase();

  if (ext === "json") {
    const data = JSON.parse(text);
    const rows = Array.isArray(data) ? data : [data];
    const columns = rows.length > 0 ? Object.keys(rows[0]) : [];
    return { columns, rows, rowCount: rows.length };
  }

  if (ext === "csv") {
    const lines = text.trim().split("\n");
    if (lines.length < 2) throw new Error("CSV must have a header row and at least one data row");
    const headers = parseCSVLine(lines[0]);
    const rows = lines.slice(1).map((line) => {
      const values = parseCSVLine(line);
      const row: Record<string, unknown> = {};
      headers.forEach((h, i) => { row[h] = values[i] ?? ""; });
      return row;
    });
    return { columns: headers, rows, rowCount: rows.length };
  }

  throw new Error(`Unsupported file format: .${ext}. Use .json or .csv`);
}
