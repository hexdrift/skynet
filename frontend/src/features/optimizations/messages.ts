// Hebrew UI strings owned by the optimizations feature slice. Edit directly.

import { TERMS } from "@/shared/lib/terms";

export const optimizationsMessages = {
  "optimization.cancel.sent": "בקשת ביטול נשלחה",
  "optimization.cancel.failed": "ביטול נכשל",
  "optimization.rerun": "הרץ/הריצי שוב",
  "optimization.rerun_tooltip": "צור/צרי אופטימיזציה חדשה על בסיס זו",
  "optimization.rerun.success": "נוצרה אופטימיזציה חדשה",
  "optimization.rerun.failed": "לא ניתן ליצור אופטימיזציה חדשה",
  "optimization.delete.failed": "מחיקה נכשלה",
  "optimization.file.parse_error": "שגיאה בפענוח הקובץ",
  "optimization.progress.gepa": "אופטימיזציית GEPA",
  "optimizations.react.optimized_tools": "כלים מותאמים (ReAct)",
  "optimizations.react.chat_empty_title": "שיחה עם הסוכן",
  "optimizations.react.chat_empty_desc":
    "שלח/שלחי הודעה כדי להתחיל שיחה עם סוכן ה-ReAct המותאם והכלים הזמינים לו.",
  "optimizations.react.chat_placeholder": "כתוב/כתבי הודעה לסוכן…",
  "optimizations.react.chat_send_aria": "שלח/שלחי הודעה",
  "optimizations.react.chat_stop_aria": "עצור/עצרי את השיחה",
  "optimizations.react.chat_retry": "נסה/נסי שוב",
  "optimizations.react.api_title": "API של השירות",
  "optimizations.logs.verbosity.aria": "רמת פירוט היומנים",
  "optimizations.logs.verbosity.quiet": "שקט",
  "optimizations.logs.verbosity.normal": "רגיל",
  "optimizations.logs.verbosity.verbose": "מפורט",
  "optimizations.logs.verbosity.empty_quiet": "אין אזהרות או שגיאות בריצה זו",
  "optimizations.logs.verbosity.empty_filtered": "אין יומנים התואמים לסינון",
  "optimizations.datatab.description": `הנתונים ששימשו ב${TERMS.optimization} — מחולקים ל${TERMS.splitTrain}, ${TERMS.splitVal} ו${TERMS.splitTest}, עם התוצאות לכל דוגמה.`,
  "optimizations.lmactivity.description": `פעילות מודלי השפה לפי שלב — כמה קריאות היו וכמה זמן הן לקחו, ל${TERMS.generationModelShort} ולמודל הרפלקציה בנפרד.`,
} as const;
