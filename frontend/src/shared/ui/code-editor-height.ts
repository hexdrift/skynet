// Kept apart from code-editor.tsx so callers that load the editor through
// next/dynamic can size it without pulling CodeMirror into their bundle.
const LINE_HEIGHT_PX = 19.6;
const PADDING_PX = 8;

/** Height that fits a read-only CodeEditor to its content, plus one spare line. */
export function readOnlyEditorHeight(
  code: string,
  opts?: { maxLines?: number; maxPx?: number },
): string {
  let lines = code.split("\n").length + 1;
  if (opts?.maxLines !== undefined) lines = Math.min(lines, opts.maxLines);
  let px = lines * LINE_HEIGHT_PX + PADDING_PX;
  if (opts?.maxPx !== undefined) px = Math.min(px, opts.maxPx);
  return `${px}px`;
}
