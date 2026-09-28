/**
 * Pure formatters for the explore slice.
 */

import { getActiveIntlLocale } from "@/shared/lib/runtime-locale";

// DSPy runs store the optimizer alias the user submitted ("gepa") or a dotted
// import path; only the registered aliases get a display label, anything else
// passes through verbatim.
const OPTIMIZER_LABELS: Record<string, string> = {
  gepa: "GEPA",
};

/** Human label for an optimizer identifier as stored in the corpus. */
export function optimizerDisplayName(raw: string | null | undefined): string {
  if (!raw) return "";
  return OPTIMIZER_LABELS[raw.trim().toLowerCase()] ?? raw;
}

/**
 * Exact calendar date of a run, in the active UI locale but always on the
 * Gregorian calendar. Medium style with the year always shown, e.g.
 * "Sep 12, 2026". Returns "—" for missing/unparseable input.
 *
 * The `gregory` calendar is pinned deliberately: some locales (Persian, and
 * a few Arabic regions) default `Intl` to a non-Gregorian calendar, so
 * without it the same run would show a different date per locale.
 */
export function formatExactDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(getActiveIntlLocale(), {
    dateStyle: "medium",
    calendar: "gregory",
  });
}
