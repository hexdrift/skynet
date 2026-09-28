/** Return the next radio in reading order, or leave unrelated keys alone. */
export function radioNavigationIndex(
  key: string,
  index: number,
  count: number,
  rtl: boolean,
): number | null {
  if (count < 1) return null;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(key)) return null;
  const backward = key === "ArrowUp" || key === (rtl ? "ArrowRight" : "ArrowLeft");
  return (index + (backward ? -1 : 1) + count) % count;
}
