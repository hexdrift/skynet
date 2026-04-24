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
 *     import { msg } from "@/shared/lib/messages";
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

import { TERMS } from "@/shared/lib/terms";

/**
 * Catalog of UI strings keyed by dotted feature path.
 *
 * Keep keys grouped by feature so ownership maps to the feature-slice
 * directory structure.
 */
export const MESSAGES = {
  "submit.validation.username_required": "נא להזין שם משתמש",
  "submit.validation.name_required": `נא להזין שם ל${TERMS.optimization}`,
  "submit.validation.dataset_required": `נא להעלות קובץ ${TERMS.dataset}`,
  "submit.validation.input_column_required": `נא לסמן לפחות ${TERMS.inputColumn} אחת`,
  "submit.validation.output_column_required": `נא לסמן לפחות ${TERMS.outputColumn} אחת`,
  "submit.validation.model_required": `נא לבחור ${TERMS.model}`,
  "submit.validation.reflection_model_required": `נא לבחור ${TERMS.reflectionModel}`,
  "submit.validation.reflection_models_required": `נא להוסיף לפחות ${TERMS.reflectionModel} אחד`,
  "submit.validation.generation_model_required": `נא להוסיף לפחות ${TERMS.generationModel} אחד`,
  "model.generation.label": TERMS.generationModel,
  "model.generation.label_short": TERMS.generationModelShort,
  "model.generation.label_plural": TERMS.generationModelPlural,
  "model.generation.new": `${TERMS.generationModel} חדש`,
  "submit.validation.no_models_available": `אין מודלים זמינים ב${TERMS.modelCatalog} — הגדר ${TERMS.apiKey} של ${TERMS.provider}`,
  "submit.validation.dataset_required_short": `נא להעלות ${TERMS.dataset}`,
  "submit.validation.api_key_required": `נא להזין ${TERMS.apiKey} — אין ב-env ולא הוזן ידנית`,
  "submit.validation.signature_required": `נא להזין קוד ${TERMS.signature}`,
  "submit.validation.metric_required": `נא להזין קוד ${TERMS.metric}`,
  "submit.validation.code_has_errors": "יש שגיאות בקוד — בדוק את הפירוט למטה",
  "submit.validation.dataset_before_code": `נא להעלות ${TERMS.dataset} לפני אימות הקוד`,
  "submit.submit_failed": `שגיאה בשליחת ה${TERMS.optimization}`,
  "submit.code_validation_failed": "שגיאה באימות הקוד",
  "submit.dataset.file_error": "שגיאה בטעינת הקובץ",
  "submit.clone.success": "הגדרות שוכפלו בהצלחה",
  "submit.clone.failed": "שגיאה בטעינת הגדרות לשכפול",
  "submit.split.recommended_title": "ההמלצה שלנו",
  "submit.split.mode_auto": "לפי ההמלצה",
  "submit.split.mode_manual": "אני אבחר",
  "submit.split.rationale_aria": "למה בחרנו את החלוקה הזו",
  "submit.split.rationale_title": "למה חילקנו ככה",
  "submit.split.rationale_description": `החלוקה נבחרה לפי גודל ה${TERMS.dataset}, האיזון בין המחלקות והצרכים של ה${TERMS.optimizer}.`,
  "submit.split.profile_failed": `שגיאה בניתוח ה${TERMS.dataset}`,
  "submit.split.label_train": TERMS.splitTrain,
  "submit.split.label_val": TERMS.splitVal,
  "submit.split.label_test": TERMS.splitTest,
  "submit.probe.asymptote_label": TERMS.expectedScore,
  "submit.probe.observed_label": TERMS.observedScore,
  "submit.probe.observed_hint":
    "לא ניתן היה להכין חיזוי אמין — מוצג הציון הגבוה ביותר שנמדד בפועל במהלך הריצה.",
  "submit.probe.score_label": TERMS.observedScore,
  "submit.probe.signal_weak": "לא ניתן לקבוע",
  "submit.probe.signal_weak_hint":
    "לא נאסף מספיק מידע כדי לחזות את הציון של המודל הזה. מוצג הציון האחרון בפועל.",
  "submit.probe.details.title": `פרטי ${TERMS.optimizationTypeRun}`,
  "submit.probe.details.trajectory": "מסלול ציונים",
  "submit.probe.details.fit_method": "שיטת חיזוי",
  "submit.probe.details.logs": "יומן ריצה",
  "submit.probe.details.points_count": "מדידות",
  "submit.probe.details.toggle_open": "פתח פרטים",
  "submit.probe.details.toggle_close": "סגור פרטים",
  "dashboard.load_error": `שגיאה בטעינת ${TERMS.optimizationPlural}`,
  "dashboard.delete_failed": "מחיקה נכשלה",
  "dashboard.header.title": "לוח בקרה",
  "dashboard.header.jobs_suffix": TERMS.optimizationPlural,
  "dashboard.header.active_suffix": "פעילות",
  "sidebar.delete.success": "נמחק",
  "sidebar.delete.failed": "שגיאה במחיקה",
  "sidebar.link.copied": "קישור הועתק",
  "sidebar.rename.success": "שם עודכן",
  "sidebar.rename.failed": "שגיאה בעדכון שם",
  "sidebar.pin.on": "הוצמד",
  "sidebar.pin.off": "הוסר מהצמדה",
  "sidebar.generic_error": "שגיאה",
  "compare.select_two": `בחר שתי ${TERMS.optimizationPlural} מלוח הבקרה כדי להשוות ביניהן`,
  "compare.load_error": `שגיאה בטעינת ה${TERMS.optimizationPlural}`,
  "compare.mismatch": `להשוואה דרושים אותו ${TERMS.dataset}, אותה ${TERMS.metric} ואותו ${TERMS.signature} — הריצה שנבחרה שונה`,
  "compare.cap_reached": `ניתן להשוות עד 8 ${TERMS.optimizationPlural} בבת אחת`,
  "compare.partial_load": "חלק מהריצות לא נטענו והושמטו מההשוואה",
  "optimization.cancel.sent": "בקשת ביטול נשלחה",
  "optimization.cancel.failed": "ביטול נכשל",
  "optimization.delete.failed": "מחיקה נכשלה",
  "optimization.file.parse_error": "שגיאה בפענוח הקובץ",
  "clipboard.copied": "הועתק בהצלחה",
  "clipboard.copied_short": "הועתק",
  "submit.rec.label": TERMS.recommendation,
  "submit.rec.match_suffix": "התאמה",
  "submit.rec.apply": TERMS.apply,
  "submit.rec.details": "הצג פרטים",
  "submit.rec.hide_details": "הסתר פרטים",
  "submit.rec.dismiss": TERMS.dismiss,
  "submit.rec.applied": "הוחל",
  "submit.rec.cold_title": `אין עדיין ${TERMS.similarRun} — הנה נקודת פתיחה טובה`,
  "submit.rec.cold_body":
    "הגדרות שעובדות טוב על משימות מהסוג הזה בממוצע. אפשר להחיל ולהמשיך לכוונן.",
  "submit.rec.recommendability_tooltip": `מוצגות רק ריצות שעברו את ${TERMS.qualityThreshold}: תוצאה סופית 50+ ו${TERMS.scoreImprovement} של לפחות 5 נק׳ (או 10% מה${TERMS.baseline}).`,
  "submit.rec.apply_failed": "לא ניתן להחיל את ההגדרות",
  "submit.rec.gain_label": TERMS.scoreImprovement,
  "submit.rec.from_to": "מ־{baseline} ל־{optimized}",
  "submit.rec.cold_run_summary": "GEPA עם gpt-4o-mini + ChainOfThought",
  "submit.rec.cold_grid_summary": `${TERMS.optimizationTypeGrid} עם GEPA על 3 מודלים של gpt-4o-mini`,
  "explore.filter.all": "הכל",
  "explore.filter.run": TERMS.optimizationTypeRun,
  "explore.filter.grid": TERMS.optimizationTypeGrid,
  "explore.filter.aria": "סינון סוג ריצה",
  "explore.filter.showing": "מציג {count} מתוך {total}",
  "explore.filter.no_match": "אין ריצות מסוג זה.",
  "explore.filter.clear": "הצג הכל",
  "explore.empty.title": "השדה עדיין ריק. ריצות מופיעות כאן אחרי שמעבדים אותן.",
  "explore.empty.cta": "היה הראשון",
  "explore.detail.task": `ה${TERMS.task}`,
  "explore.detail.model": TERMS.winningModel,
  "explore.detail.optimizer": TERMS.optimizer,
  "explore.detail.score": TERMS.score,
  "explore.detail.time_ago": "לפני",
  "explore.cold_corpus": "השדה עוד קטן. כדאי לחזור אחרי כמה ריצות נוספות.",
  "explore.your_job.caption": "זו הריצה שלך.",
  "explore.detail.empty": "לחצו על נקודה כדי לראות פרטים.",
  "explore.tooltip.open_hint": "לחצו לפרטים",
  "explore.map.reset": "איפוס תצוגה",
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
