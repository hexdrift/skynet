/**
 * Relative date ranges for the explore date filter. The filter itself stores
 * absolute calendar days in the URL, so a preset resolves to concrete days
 * when picked and is recognized again by resolving it against today.
 */

export const DATE_PRESETS = [7, 30, 90] as const;
export type DatePresetDays = (typeof DATE_PRESETS)[number];

export interface DayRange {
  from: string;
  to: string;
}

/** The calendar day of `date` in the local zone, as YYYY-MM-DD. */
export function isoDay(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/** The last `days` calendar days ending today, both ends inclusive. */
export function lastDaysRange(days: number, today: Date = new Date()): DayRange {
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - (days - 1));
  return { from: isoDay(start), to: isoDay(today) };
}

/** The preset a stored range means as of today, or null for a custom range. */
export function matchingPreset(
  from: string | null,
  to: string | null,
  today: Date = new Date(),
): DatePresetDays | null {
  if (!from || !to) return null;
  return DATE_PRESETS.find((days) => {
    const range = lastDaysRange(days, today);
    return range.from === from && range.to === to;
  }) ?? null;
}
