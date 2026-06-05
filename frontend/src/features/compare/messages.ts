// Hebrew UI strings owned by the compare feature slice. Edit directly.

import { TERMS } from "@/shared/lib/terms";

export const compareMessages = {
  "compare.load_error": `שגיאה בטעינת ${TERMS.optimizationPlural}`,
  "compare.mismatch": `אפשר להשוות רק ריצות מאותו סט בדיקה ועם אותה ${TERMS.metric}`,
  "compare.cap_reached": `ניתן להשוות עד 4 ${TERMS.optimizationPlural} בבת אחת`,
  "compare.partial_load": "חלק מהריצות לא נטענו ולכן לא נכללו בהשוואה",
  "compare.includes_siblings":
    "{p1, plural, one {השוואה (תכלול גם ריצה אחת מאותה משימה)} two {השוואה (תכלול גם שתי ריצות מאותה משימה)} other {השוואה (תכלול גם # ריצות מאותה משימה)}}",
} as const;
