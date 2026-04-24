/**
 * Constants for the optimization detail page.
 *
 * Extracted from app/optimizations/[id]/page.tsx as a partial split —
 * full decomposition of the 2735-line page is a dedicated follow-up
 * (audit #13). These constants are pure data and safe to move first.
 */

import { TERMS } from "@/shared/lib/terms";

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
  { key: "baseline", label: TERMS.baselineScore },
  { key: "optimizing", label: TERMS.optimization },
  { key: "evaluating", label: "הערכה" },
];

export const STAGE_INFO: Record<string, { title: string; description: string; details: string }> = {
  validating: {
    title: "אימות הקלט",
    description: `בדיקה שכל הרכיבים תקינים לפני תחילת ה${TERMS.optimization}.`,
    details: `ה${TERMS.signature} של הקלט והפלט נבדק מול מיפוי העמודות ב${TERMS.dataset}. ${TERMS.metric} נטענת ומאומתת. ה${TERMS.module} וה${TERMS.optimizer} נבדקים לתאימות. אם נמצאת שגיאה — ה${TERMS.optimization} נעצרת כאן.`,
  },
  splitting: {
    title: "חלוקת הנתונים",
    description: `ה${TERMS.dataset} מחולק לשלושה סטים: ${TERMS.splitTrain}, ${TERMS.splitVal} ו${TERMS.splitTest}.`,
    details: `השורות מעורבבות באופן אקראי עם ערך התחלתי קבוע כדי להבטיח תוצאות זהות בכל ${TERMS.optimizationTypeRun}. לאחר מכן הן מחולקות לפי היחסים שהוגדרו. סט הבדיקה נשמר בצד ולא משתתף בתהליך ה${TERMS.optimization}.`,
  },
  baseline: {
    title: `מדידת ${TERMS.baselineScore}`,
    description: `הרצת ה${TERMS.program} ללא ${TERMS.optimization} על סט הבדיקה.`,
    details: `ה${TERMS.program} רצה כפי שהיא — ללא prompt engineering או דוגמאות — על כל ${TERMS.example} בסט הבדיקה. ${TERMS.metric} מחשבת ${TERMS.score} לכל ${TERMS.example}, והממוצע הוא ${TERMS.baselineScore}. ציון זה משמש כנקודת השוואה ל${TERMS.scoreImprovement} שה${TERMS.optimization} מביאה.`,
  },
  optimizing: {
    title: TERMS.optimization,
    description: `ה${TERMS.optimizer} משפר את ה${TERMS.program} באמצעות סט האימון.`,
    details: `ה${TERMS.optimizer} מנסה שילובים שונים של הנחיות, דוגמאות נבחרות והוראות כדי למקסם את ציון המדידה על סט האימות. כל ניסיון מריץ את ה${TERMS.program} עם הגדרה שונה ומודד את התוצאה. בסיום נבחרת הגרסה הטובה ביותר.`,
  },
  evaluating: {
    title: "הערכה סופית",
    description: `הרצת ה${TERMS.program} המשופרת על סט הבדיקה.`,
    details: `ה${TERMS.program} המשופרת רצה על סט הבדיקה — אותן דוגמאות שנמדדו בשלב ה${TERMS.baseline}. ההשוואה בין הציונים מראה את ה${TERMS.scoreImprovement} בפועל. אם ה${TERMS.program} המשופרת גרועה יותר מהמקורית, המערכת שומרת את ה${TERMS.program} המקורית.`,
  },
};
