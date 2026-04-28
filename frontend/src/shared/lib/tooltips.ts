/**
 * Centralized Hebrew tooltip copy.
 *
 * Tooltips that describe the same concept should share a single string.
 * Call sites import `tip(key)` and pass the result to <HelpTip text={...}>.
 *
 *     import { tip } from "@/shared/lib/tooltips";
 *     <HelpTip text={tip("score.baseline")}>ציון בסיס</HelpTip>
 *
 * Keys are grouped by domain concept, not by feature slice — the same
 * definition of "ציון בסיס" should read identically on the overview
 * tab, the pair detail view, and the compare page.
 */

import { TERMS } from "@/shared/lib/terms";

export const TOOLTIPS = {
  "score.baseline": `${TERMS.baselineScore} לפני ${TERMS.optimization} — ה${TERMS.program} רצה ללא הנחיות או דוגמאות`,
  "score.optimized": `${TERMS.optimizedScore} אחרי ${TERMS.optimization} — ה${TERMS.program} רצה עם ההנחיות והדוגמאות שנבחרו`,
  "score.improvement": `ההפרש בין ה${TERMS.optimizedScore} ל${TERMS.baselineScore} — ככל שגבוה יותר, ה${TERMS.optimization} הועילה יותר`,
  "score.progression": `שינוי ה${TERMS.score} לאורך הניסיונות השונים של ה${TERMS.optimizer}`,

  "lm.calls_count": `מספר הפעמים שהמערכת פנתה ל${TERMS.model} השפה במהלך ה${TERMS.optimization}`,
  "lm.avg_response_time": `משך זמן ממוצע לכל קריאה בודדת ל${TERMS.model} השפה`,

  "model.generation": `ה${TERMS.model} שמייצר את הפלט — מבצע את ה${TERMS.task} בפועל בזמן ה${TERMS.optimizationTypeRun}`,
  "model.reflection": `ה${TERMS.model} שבוחן את הפלטים ומציע שיפורים להנחיות במהלך ה${TERMS.optimization}`,

  "data.split_explanation": `הנתונים מחולקים לשלושה סטים — ${TERMS.splitTrain} ללמידה, ${TERMS.splitVal} לכיוונון, ו${TERMS.splitTest} למדידת הביצועים הסופיים`,
  "data.shuffle_explanation": `ערבוב סדר השורות ב${TERMS.dataset} לפני ה${TERMS.split} — מונע הטיה מסדר הנתונים`,
  "data.split.train": `דוגמאות שה${TERMS.optimizer} לומד מהן`,
  "data.split.val": `דוגמאות לכיוונון פנימי במהלך ה${TERMS.optimization}`,
  "data.split.test": "דוגמאות שמורות למדידה סופית — לא נחשפות באימון",
  "data.seed": `מספר קבוע שמבטיח שהערבוב והחלוקה יהיו זהים בכל ${TERMS.optimizationTypeRun} חוזרת`,

  "prompt.optimized": `הפרומפט שנבנה אוטומטית ע״י ה${TERMS.optimizer} — כולל הנחיות ודוגמאות שנבחרו`,
  "prompt.demonstrations": `דוגמאות קלט-פלט שנבחרו מה${TERMS.dataset} ומוצגות ל${TERMS.model} כדי ללמד אותו את הפורמט הרצוי`,
  "prompt.instructions": `ההנחיות שה${TERMS.optimizer} יצר ל${TERMS.model} — מתארות את ה${TERMS.task} ואיך לבצע אותה`,

  "module.choice": "אופן עיבוד הפרומפט — Predict שולח ישירות, CoT מוסיף שלב חשיבה לפני התשובה",
  "optimizer.choice": `אלגוריתם ה${TERMS.optimization} שמשפר את הפרומפט`,
  "optimizer.gepa": `אלגוריתם ה${TERMS.optimization} GEPA — משפר הוראות דרך רפלקציה על שגיאות`,

  "config.section.summary": `ה${TERMS.module}, ה${TERMS.optimizer}, והפרמטרים שנבחרו ל${TERMS.optimizationTypeRun} זו`,
  "config.section.models": `מודלי השפה שהוגדרו — ${TERMS.generationModelShort} לייצור תשובות, רפלקציה לניתוח שגיאות`,
  "config.section.data": `חלוקת ה${TERMS.dataset} ל${TERMS.splitTrain}, ${TERMS.splitVal} ו${TERMS.splitTest}, והגדרות ערבוב`,

  "grid.generation_models": `המודלים שמייצרים את התשובות — כל ${TERMS.pair} נבדק עם ${TERMS.generationModel} שונה`,
  "grid.reflection_models": `המודלים שמנתחים שגיאות ומציעים שיפורים — כל ${TERMS.pair} נבדק עם ${TERMS.reflectionModel} שונה`,
  "grid.score_comparison": `השוואת ${TERMS.baselineScore} וה${TERMS.optimizedScore} לכל ${TERMS.pair} מודלים`,
  "grid.quality_speed_combined":
    "איכות ומהירות לכל זוג מודלים, זה לצד זה. ככל שהאיכות והמהירות גבוהות יותר, כך הזוג טוב יותר.",
  "grid.avg_response_time_per_pair": "משך זמן ממוצע לכל קריאה למודל שפה, לפי זוג מודלים",
  "grid.best_pair_default":
    "ברירת מחדל: הזוג עם ציון האיכות הגבוה ביותר. ניתן להחליף לכל זוג אחר.",

  "pair.runtime": `משך ${TERMS.optimizationTypeRun} ה${TERMS.optimization} עבור ${TERMS.pair} המודלים הזה`,

  "serve.section_pair": "כתובת API וקוד לשילוב הזוג הנבחר באפליקציה שלך",
  "serve.section_run": `כתובת API וקוד לשילוב ה${TERMS.program} המאומנת באפליקציה שלך`,
  "serve.api_url_pair": "כתובת ה-API של הזוג הנבחר",
  "serve.api_url_run": `כתובת ה-API שאליה שולחים בקשות POST עם שדות הקלט כדי לקבל ${TERMS.prediction} מה${TERMS.program} המאומנת`,
  "serve.integration_code": "דוגמאות קוד מוכנות להעתקה",

  "submit.depth":
    "עומק החיפוש — קלה מהירה עם פחות ניסיונות, מעמיקה בודקת יותר שילובים אך לוקחת זמן רב יותר",
  "submit.reflection_minibatch": `כמה דוגמאות ה${TERMS.model} מנתח בכל סבב רפלקציה כדי לזהות דפוסי שגיאה`,
  "submit.eval_rounds": "מספר הפעמים שהמערכת מריצה הערכה מלאה על כל הנתונים",
  "submit.merge": "כשפעיל, המערכת משלבת הוראות מכמה מועמדים טובים לפרומפט אחד משופר",

  "model_config.temperature": `מידת היצירתיות של ה${TERMS.model} — ערך נמוך נותן תשובות עקביות, גבוה מגוון יותר`,
  "model_config.top_p": `מגביל את מגוון המילים שה${TERMS.model} שוקל — ערך נמוך ממקד, גבוה מאפשר יותר מגוון`,
  "model_config.max_tokens": `אורך ה${TERMS.prediction} המקסימלי — טוקן הוא בערך מילה אחת`,

  "code.signature_metric": `קוד המקור של ה${TERMS.signature} ו${TERMS.metric} שהוגדרו ל${TERMS.optimization} זו`,
  "code.signature": `הגדרת שדות הקלט והפלט של ה${TERMS.task} — מה ה${TERMS.model} מקבל ומה הוא צריך להחזיר`,
  "code.metric": `פונקציה שמודדת את איכות ה${TERMS.prediction} — מחזירה ${TERMS.score} מספרי לכל ${TERMS.example}`,
  "code.predictions_table": `תוצאות הרצת ה${TERMS.program} על דוגמאות הבדיקה — ${TERMS.score} לכל ${TERMS.example} וסיכום כולל`,

  "tagger.upload_file": "העלה קובץ CSV, JSON או Excel — כל שורה תהפוך לטקסט לתיוג",
  "tagger.text_column": "בחר את העמודה שמכילה את הטקסטים לתיוג — שאר העמודות יישמרו בייצוא",
  "tagger.mode": "בחר את סוג התיוג המתאים למשימה — סיווג בינארי, בחירה מרשימה, או כתיבת טקסט חופשי",
  "tagger.binary_question":
    "השאלה שתוצג מעל כפתורי כן/לא — נסח שאלה ברורה שאפשר לענות עליה בכן או לא",
  "tagger.multiclass_categories": "הגדר את הקטגוריות הזמינות לבחירה בזמן התיוג — לפחות שתיים",
  "tagger.freetext_instruction": "ההנחיה שתוצג מעל שדה הטקסט — עזור למתייג להבין מה לכתוב",

  "compare.detail": `השוואה מפורטת בין שתי ${TERMS.optimizationTypeRunPlural} — ציונים, הגדרות, ופרומפטים`,
  "compare.scores_section": `ציוני המדידה לפני ואחרי ה${TERMS.optimization} לכל ${TERMS.optimizationTypeRun}`,
  "compare.config_section": `השוואת ההגדרות שנבחרו לכל ${TERMS.optimizationTypeRun} — ${TERMS.model}, ${TERMS.optimizer}, ונתונים`,
  "compare.per_example": "השוואה ברמת הדוגמה — לכל פריט בסט הבדיקה, מי עבר (ירוק) ומי נכשל (אדום)",
  "compare.winner_improvement": `אחוז ה${TERMS.scoreImprovement} של ה${TERMS.optimizationTypeRun} הזוכה — ההפרש בין ה${TERMS.optimizedScore} ל${TERMS.baselineScore}`,
  "compare.winner_runtime": `משך הזמן הכולל של ה${TERMS.optimizationTypeRun} הזוכה, מרגע השיגור ועד סיום ה${TERMS.optimization}`,
  "compare.winner_models": `זוג מודלי השפה של ה${TERMS.optimizationTypeRun} הזוכה — ${TERMS.generationModel} שמייצר פלט, ו${TERMS.reflectionModel} שמשפר את ההנחיות`,

  "analytics.score_comparison": `השוואת ${TERMS.baselineScore} מול ה${TERMS.optimizedScore} לכל ${TERMS.optimization} שהושלמה`,
  "analytics.runtime_vs_gain": `ניתוח זמני ${TERMS.optimizationTypeRun} ויעילות — כמה שיפור מתקבל ביחס לזמן`,
  "analytics.runtime_minutes": `משך ה${TERMS.optimizationTypeRun} בדקות לכל ${TERMS.optimization} שהושלמה`,
  "analytics.improvement_per_minute": `אחוזי ${TERMS.scoreImprovement} לכל דקת ${TERMS.optimizationTypeRun} — ערך גבוה משמעו ${TERMS.optimization} יעילה יותר`,
  "analytics.dataset_size_vs_improvement": `האם יותר נתונים מובילים ל${TERMS.scoreImprovement} טוב יותר — כל נקודה היא ${TERMS.optimization} אחת`,
  "analytics.submissions_per_day": `מספר ה${TERMS.optimizationPlural} שהוגשו לפי יום`,
  "analytics.optimizer_avg_improvement": `${TERMS.scoreImprovement} ממוצע באחוזים שכל ${TERMS.optimizer} השיג על פני כל ה${TERMS.optimizationTypeRunPlural}`,
  "analytics.top_improvements": `ה${TERMS.optimizationTypeRunPlural} שהשיגו את השיפור הגדול ביותר בציון, מהטוב לפחות טוב`,
  "analytics.optimizer_comparison_table": `השוואה מפורטת בין ה${TERMS.optimizerPlural}: שיפור ממוצע, מספר ${TERMS.optimizationTypeRunPlural}, וזמן ${TERMS.optimizationTypeRun}`,
  "analytics.model_performance_table": "ביצועי המודלים השונים: תדירות שימוש ושיפור ממוצע",
} as const;

export type TooltipKey = keyof typeof TOOLTIPS;

/**
 * Look up tooltip copy by key. Silently returns the key itself if not
 * found, so missing entries surface as a dev-visible artifact rather
 * than a blank tooltip.
 */
export function tip(key: TooltipKey): string {
  return TOOLTIPS[key] ?? key;
}
