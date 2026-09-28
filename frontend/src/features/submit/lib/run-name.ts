/**
 * A run name the wizard can suggest without a model call: taken from the
 * Signature's docstring once the user wrote one, else from the dataset file.
 */

/**
 * The first sentence of `text`, trimmed of trailing punctuation and cut at a
 * word boundary past `maxChars`. Empty when the text is blank.
 */
export function suggestedRunName(text: string, maxChars = 60): string {
  const firstLine = text.trim().split(/\r?\n/)[0] ?? "";
  const sentence = /^[^.!?]*[.!?]?/.exec(firstLine)?.[0] ?? firstLine;
  const compact = sentence
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[.!?:;,]+$/u, "");
  if (compact.length <= maxChars) return compact;
  const cut = compact.slice(0, maxChars);
  const lastSpace = cut.lastIndexOf(" ");
  return `${(lastSpace > maxChars / 2 ? cut.slice(0, lastSpace) : cut).trimEnd()}…`;
}

// The placeholder docstring `buildSignatureTemplate` writes; it names nothing.
const TEMPLATE_DOCSTRING = "Describe the task here.";

/** The Signature docstring once it differs from the template, else the dataset file's stem. */
export function suggestedDspyRunName(
  signatureCode: string,
  datasetFileName: string | null,
): string {
  const doc = /"""\s*([^\n"]+)/.exec(signatureCode)?.[1]?.trim() ?? "";
  if (doc && doc !== TEMPLATE_DOCSTRING) return suggestedRunName(doc);
  const stem = (datasetFileName ?? "")
    .replace(/\.[^.]+$/, "")
    .replace(/[_-]+/g, " ")
    .trim();
  return suggestedRunName(stem);
}
