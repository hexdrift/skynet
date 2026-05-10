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
  "score.baseline": `${TERMS.baselineScore} לפני ${TERMS.optimization}: איך ה${TERMS.program} הצליחה בלי פרומפט משופר או דוגמאות נבחרות`,
  "score.optimized": `${TERMS.optimizedScore} אחרי ${TERMS.optimization}: איך ה${TERMS.program} הצליחה עם הפרומפט והדוגמאות שנבחרו`,
  "score.improvement": `הפער בין ה${TERMS.optimizedScore} ל${TERMS.baselineScore}. ככל שהוא גדול יותר, ה${TERMS.optimization} שיפרה יותר את התוצאה`,
  "score.progression": `איך ה${TERMS.score} השתנה מניסיון לניסיון בזמן שה${TERMS.optimizer} חיפש פרומפט טוב יותר`,

  "lm.calls_count": `מספר הקריאות ל${TERMS.model} השפה במהלך ה${TERMS.optimization}`,
  "lm.avg_response_time": `הזמן הממוצע שלקח ל${TERMS.model} לענות לכל קריאה`,

  "model.generation": `ה${TERMS.model} שמייצר את התשובה בפועל בזמן ה${TERMS.optimizationTypeRun}`,
  "model.reflection": `ה${TERMS.model} שבודק טעויות ומציע איך לשפר את ההנחיות במהלך ה${TERMS.optimization}`,

  "data.split_explanation": `ה${TERMS.dataset} מתחלק לשלושה חלקים: ${TERMS.splitTrain} ללמידה, ${TERMS.splitVal} לבחירת הפרומפט, ו${TERMS.splitTest} למדידה סופית`,
  "data.shuffle_explanation": `מערבב את סדר השורות לפני ה${TERMS.split}, כדי שסדר הקובץ לא ישפיע בטעות על התוצאות`,
  "data.split.train": `דוגמאות שה${TERMS.optimizer} משתמש בהן כדי לבנות מועמדים לפרומפט`,
  "data.split.val": `דוגמאות שמדרגות את המועמדים בזמן ה${TERMS.optimization}`,
  "data.split.test": "דוגמאות שמורות למדידה הסופית, אחרי שהפרומפט כבר נבחר",
  "data.seed": `מספר התחלתי קבוע ששומר על אותה חלוקה ואותו ערבוב בכל הרצה חוזרת`,

  "prompt.optimized": `הפרומפט שה${TERMS.optimizer} בנה: הנחיות משופרות ודוגמאות שנבחרו מתוך ה${TERMS.dataset}`,
  "prompt.demonstrations": `דוגמאות קלט-פלט שמוצגות ל${TERMS.model} כדי להראות לו את הפורמט והתשובה הרצויים`,

  "module.choice": "איך להריץ את הפרומפט: Predict מבקש תשובה ישירה; CoT מוסיף שלב reasoning לפני התשובה",
  "optimizer.choice": `השיטה שמנסה לשפר את הפרומפט ולמצוא גרסה עם ${TERMS.score} גבוה יותר`,

  "config.section.summary": `ה${TERMS.module}, ה${TERMS.optimizer}, והפרמטרים שנבחרו ל${TERMS.optimizationTypeRun} זו`,
  "config.section.models": `מודלי השפה שהוגדרו — ${TERMS.generationModelShort} לייצור תשובות, רפלקציה לניתוח שגיאות`,
  "config.section.data": `חלוקת ה${TERMS.dataset} ל${TERMS.splitTrain}, ${TERMS.splitVal} ו${TERMS.splitTest}, והגדרות ערבוב`,

  "grid.generation_models": `המודלים שמייצרים תשובות. כל ${TERMS.pair} בסריקה משתמש ב${TERMS.generationModel} אחר`,
  "grid.reflection_models": `המודלים שמנתחים שגיאות ומציעים שיפורים. כל ${TERMS.pair} משתמש ב${TERMS.reflectionModel} אחר`,
  "grid.score_comparison": `השוואת ${TERMS.baselineScore} וה${TERMS.optimizedScore} לכל ${TERMS.pair} מודלים`,
  "grid.quality_speed_combined":
    "איכות ומהירות לכל זוג מודלים, זה לצד זה. ככל שהאיכות והמהירות גבוהות יותר, כך הזוג טוב יותר.",
  "grid.avg_response_time_per_pair": "משך זמן ממוצע לכל קריאה למודל שפה, לפי זוג מודלים",
  "grid.best_pair_default":
    "ברירת מחדל: הזוג עם ציון האיכות הגבוה ביותר. ניתן להחליף לכל זוג אחר.",

  "pair.runtime": `משך ${TERMS.optimizationTypeRun} ה${TERMS.optimization} עבור ${TERMS.pair} המודלים הזה`,

  "serve.section_pair": "כתובת API וקטעי קוד לשילוב הזוג הנבחר באפליקציה שלכם",
  "serve.section_run": `כתובת API וקטעי קוד לשילוב ה${TERMS.program} המשופרת באפליקציה שלכם`,
  "serve.api_url_pair": "כתובת ה-API של הזוג הנבחר",
  "serve.api_url_run": `כתובת ה-API שאליה שולחים בקשות POST עם שדות הקלט כדי לקבל ${TERMS.prediction} מה${TERMS.program} המשופרת`,
  "serve.integration_code": "דוגמאות קוד מוכנות להעתקה",

  "submit.depth":
    "כמה רחב החיפוש של GEPA: קל רץ מהר עם פחות ניסיונות; מעמיק בודק יותר אפשרויות ולוקח יותר זמן",
  "submit.reflection_minibatch": `כמה דוגמאות ה${TERMS.model} בודק בכל סבב רפלקציה כדי למצוא דפוסי שגיאה`,
  "submit.eval_rounds": "כמה פעמים להריץ הערכה מלאה כדי לבדוק מועמדים לפרומפט",
  "submit.merge": "כשפעיל, GEPA יכול לשלב רעיונות מכמה מועמדים טובים לפרומפט אחד",

  "model_config.temperature": `מידת היצירתיות של ה${TERMS.model} — ערך נמוך נותן תשובות עקביות, גבוה מגוון יותר`,
  "model_config.top_p": `מגביל את מגוון המילים שה${TERMS.model} שוקל — ערך נמוך ממקד, גבוה מאפשר יותר מגוון`,
  "model_config.max_tokens": `אורך ה${TERMS.prediction} המקסימלי — טוקן הוא בערך מילה אחת`,

  "code.signature_metric": `קוד המקור של ה${TERMS.signature} ו${TERMS.metric} שהוגדרו ל${TERMS.optimization} זו`,
  "code.signature": `הגדרת שדות הקלט והפלט של ה${TERMS.task} — מה ה${TERMS.model} מקבל ומה הוא צריך להחזיר`,
  "code.metric": `פונקציה שמודדת את איכות ה${TERMS.prediction} — מחזירה ${TERMS.score} מספרי לכל ${TERMS.example}`,
  "code.predictions_table": `תוצאות הרצת ה${TERMS.program} על דוגמאות הבדיקה — ${TERMS.score} לכל ${TERMS.example} וסיכום כולל`,

  "tagger.upload_file": "העלו קובץ CSV, JSON או Excel. כל שורה תהפוך לפריט לתיוג",
  "tagger.text_column": "בחרו את העמודה שמכילה את הטקסט לתיוג. שאר העמודות יישמרו בייצוא",
  "tagger.mode": "בחרו את סוג התיוג שמתאים למשימה: כן/לא, בחירה מרשימה או טקסט חופשי",
  "tagger.binary_question":
    "השאלה שתוצג מעל כפתורי כן/לא. כדאי לנסח שאלה שאפשר לענות עליה בבירור",
  "tagger.multiclass_categories": "הגדירו את הקטגוריות הזמינות לבחירה בזמן התיוג — לפחות שתיים",
  "tagger.freetext_instruction": "ההנחיה שתוצג מעל שדה הטקסט. הסבירו בקצרה מה צריך לכתוב",

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
