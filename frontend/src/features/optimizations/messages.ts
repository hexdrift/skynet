// Hebrew UI strings owned by the optimizations feature slice. Edit directly.

import { TERMS } from "@/shared/lib/terms";

export const optimizationsMessages = {
  "optimization.cancel.sent": "בקשת ביטול נשלחה",
  "optimization.cancel.failed": "ביטול נכשל",
  "optimization.rerun": "הרצה מחדש",
  "optimization.rerun_tooltip": "הרצה מחדש של האופטימיזציה הזו",
  "optimization.rerun.success": "הרצה חדשה הופעלה",
  "optimization.rerun.failed": "ההרצה מחדש נכשלה",
  "optimization.delete.failed": "מחיקה נכשלה",
  "optimization.file.parse_error": "שגיאה בפענוח הקובץ",
  "optimization.progress.gepa": "אופטימיזציית GEPA",
  "optimizations.react.optimized_tools": "כלים מותאמים (ReAct)",
  "optimizations.react.chat_empty_title": "שיחה עם הסוכן",
  "optimizations.react.chat_empty_desc":
    "שלחו הודעה כדי להפעיל את סוכן ה-ReAct המותאם עם הכלים החיים שלו.",
  "optimizations.react.chat_placeholder": "כתבו הודעה לסוכן…",
  "optimizations.react.chat_send_aria": "שליחת הודעה",
  "optimizations.react.chat_stop_aria": "עצירת השיחה",
  "optimizations.react.chat_retry": "נסו שוב",
  "optimizations.datatab.description": `הנתונים שעליהם רצה ה${TERMS.optimization} — מחולקים ל${TERMS.splitTrain}, ${TERMS.splitVal}, ו${TERMS.splitTest}, עם התוצאות לכל דוגמה.`,
  "optimizations.lmactivity.description": `פעילות מודלי השפה לפי שלב — כמה קריאות בוצעו וכמה זמן לקחו, מה${TERMS.generationModelShort} וממודל הרפלקציה בנפרד.`,
} as const;
