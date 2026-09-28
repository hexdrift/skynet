/**
 * Arrow-key paging shared by every carousel and prev/next pager, so ← and →
 * traverse slides the same way everywhere: the arrow pointing toward the
 * inline-end edge is forward (→ in LTR, ← in RTL), and a key typed into a
 * text field never pages.
 */

type ArrowKeyEvent = { key: string; target: EventTarget | null };

/**
 * True when a keyboard event comes from a text-editing surface — an input,
 * textarea, select or contenteditable (CodeMirror's editor included) — where
 * the arrow keys move the caret and must be left alone.
 */
export function isEditableTarget(target: EventTarget | null): boolean {
  const el = target as { tagName?: string; isContentEditable?: boolean } | null;
  if (!el?.tagName) return false;
  return (
    el.tagName === "INPUT" ||
    el.tagName === "TEXTAREA" ||
    el.tagName === "SELECT" ||
    el.isContentEditable === true
  );
}

/**
 * The step an arrow key asks a pager for: +1 when it points toward the
 * inline-end edge, -1 toward inline-start, 0 for any other key or while
 * typing. Pass ``rtl: false`` for a pager whose own layout is pinned
 * left-to-right whatever the locale, so ← is always previous there.
 */
export function arrowPageStep(event: ArrowKeyEvent, rtl: boolean): 1 | -1 | 0 {
  if (isEditableTarget(event.target)) return 0;
  const forwardKey = rtl ? "ArrowLeft" : "ArrowRight";
  const backKey = rtl ? "ArrowRight" : "ArrowLeft";
  if (event.key === forwardKey) return 1;
  if (event.key === backKey) return -1;
  return 0;
}
