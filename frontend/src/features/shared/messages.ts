/**
 * Centralized Hebrew UI strings.
 *
 * Seeded as the landing pad for the i18n layer (P2 #23 in the audit).
 * Every call to toast.error/success and every hard-coded Hebrew label
 * in a feature slice should eventually move here.
 *
 * The API is intentionally minimal: a flat keyed object with a typed
 * helper. When real i18n is needed, swap this for an i18next/paraglide/
 * react-intl binding without touching call sites.
 *
 *     import { msg } from "@/features/shared/messages";
 *     toast.error(msg("submission.failed"));
 *
 * Migration status (2026-04-10): all static toast strings across submit,
 * dashboard, sidebar, optimizations/[id] and DataTab now use msg(). Two
 * sites remain hard-coded because they need interpolation or JSX:
 *   - use-submit-wizard.ts:437   `נטען ${n} שורות מ-${file}` (needs
 *     parameterised template support in the catalog)
 *   - optimizations/[id]/page.tsx:1204  `<div>נא למלא…{missing.join(",")}</div>`
 *     (JSX toast with a runtime array)
 * When real i18next/paraglide is adopted, both can move to a parameterised
 * ICU message and the inline literals can be removed.
 */

/**
 * Catalog of UI strings keyed by dotted feature path.
 *
 * Keep keys grouped by feature so ownership maps to the feature-slice
 * directory structure.
 */
export const MESSAGES = {
  // ── submit wizard ────────────────────────────────────────────────────
  "submit.validation.username_required": "נא להזין שם משתמש",
  "submit.validation.name_required": "נא להזין שם לאופטימיזציה",
  "submit.validation.dataset_required": "נא להעלות קובץ דאטאסט",
  "submit.validation.input_column_required": "נא לסמן לפחות עמודת קלט אחת",
  "submit.validation.output_column_required": "נא לסמן לפחות עמודת פלט אחת",
  "submit.validation.model_required": "נא לבחור מודל",
  "submit.validation.reflection_model_required": "נא לבחור מודל רפלקציה",
  "submit.validation.reflection_models_required": "נא להוסיף לפחות מודל רפלקציה אחד",
  "submit.validation.generation_model_required": "נא להוסיף לפחות מודל יצירה אחד",
  "submit.validation.dataset_required_short": "נא להעלות דאטאסט",
  "submit.validation.api_key_required": "נא להזין מפתח API — אין ב-env ולא הוזן ידנית",
  "submit.validation.signature_required": "נא להזין קוד חתימה",
  "submit.validation.metric_required": "נא להזין קוד Metric",
  "submit.validation.code_has_errors": "יש שגיאות בקוד — בדוק את הפירוט למטה",
  "submit.validation.dataset_before_code": "נא להעלות דאטאסט לפני אימות הקוד",
  "submit.submit_failed": "שגיאה בשליחת האופטימיזציה",
  "submit.code_validation_failed": "שגיאה באימות הקוד",
  "submit.dataset.file_error": "שגיאה בטעינת הקובץ",
  "submit.clone.success": "הגדרות שוכפלו בהצלחה",
  "submit.clone.failed": "שגיאה בטעינת הגדרות לשכפול",

  // ── dashboard ────────────────────────────────────────────────────────
  "dashboard.load_error": "שגיאה בטעינת אופטימיזציות",
  "dashboard.delete_failed": "מחיקה נכשלה",
  "dashboard.header.title": "לוח בקרה",
  "dashboard.header.jobs_suffix": "אופטימיזציות",
  "dashboard.header.active_suffix": "פעילות",

  // ── sidebar ──────────────────────────────────────────────────────────
  "sidebar.delete.success": "נמחק",
  "sidebar.delete.failed": "שגיאה במחיקה",
  "sidebar.link.copied": "קישור הועתק",
  "sidebar.rename.success": "שם עודכן",
  "sidebar.rename.failed": "שגיאה בעדכון שם",
  "sidebar.pin.on": "הוצמד",
  "sidebar.pin.off": "הוסר מהצמדה",
  "sidebar.generic_error": "שגיאה",

  // ── compare ──────────────────────────────────────────────────────────
  "compare.select_two": "בחר שתי אופטימיזציות מלוח הבקרה כדי להשוות ביניהן",
  "compare.load_error": "שגיאה בטעינת האופטימיזציות",

  // ── optimization detail ──────────────────────────────────────────────
  "optimization.cancel.sent": "בקשת ביטול נשלחה",
  "optimization.cancel.failed": "ביטול נכשל",
  "optimization.delete.failed": "מחיקה נכשלה",
  "optimization.file.parse_error": "שגיאה בפענוח הקובץ",

  // ── clipboard / generic ──────────────────────────────────────────────
  "clipboard.copied": "הועתק בהצלחה",
  "clipboard.copied_short": "הועתק",
} as const;

export type MessageKey = keyof typeof MESSAGES;

/**
 * Look up a user-facing string by key. Silently returns the key itself
 * if not found so missing messages surface as a dev-visible "key not
 * translated" artifact instead of a silent blank.
 */
export function msg(key: MessageKey): string {
  return MESSAGES[key] ?? key;
}
