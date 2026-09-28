/**
 * Move focus to a wizard field after a stage switch. The stage view animates
 * in, so the lookup retries across frames until the target mounts. The id is
 * either a DOM id or a `data-tutorial` handle; a container moves focus to its
 * first focusable control.
 */
const FOCUSABLE = "input, textarea, select, button, [tabindex], [contenteditable=true]";
const MAX_FRAMES = 30;

export function focusField(id: string): void {
  if (typeof window === "undefined") return;
  let frames = 0;
  const focus = () => {
    const element =
      document.getElementById(id) ?? document.querySelector(`[data-tutorial="${CSS.escape(id)}"]`);
    if (!(element instanceof HTMLElement)) {
      if (++frames < MAX_FRAMES) window.requestAnimationFrame(focus);
      return;
    }
    const target = element.matches(FOCUSABLE)
      ? element
      : (element.querySelector<HTMLElement>(FOCUSABLE) ?? element);
    if (!target.hasAttribute("tabindex") && target === element) target.tabIndex = -1;
    element.scrollIntoView({
      block: "center",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
    target.focus({ preventScroll: true });
  };
  window.requestAnimationFrame(focus);
}
