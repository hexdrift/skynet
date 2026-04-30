// Resize a textarea to fit its content, clamped to `maxHeight` pixels.
// Used by every chat composer and inline editor in the app — the cap mirrors
// the `max-h-[120px]` in their Tailwind classnames so the scroll only kicks
// in once the textarea has actually grown to that ceiling.
export function autoResizeTextarea(el: HTMLTextAreaElement | null, maxHeight = 120): void {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
}
