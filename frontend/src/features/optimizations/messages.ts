// Hebrew UI strings owned by the optimizations feature slice. Edit directly.

import { TERMS } from "@/shared/lib/terms";

export const optimizationsMessages = {
  "optimization.cancel.sent": "בקשת ביטול נשלחה",
  "optimization.cancel.failed": "ביטול נכשל",
  "optimization.rerun": "הריצו שוב",
  "optimization.rerun_tooltip": "צרו אופטימיזציה חדשה על בסיס זו",
  "optimization.rerun.success": "נוצרה אופטימיזציה חדשה",
  "optimization.rerun.failed": "לא הצלחנו ליצור אופטימיזציה חדשה",
  "optimization.delete.failed": "מחיקה נכשלה",
  "optimization.file.parse_error": "שגיאה בפענוח הקובץ",
  "optimization.progress.gepa": "אופטימיזציית GEPA",
  "optimizations.react.optimized_tools": "כלים מותאמים (ReAct)",
  "optimizations.react.chat_empty_title": "שיחה עם הסוכן",
  "optimizations.react.chat_empty_desc":
    "שלחו הודעה כדי להתחיל שיחה עם סוכן ה-ReAct המותאם והכלים הזמינים לו.",
  "optimizations.react.chat_placeholder": "כתבו הודעה לסוכן…",
  "optimizations.react.chat_send_aria": "שלחו הודעה",
  "optimizations.react.chat_stop_aria": "עצרו את השיחה",
  "optimizations.react.chat_retry": "נסו שוב",
  "optimizations.react.api_title": "API של השירות",
  "optimizations.react.api_desc":
    "שלחו בקשות API לסוכן ה-ReAct המותאם. נקודת הקצה מחזירה את תשובת הסוכן בזרם SSE.",
  "optimizations.datatab.description": `הנתונים ששימשו ב${TERMS.optimization} — מחולקים ל${TERMS.splitTrain}, ${TERMS.splitVal} ו${TERMS.splitTest}, עם התוצאות לכל דוגמה.`,
  "optimizations.lmactivity.description": `פעילות מודלי השפה לפי שלב — כמה קריאות היו וכמה זמן הן לקחו, ל${TERMS.generationModelShort} ולמודל הרפלקציה בנפרד.`,
} as const;
