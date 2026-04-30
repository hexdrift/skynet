// Hebrew UI strings owned by the compare feature slice. Edit directly.

import { TERMS } from "@/shared/lib/terms";

export const compareMessages = {
  "compare.select_two": `בחרו לפחות שתי ${TERMS.optimizationPlural} מלוח הבקרה כדי להשוות ביניהן`,
  "compare.load_error": `שגיאה בטעינת ה${TERMS.optimizationPlural}`,
  "compare.mismatch": `אפשר להשוות רק ריצות עם אותו סט בדיקה ואותה ${TERMS.metric}`,
  "compare.cap_reached": `ניתן להשוות עד 4 ${TERMS.optimizationPlural} בבת אחת`,
  "compare.partial_load": "חלק מהריצות לא נטענו והושמטו מההשוואה",
} as const;
