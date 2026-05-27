// Hebrew UI strings owned by the compare feature slice. Edit directly.

import { TERMS } from "@/shared/lib/terms";

export const compareMessages = {
  "compare.load_error": `שגיאה בטעינת ה${TERMS.optimizationPlural}`,
  "compare.mismatch": `אפשר להשוות רק ריצות עם אותו סט בדיקה ואותה ${TERMS.metric}`,
  "compare.cap_reached": `ניתן להשוות עד 4 ${TERMS.optimizationPlural} בבת אחת`,
  "compare.partial_load": "חלק מהריצות לא נטענו והושמטו מההשוואה",
  "compare.includes_siblings":
    "{p1, plural, one {השוואה (תוכלל גם ריצה אחת של אותה משימה)} two {השוואה (יוכללו גם שתי ריצות של אותה משימה)} other {השוואה (יוכללו גם # ריצות של אותה משימה)}}",
} as const;
