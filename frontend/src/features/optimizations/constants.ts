/**
 * Constants for the optimization detail page.
 *
 * Extracted from app/optimizations/[id]/page.tsx as a partial split —
 * full decomposition of the 2735-line page is a dedicated follow-up
 * (audit #13). These constants are pure data and safe to move first.
 */

export const STATUS_COLORS: Record<string, string> = {
  pending: "status-pill-pending",
  validating: "status-pill-running",
  running: "status-pill-running",
  success: "status-pill-success",
  failed: "status-pill-failed",
  cancelled: "status-pill-cancelled",
};

export type PipelineStage =
  | "validating"
  | "splitting"
  | "baseline"
  | "optimizing"
  | "evaluating"
  | "done";

export const PIPELINE_STAGES: { key: PipelineStage; label: string }[] = [
  { key: "validating", label: "אימות" },
  { key: "splitting", label: "חלוקת נתונים" },
  { key: "baseline", label: "ציון התחלתי" },
  { key: "optimizing", label: "אופטימיזציה" },
  { key: "evaluating", label: "הערכה" },
];

export const STAGE_INFO: Record<string, { title: string; description: string; details: string }> = {
  validating: {
    title: "אימות הקלט",
    description: "בדיקה שכל הרכיבים תקינים לפני תחילת האופטימיזציה.",
    details: "חתימת הקלט והפלט נבדקת מול מיפוי העמודות בדאטאסט. פונקציית המדידה נטענת ומאומתת. המודול והאופטימייזר נבדקים לתאימות. אם נמצאת שגיאה — האופטימיזציה נעצרת כאן.",
  },
  splitting: {
    title: "חלוקת הנתונים",
    description: "הדאטאסט מחולק לשלוש קבוצות: אימון, אימות ובדיקה.",
    details: "השורות מעורבבות באופן אקראי עם ערך מספרי התחלתי קבוע כדי להבטיח תוצאות זהות בכל הרצה. לאחר מכן הן מחולקות לפי היחסים שהוגדרו. סט הבדיקה נשמר בצד ולא משתתף בתהליך האופטימיזציה.",
  },
  baseline: {
    title: "מדידת ציון בסיס",
    description: "הרצת התוכנית ללא אופטימיזציה על סט הבדיקה.",
    details: "התוכנית רצה כפי שהיא — ללא prompt engineering או דוגמאות — על כל דוגמה בסט הבדיקה. פונקציית המדידה מחשבת ציון לכל דוגמה, והממוצע הוא ציון הבסיס. ציון זה משמש כנקודת השוואה לשיפור שהאופטימיזציה מביאה.",
  },
  optimizing: {
    title: "אופטימיזציה",
    description: "האופטימייזר משפר את התוכנית באמצעות סט האימון.",
    details: "האופטימייזר מנסה שילובים שונים של הנחיות, דוגמאות נבחרות והוראות כדי למקסם את ציון המדידה על סט האימות. כל ניסיון מריץ את התוכנית עם הגדרה שונה ומודד את התוצאה. בסיום נבחרת הגרסה הטובה ביותר.",
  },
  evaluating: {
    title: "הערכה סופית",
    description: "הרצת התוכנית המשופרת על סט הבדיקה.",
    details: "התוכנית המשופרת רצה על סט הבדיקה — אותן דוגמאות שנמדדו בשלב הבסיס. ההשוואה בין הציונים מראה את השיפור בפועל. אם התוכנית המשופרת גרועה יותר מהמקורית, המערכת שומרת את התוכנית המקורית.",
  },
};
