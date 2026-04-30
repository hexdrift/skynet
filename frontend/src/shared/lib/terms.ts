/**
 * Canonical Hebrew vocabulary for Skynet.
 *
 * Source of truth for the TERMS map: ``i18n/locales/he.json`` (under
 * ``terms``) and ``i18n/glossary.yml``. UI message strings are NOT
 * sourced from here — they live in the per-feature slice files under
 * ``frontend/src/features/<name>/messages.ts`` and are hand-edited.
 *
 * Hebrew copy should use gender-neutral plural imperatives: "לחצו", "בחרו",
 * "ראו". Avoid slash forms such as "לחצ/י" or "ראי/ה".
 *
 * Keep established borrowed ML terms: "אופטימיזציה", "אופטימייזר",
 * "דאטאסט", and "מודול". Use native Hebrew only for the owner-approved
 * exceptions: baseline -> "בסיס" / "תוצאות בסיס", and metric ->
 * "פונקציית מדידה".
 *
 * Any block that holds user-generated text, model identifiers (`openai/...`),
 * numbers, or code should set `dir="ltr"`. The app shell is RTL by default.
 *
 * Adding a new term:
 * 1. Edit i18n/locales/he.json and i18n/glossary.yml.
 * 2. Run `python scripts/generate_i18n.py`.
 * 3. Reference `TERMS.<key>` from messages, tooltips, constants, and copy
 *    catalogs instead of hardcoding the Hebrew term.
 * 4. Grep for hardcoded variants and migrate or document any deliberate
 *    exceptions in the same change.
 */
export { TERMS } from "./generated/i18n-catalog";
export type { TermKey } from "./generated/i18n-catalog";
