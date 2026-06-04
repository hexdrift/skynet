# Tooltip Audit Report

121 tooltips Codex-reviewed (accuracy + Hebrew fit). 31 component files audited for positioning.

- Copy: **26 major**, **37 minor**, 58 clean
- Positioning: **8** findings (all native title= upgrade candidates; 0 Radix mis-anchors)

## Positioning — native title= → Radix tooltip upgrades

- **src/shared/ui/index-pager.tsx:45** (medium) — Wrap each <button> in the existing TooltipButton from @/shared/ui/tooltip-button (`<TooltipButton tooltip={prevLabel} side="top"><button…/></TooltipButton>`), keeping aria-label for accessibility and dropping the title= attribute. side="top" suits a horizontal pager.
- **src/shared/ui/model-chip.tsx:148** (medium) — Wrap both icon buttons with TooltipButton from @/shared/ui/tooltip-button, passing the same msg() string as `tooltip` and side="top"; keep aria-label, remove the title= attributes.
- **src/shared/layout/app-shell.tsx:181** (low) — Wrap the logout <button> in TooltipButton from @/shared/ui/tooltip-button with tooltip={msg("app.shell.logout")} and side="bottom" (it's in the top bar); keep aria-label and remove title=.
- **src/shared/ui/agent/composer.tsx:81** (low) — Wrap the stop <Button> with TooltipButton from @/shared/ui/tooltip-button (Button supports asChild/ref forwarding) using tooltip={stopAriaLabel} and side="top"; keep aria-label, drop title=.
- **src/shared/ui/agent/user-bubble.tsx:46** (low) — Wrap both <button> elements with TooltipButton from @/shared/ui/tooltip-button, passing the existing msg() copy/edit strings as tooltip and side="top"; preserve aria-label and the aria-live status span, remove title=.
- **src/shared/ui/code-editor.tsx:547** (low) — Wrap each toolbar <button> with TooltipButton from @/shared/ui/tooltip-button, forwarding the existing conditional msg() strings as tooltip and side="top"; keep aria-label, remove title=.
- **src/shared/ui/agent/message-markdown.tsx:58** (low) — Wrap the run/copy <button> elements with TooltipButton from @/shared/ui/tooltip-button using the existing msg() strings as tooltip and side="top"; keep aria-label, drop title=.
- **src/features/settings/components/SettingsTrigger.tsx:21** (low) — Wrap the collapsed <button> in TooltipButton from @/shared/ui/tooltip-button with tooltip={msg("settings.title")} and side="right" (collapsed left rail); keep aria-label={msg("settings.open")}, remove title=.

## Copy — MAJOR (26)

### `module.choice`  _[accuracy, hebrew]_
- current: מודול DSPy הוא רכיב בתוכנית שמפעילה מודל שפה: הוא עוטף כל signature בטכניקת prompting ומגדיר את מבנה הקריאה למודל כדי להפיק את הפלט שמוגדר ב-signature. בתוך המסגרת הזו האופטימייזר מכוון את הפרמטרים הניתנים ללמידה של המודול, כמו הוראות ודוגמאות בפרומפט
- ACC: A DSPy module does not "wrap every signature"; the copy conflates general modules with predictor modules.
- HEB: "כל signature בטכניקת prompting" is awkward and lower-case `signature` is inconsistent with DSPy terminology.
- → **מודול DSPy הוא רכיב בתוכנית שמגדיר קריאה אחת או יותר למודל שפה לפי Signature, כולל אסטרטגיית ה-prompting להפקת שדות הפלט. האופטימייזר יכול לכוון פרמטרים נלמדים של המודול, כמו הוראות ודוגמאות few-shot בפרומפט**

### `model.reflection`  _[accuracy, hebrew]_
- current: המודל שבודק טעויות ומציע איך לשפר את ההנחיות במהלך האופטימיזציה
- ACC: "בודק טעויות" makes the reflection model sound like an evaluator rather than a model that analyzes traces or feedback and proposes prompt edits.
- HEB: The copy hides the expected רפלקציה term and "מציע איך לשפר" is less professional than "מציע שיפורים".
- → **מודל הרפלקציה שמנתח שגיאות ומשוב מהריצה ומציע שיפורים להנחיות בפרומפט במהלך האופטימיזציה**

### `grid.generation_models`  _[accuracy]_
- current: המודלים שמייצרים תשובות. כל זוג בסריקה משתמש במודל מג׳נרט אחר
- ACC: אחר implies every pair has a unique generation model, but grid pairs can share the same generation model across different reflection models.
- → **המודלים שמייצרים תשובות. כל זוג בסריקה כולל מודל מג׳נרט אחד**

### `grid.reflection_models`  _[accuracy]_
- current: המודלים שמנתחים שגיאות ומציעים שיפורים. כל זוג משתמש במודל רפלקציה אחר
- ACC: אחר implies every pair has a unique reflection model, but grid pairs can share the same reflection model across different generation models.
- → **המודלים שמנתחים שגיאות ומציעים שיפורים. כל זוג בסריקה כולל מודל רפלקציה אחד**

### `grid.score_comparison`  _[hebrew]_
- current: השוואת ציון בסיס והציון סופי לכל זוג מודלים
- HEB: והציון סופי is grammatically wrong, and ציון בסיס is less natural than baseline in practitioner-facing copy.
- → **השוואת ציון ה-baseline לציון הסופי לכל זוג מודלים**

### `react.reward`  _[accuracy]_
- current: כיצד מתוגמל הסוכן: replay_match מתגמל שחזור של רצף הכלים שהוקלט; generalist משתמש בתגמול רב-ממדי; general הוא תגמול כללי
- ACC: Codex: these presets are reward/scoring for ReAct runs inside GEPA, not 'agent reward' in a direct RL sense. replay_match does not check only the tool sequence, and generalist/general are both multi-dimensional — so contrasting generalist as multi-dim vs general as 'general' is misleading.
- → **בחירת preset לציון ריצת ReAct: replay_match מדרג התאמה למסלול ה-tool calls שהוקלט, כולל arguments וסכמות; generalist משתמש במדדי ה-Generalist הייעודיים; general משתמש במדדי ReAct כלליים.**

### `react.grounding`  _[accuracy, hebrew]_
- current: כמה משקל לתת לאיתות העיגון של הכלים בתוך התגמול
- ACC: Codex: in the current serve path grounding_weight is kept for provenance but does not actually enter the score; only outside this path is it truly a coefficient of an auxiliary grounding reward. The tooltip implies it always weights the reward.
- HEB: Codex: 'איתות העיגון' is a clumsy translation; practitioners expect 'grounding signal'.
- → **משקל ה-grounding signal בתגמול ה-tools; במסלול השירות הנוכחי הערך נשמר כמטא-דאטה, אך לא נכנס לציון בפועל.**

### `react.auth`  _[accuracy, hebrew]_
- current: כותרת אימות לשרת ה-MCP. לא נשמרת בשרת ולא נחשפת לסוכן הצ'אט
- ACC: Codex: the claim 'not stored on the server' is incorrect given the payload-saving path; it is not stored in the react artifact and should not be exposed to the agent, but it is sent to the server.
- HEB: Codex: 'כותרת אימות' is understandable, but 'Authorization header' is the expected term.
- → **Authorization header לשרת ה-MCP. נשלחת לשרת כדי לטעון את ה-tools ואינה נחשפת לסוכן; ב-artifact היא לא נשמרת.**

### `submit.reflection_minibatch`  _[accuracy]_
- current: כמה דוגמאות המודל בודק בכל סבב רפלקציה כדי למצוא דפוסי שגיאה
- ACC: Codex: it is not 'the model' generically that inspects; this is the number of examples fed into each reflection step so that the reflection model can propose an improvement.
- → **כמה דוגמאות נכללות בכל reflection step של GEPA, כדי שמודל הרפלקציה יזהה דפוסי שגיאה ויציע שיפור לפרומפט.**

### `model_config.top_p`  _[accuracy, hebrew]_
- current: מגביל את מגוון המילים שהמודל שוקל — ערך נמוך ממקד, גבוה מאפשר יותר מגוון
- ACC: Codex: top_p limits token candidates by cumulative probability mass, not 'words' — the 'words' framing is technically wrong.
- HEB: Codex: missing the term top_p / nucleus sampling, and 'מילים' (words) is misleading for a technical audience.
- → **top_p (nucleus sampling) — מגביל את ה-token candidates לפי מסה הסתברותית מצטברת; ערך נמוך ממקד יותר, ערך גבוה משאיר יותר אפשרויות.**

### `code.signature_metric`  _[accuracy, hebrew]_
- current: קוד המקור של הפרומפט התחלתי ופונקציית מדידה שהוגדרו לאופטימיזציה זו
- ACC: Codex: incorrectly equates a DSPy Signature with an initial prompt; a Signature is the input/output contract, not the prompt itself.
- HEB: Codex: the phrase is ungrammatical and hides the expected professional term "Signature" behind an inaccurate Hebrew replacement.
- → **קוד המקור של ה-Signature ושל פונקציית המדידה שהוגדרו לאופטימיזציה הזו**

### `serve.section_pair`  _[accuracy, hebrew]_
- current: כתובת API וקטעי קוד לשילוב הזוג הנבחר באפליקציה שלכם
- ACC: Codex: it suggests integrating the model pair itself, but serving exposes the optimized program produced for the selected pair.
- HEB: Codex: "הזוג הנבחר" is too vague, and "כתובת ה-API" would be more idiomatic than "כתובת API".
- → **כתובת ה-API וקטעי קוד לשילוב התוכנית שנוצרה עבור זוג המודלים הנבחר באפליקציה שלכם**

### `serve.api_url_pair`  _[accuracy, hebrew]_
- current: כתובת ה-API של הזוג הנבחר
- ACC: Codex: a pair does not really have an API URL; the endpoint serves the program artifact associated with that selected model pair.
- HEB: Codex: the phrase is too elliptical because "הזוג" should be tied to "זוג המודלים" or to the served program.
- → **כתובת ה-API של התוכנית שנוצרה עבור זוג המודלים הנבחר**

### `compare.winner_improvement`  _[accuracy, hebrew]_
- current: אחוז השיפור של הריצה הזוכה — ההפרש בין הציון הסופי לציון בסיס
- ACC: Codex: calling it a percent improvement can confuse relative gain with the actual score delta described here.
- HEB: Codex: "לציון בסיס" is awkward after "הציון הסופי"; "ציון הבסיס" reads naturally.
- → **שיפור הציון בריצה הזוכה — הפער בין הציון הסופי לציון הבסיס**

### `compare.winner_models`  _[accuracy, hebrew]_
- current: זוג מודלי השפה של הריצה הזוכה — מודל מג׳נרט שמייצר פלט, ומודל רפלקציה שמשפר את ההנחיות
- ACC: Codex: assumes every winning run has a generation/reflection model pair, but compare can also show a single-model run.
- HEB: Codex: "מודל מג׳נרט" is an awkward Hebrew/English hybrid; describing the model role is clearer.
- → **המודל או זוג המודלים של הריצה הזוכה — המודל שמפיק את התשובה, ובסריקה גם מודל הרפלקציה ששימש לשיפור ההנחיות**

### `analytics.improvement_per_minute`  _[accuracy]_
- current: אחוזי שיפור לכל דקת ריצה — ערך גבוה משמעו אופטימיזציה יעילה יותר
- ACC: Codex: המדד הוא שיפור בציון לדקת ריצה, לא בהכרח "אחוזי שיפור" יחסיים.
- → **שיפור בציון לכל דקת ריצה — ערך גבוה יותר מצביע על אופטימיזציה יעילה יותר**

### `analytics.dataset_size_vs_improvement`  _[accuracy, hebrew]_
- current: האם יותר נתונים מובילים ל שיפור טוב יותר — כל נקודה היא אופטימיזציה אחת
- ACC: Codex: "מובילים" מרמז על סיבתיות, בעוד שהגרף מציג קשר/מתאם בין גודל הדאטאסט לשיפור.
- HEB: Codex: "שיפור טוב יותר" נשמע מסורבל ולא אידיומטי.
- → **הקשר בין גודל הדאטאסט לשיפור בציון — כל נקודה מייצגת אופטימיזציה אחת**

### `analytics.optimizer_avg_improvement`  _[accuracy]_
- current: שיפור ממוצע באחוזים שכל אופטימייזר השיג על פני כל ה ריצות
- ACC: Codex: "כל הריצות" מטעה כי הממוצע מחושב רק מריצות שהושלמו ויש להן שיפור מדיד.
- → **שיפור ממוצע בציון שכל אופטימייזר השיג בריצות שהושלמו בהצלחה**

### `analytics.model_performance_table`  _[accuracy]_
- current: ביצועי המודלים השונים: תדירות שימוש ושיפור ממוצע
- ACC: Codex: לפי מבנה הנתונים הקיים יש תדירות שימוש במודלים, אבל לא שיפור ממוצע לפי מודל — התוכן מטעה.
- → **שימוש במודלים השונים: כמה פעמים כל מודל הופיע בריצות**

### `trajectory.detail.pareto_title.explain`  _[accuracy]_
- current: כל ריבוע מייצג דוגמת אימות. ירוק = המועמד ענה נכון, אדום = ענה שגוי. לחיצה פותחת את הדוגמה.
- ACC: ירוק/אדום מסמנים ציון חיובי מול לא-חיובי, לא בהכרח "נכון" או "שגוי" במדדים חלקיים.
- → **כל ריבוע מייצג דוגמת אימות. ירוק = ציון חיובי לפי פונקציית המדידה, אדום = ציון אפס או נמוך ממנו. לחיצה פותחת את הדוגמה.**

### `trajectory.drawer.rejected.prompt_title.explain`  _[accuracy, hebrew]_
- current: ההבדל בין פרומפט ההורה לבין הפרומפט שמודל הרפלקציה יצר ונדחה. שורות בירוק נוספו, שורות באדום הוסרו.
- ACC: ההסבר מתאר רק תצוגת diff, אף שהסעיף יכול להציג גם את הפרומפט המלא.
- HEB: "שמודל הרפלקציה יצר ונדחה" מסורבל; טבעי יותר לומר שהפרומפט הוצע ולא אומץ.
- → **הפרומפט שמודל הרפלקציה הציע ולא אומץ. במצב השוואה, שורות בירוק נוספו ושורות באדום הוסרו.**

### `trajectory.minibatch.feedback_label.explain`  _[accuracy]_
- current: המשוב שמודל הרפלקציה ניסח לאחר ההערכה — מסביר למה התשובה נכונה או שגויה.
- ACC: המשוב לא בהכרח נוסח על ידי מודל הרפלקציה; לרוב הוא מגיע מה-metric ונצרך על ידי הרפלקציה.
- → **המשוב ש-GEPA מעביר למודל הרפלקציה אחרי ההערכה — מסביר את הציון ואת דפוס השגיאה שההצעה הבאה אמורה לתקן.**

### `trajectory.ghost.title.explain`  _[accuracy]_
- current: הצעת פרומפט ש־GEPA יצר אך לא אימץ — הציון שלה היה נמוך מההורה על ה-mini-batch, ולכן לא נכנסה לעץ.
- ACC: הצעה נדחית גם כשהציון שווה לציון ההורה, לא רק כשהוא נמוך ממנו.
- → **הצעת פרומפט ש-GEPA יצר אך לא אימץ — הציון שלה באותו mini-batch לא היה גבוה מציון ההורה, ולכן היא לא נכנסה לעץ.**

### `submit.code.agent.tool.signature.title`  _[accuracy, hebrew]_
- current: עריכת פרומפט התחלתי
- ACC: DSPy Signature אינו פרומפט התחלתי אלא חוזה קלט/פלט והוראות משימה.
- HEB: החלפת Signature ב"פרומפט התחלתי" מבלבלת עבור משתמשי DSPy.
- → **עריכת ה-Signature**

### `submit.code.agent.tool.metric.title`  _[accuracy, hebrew]_
- current: עריכת פונקציית מדידה
- ACC: Metric ב-DSPy היא פונקציית הערכה/ניקוד לאופטימייזר, לא רק פונקציית מדידה כללית.
- HEB: "פונקציית מדידה" נשמע מאולץ ופחות מוכר מ-Metric לקהל ML.
- → **עריכת פונקציית ההערכה (Metric)**

### `settings.admin.quotas.title`  _[accuracy, hebrew]_
- current: מגבלות משתמשים
- ACC: Quotas הן מכסות שימוש, לא "מגבלות משתמשים" כלליות.
- HEB: הביטוי עמום ועלול להישמע כמו הגבלות על המשתמשים עצמם.
- → **מכסות לפי משתמש**

## Copy — MINOR (37)

### `score.baseline`  _[hebrew]_
- current: ציון בסיס לפני אופטימיזציה: איך התוכנית הצליחה בלי פרומפט משופר או דוגמאות נבחרות
- HEB: "איך התוכנית הצליחה" is too conversational, and "דוגמאות נבחרות" hides the expected few-shot/demonstrations term.
- → **ציון בסיס לפני אופטימיזציה: ביצועי התוכנית ללא פרומפט משופר וללא דוגמאות few-shot שנבחרו**

### `score.optimized`  _[hebrew]_
- current: ציון סופי אחרי אופטימיזציה: איך התוכנית הצליחה עם הפרומפט והדוגמאות שנבחרו
- HEB: "איך התוכנית הצליחה" is informal, and "דוגמאות" should name the few-shot/demonstrations concept.
- → **ציון סופי אחרי אופטימיזציה: ביצועי התוכנית עם הפרומפט המשופר ועם דוגמאות few-shot שנבחרו**

### `score.improvement`  _[hebrew]_
- current: הפער בין הציון סופי לציון בסיס. ככל שהוא גדול יותר, האופטימיזציה שיפרה יותר את התוצאה
- HEB: "הציון סופי" is ungrammatical and "לציון בסיס" should be definite.
- → **ההפרש בין הציון הסופי לציון הבסיס. ככל שהוא גבוה יותר, האופטימיזציה שיפרה יותר את התוצאה**

### `module.cot`  _[accuracy]_
- current: Chain of Thought — מוסיף שדה reasoning שמוביל את המודל לחשוב שלב-אחר-שלב לפני התשובה הסופית; לרוב משפר דיוק במשימות מורכבות
- ACC: "לרוב משפר דיוק" overpromises because Chain of Thought is task-dependent and empirical.
- → **Chain of Thought — מוסיף שדה reasoning לפני התשובה הסופית, שבו המודל מנסח שלבי הסקה; עשוי לשפר דיוק במשימות מורכבות**

### `module.react`  _[hebrew]_
- current: ReAct — סוכן שמשלב חשיבה עם קריאה לכלים (tools) בלולאה, עד שהוא מפיק את הפלט שב-signature
- HEB: "חשיבה" awkwardly replaces the expected `reasoning`, and "הפלט שב-signature" is clumsy.
- → **ReAct — סוכן שמשלב reasoning עם קריאות לכלים (tools) בלולאה, עד שהוא מפיק את הפלט שמוגדר ב-Signature**

### `prompt.optimized`  _[hebrew]_
- current: הפרומפט שהאופטימייזר בנה: הנחיות משופרות ודוגמאות שנבחרו מתוך הדאטאסט
- HEB: "דוגמאות" alone under-translates demonstrations/few-shot for this audience.
- → **הפרומפט שהאופטימייזר בנה: הנחיות משופרות ודוגמאות few-shot שנבחרו מתוך הדאטאסט**

### `prompt.demonstrations`  _[hebrew]_
- current: דוגמאות קלט-פלט שמוצגות למודל כדי להראות לו את הפורמט והתשובה הרצויים
- HEB: "דוגמאות קלט-פלט" omits the expected few-shot/demonstrations term, and "להראות לו" is too conversational.
- → **דוגמאות few-shot של קלט ופלט שמוצגות למודל כדי להדגים את פורמט הפלט ואת ההתנהגות הרצויה**

### `model.generation`  _[hebrew]_
- current: המודל שמייצר את התשובה בפועל בזמן הריצה
- HEB: "בזמן הריצה" is too generic after placeholder substitution; "ריצת האופטימיזציה" is clearer.
- → **המודל שמייצר את התשובות בפועל במהלך ריצת האופטימיזציה**

### `lm_activity.section`  _[accuracy, hebrew]_
- current: פעילות מודלי השפה לפי שלב — כמה קריאות בוצעו וכמה זמן לקחו, מהמג׳נרט וממודל הרפלקציה בנפרד
- ACC: The table shows average response time and calls TO the models, not 'from the models' (מהמודלים is wrong directionality).
- HEB: 'מהמג׳נרט' sounds forced and unnatural as a role term.
- → **פעילות מודלי השפה לפי שלב — מספר הקריאות וזמן התגובה הממוצע, בנפרד למודל שמייצר תשובות ולמודל הרפלקציה**

### `lm_activity.stage.baseline`  _[hebrew]_
- current: קריאות שבוצעו בעת מדידת הציון בסיס — לפני שהאופטימייזר התחיל לפעול
- HEB: 'הציון בסיס' is ungrammatical; should be 'ציון הבסיס'.
- → **קריאות שבוצעו בעת מדידת ציון הבסיס — לפני שהאופטימייזר התחיל לפעול**

### `lm_activity.stage.evaluation`  _[hebrew]_
- current: קריאות שבוצעו בעת מדידת הציון סופי — אחרי שהאופטימיזציה הסתיימה
- HEB: 'הציון סופי' is ungrammatical; should be 'הציון הסופי'.
- → **קריאות שבוצעו בעת מדידת הציון הסופי — אחרי שהאופטימיזציה הסתיימה**

### `lm_activity.column.generation`  _[hebrew]_
- current: קריאות שבוצעו למודל מג׳נרט — המודל שמייצר תשובות
- HEB: 'מודל מג׳נרט' sounds like a forced transliteration/inflection; better to describe the role or use a more stable term.
- → **קריאות שבוצעו למודל שמייצר את התשובות בפועל**

### `lm_activity.cell.calls`  _[accuracy]_
- current: מספר הקריאות שבוצעו בשלב הזה
- ACC: In the table cell the value is also filtered by the column's model, not only by the stage.
- → **מספר הקריאות עבור השלב והמודל בעמודה הזו**

### `lm_activity.cell.avg_ms`  _[accuracy]_
- current: הזמן הממוצע לקריאה בשלב הזה
- ACC: In the table cell the average is by stage AND by the column's model.
- → **זמן התגובה הממוצע לכל קריאה עבור השלב והמודל בעמודה הזו**

### `lm_activity.total_row`  _[accuracy, hebrew]_
- current: סך הכול הקריאות והזמן הממוצע על פני כל השלבים
- ACC: Should clarify this is total calls and average response time per model across all stages.
- HEB: 'סך הכול הקריאות' is less natural; 'סך הקריאות' is preferable.
- → **סך הקריאות וזמן התגובה הממוצע לכל קריאה, על פני כל השלבים ולכל מודל בנפרד**

### `data.split_explanation`  _[hebrew]_
- current: הדאטאסט מתחלק לשלושה חלקים: אימון ללמידה, אימות לבחירת הפרומפט, ובדיקה למדידה סופית
- HEB: אימון/אימות/בדיקה are understandable but over-translated here, and אימון ללמידה sounds redundant for ML practitioners.
- → **הדאטאסט מתחלק לשלושה סטים: train לבניית מועמדי פרומפט, validation לבחירת הפרומפט, ו-test למדידה הסופית**

### `data.seed`  _[hebrew]_
- current: מספר התחלתי קבוע ששומר על אותה חלוקה ואותו ערבוב בכל הרצה חוזרת
- HEB: מספר התחלתי is an awkward over-translation of seed, and ערבוב is less expected than shuffle in this setting.
- → **Seed קבוע שמאפשר לשחזר את אותה חלוקה ואותו shuffle בהרצות חוזרות**

### `config.section.models`  _[hebrew]_
- current: מודלי השפה שהוגדרו — מג׳נרט לייצור תשובות, רפלקציה לניתוח שגיאות
- HEB: רפלקציה alone reads like a process rather than a model, especially after 'מודלי השפה'.
- → **מודלי השפה שהוגדרו — מודל מג׳נרט לייצור תשובות ומודל רפלקציה לניתוח שגיאות**

### `config.section.data`  _[hebrew]_
- current: חלוקת הדאטאסט לאימון, אימות ובדיקה, והגדרות ערבוב
- HEB: אימון, אימות, בדיקה, וערבוב read over-translated where practitioners expect train, validation, test, and shuffle.
- → **חלוקת הדאטאסט ל-train, validation ו-test, והגדרות shuffle**

### `grid.best_pair_default`  _[hebrew]_
- current: ברירת מחדל: הזוג עם ציון האיכות הגבוה ביותר. ניתן להחליף לכל זוג אחר.
- HEB: להחליף לכל זוג אחר is unidiomatic; Hebrew needs להחליף לזוג אחר or לבחור זוג אחר.
- → **ברירת המחדל היא הזוג עם ציון האיכות הגבוה ביותר. אפשר לבחור זוג אחר.**

### `react.match_mode`  _[hebrew]_
- current: exact דורש התאמה מדויקת של שם הכלי והארגומנטים; tool_name מתקדם בהתאמת שם הכלי בלבד
- HEB: Codex: 'מתקדם בהתאמת' sounds unnatural; for this audience 'tool name' / 'arguments' in English are preferable to the Hebrew renderings.
- → **exact דורש התאמה מדויקת של tool name ושל arguments; tool_name מתקדם לפי שם ה-tool בלבד, גם אם ה-arguments שונים.**

### `react.tool_source`  _[hebrew]_
- current: מהיכן נטענת רשימת הכלים: שרת MCP חי, או תצלום כלים מתוך הדאטאסט
- HEB: Codex: 'תצלום כלים' sounds unnatural; 'snapshot' / 'tools' in English are preferable here.
- → **מאיפה נטענת רשימת ה-tools: משרת MCP חי או מ-tool snapshot שנשמר עם הדאטאסט.**

### `submit.merge`  _[accuracy]_
- current: כשפעיל, GEPA יכול לשלב רעיונות מכמה מועמדים טובים לפרומפט אחד
- ACC: Codex: GEPA merge combines candidate components from two candidates on the Pareto front, not generic 'ideas', and not necessarily into a single prompt — the description is over-simplified to the point of being technically off.
- → **כשפעיל, GEPA מנסה לבצע merge בין שני מועמדים מחזית ה-Pareto כדי לשלב רכיבי פרומפט שהצליחו על דוגמאות שונות.**

### `model_config.temperature`  _[hebrew]_
- current: מידת היצירתיות של המודל — ערך נמוך נותן תשובות עקביות, גבוה מגוון יותר
- HEB: Codex: 'מידת היצירתיות' replaces the technical term 'temperature', which practitioners expect to see.
- → **temperature של המודל — ערך נמוך מצמצם sampling randomness ונותן תשובות עקביות יותר; ערך גבוה מגדיל גיוון.**

### `model_config.max_tokens`  _[accuracy]_
- current: אורך התשובה המקסימלי — טוקן הוא בערך מילה אחת
- ACC: Codex: 'a token is about one word' is too simplistic and potentially misleading, especially in Hebrew and in code where one word can split into several tokens.
- → **max_tokens קובע את מספר ה-output tokens המקסימלי. token הוא יחידת טקסט קצרה; מילה אחת, במיוחד בעברית או בקוד, יכולה להתפרק לכמה tokens.**

### `pair.runtime`  _[hebrew]_
- current: משך ריצה האופטימיזציה עבור זוג המודלים הזה
- HEB: Codex: the construct phrase "משך ריצה האופטימיזציה" is grammatically off; "משך הריצה של האופטימיזציה" is natural.
- → **משך הריצה של האופטימיזציה עבור זוג המודלים הזה**

### `compare.winner_runtime`  _[hebrew]_
- current: משך הזמן הכולל של הריצה הזוכה, מרגע השיגור ועד סיום האופטימיזציה
- HEB: Codex: "שיגור" is an unnatural register for a job run in this UI; "תחילת הריצה" is clearer.
- → **משך הזמן הכולל של הריצה הזוכה, מרגע תחילת הריצה ועד סיום האופטימיזציה**

### `analytics.score_comparison`  _[accuracy, hebrew]_
- current: השוואת ציון בסיס מול ה ציון סופי לכל אופטימיזציה שהושלמה
- ACC: Codex: "לכל" עלול להטעות אם הגרף מציג רק את האופטימיזציות המוצגות/המדידות ולא את כל ההיסטוריה.
- HEB: Codex: "הציון סופי" אינו תקין; צריך "הציון הסופי" (חסרה ה' היידוע על שם התואר).
- → **השוואת ציון הבסיס מול הציון הסופי באופטימיזציות שהושלמו**

### `analytics.top_improvements`  _[hebrew]_
- current: ה ריצות שהשיגו את השיפור הגדול ביותר בציון, מהטוב לפחות טוב
- HEB: Codex: "מהטוב לפחות טוב" פחות טבעי מדירוג "מהגבוה לנמוך".
- → **הריצות שהשיגו את השיפור הגדול ביותר בציון, מהגבוה לנמוך**

### `analytics.optimizer_comparison_table`  _[accuracy]_
- current: השוואה מפורטת בין ה אופטימייזרים: שיפור ממוצע, מספר ריצות, וזמן ריצה
- ACC: Codex: "זמן ריצה" אינו מציין שמדובר בזמן ריצה ממוצע ועלול להיקרא כסך זמן.
- → **השוואה מפורטת בין האופטימייזרים: שיפור ממוצע, מספר ריצות וזמן ריצה ממוצע**

### `tagger.mode`  _[hebrew]_
- current: בחרו את סוג התיוג שמתאים למשימה: כן/לא, בחירה מרשימה או טקסט חופשי
- HEB: Codex: "בחירה מרשימה" עלול להיקרא כבחירה מרשימה (נלהבת) ולא כבחירה מתוך רשימה.
- → **בחרו את סוג התיוג שמתאים למשימה: כן/לא, בחירה מתוך רשימה או טקסט חופשי**

### `trajectory.pareto.cell.outputs_label.explain`  _[accuracy]_
- current: התשובה הנכונה לפי דוגמת האימות; הציון נקבע לפי ההשוואה אליה.
- ACC: "התשובה הנכונה" וההשוואה הישירה אליה מצמצמות מדי; בפועל זה פלט יעד שה-metric משתמש בו לציון.
- → **פלט היעד שהוגדר בדוגמת האימות; פונקציית המדידה משתמשת בו כדי לחשב את הציון.**

### `trajectory.minibatch.score_label.explain`  _[hebrew]_
- current: הציון שהחזירה פונקציית המדידה על הדוגמה הזו בלבד. ערך גבוה יותר = תשובה טובה יותר לפי פונקציית המדידה. ערכי ביניים מציינים זיכוי חלקי.
- HEB: "זיכוי חלקי" נשמע משפטי/מתורגם; "ניקוד חלקי" טבעי יותר.
- → **הציון שהחזירה פונקציית המדידה על הדוגמה הזו בלבד. ערך גבוה יותר = תשובה טובה יותר לפי פונקציית המדידה. ערכי ביניים מציינים ניקוד חלקי.**

### `explore.empty.title`  _[hebrew]_
- current: עדיין אין ריצות. ריצות יופיעו כאן אחרי שהמערכת תעבד אותן.
- HEB: החזרה על "ריצות" מסורבלת ומרגישה מעט מכנית.
- → **עדיין אין ריצות. הן יופיעו כאן אחרי שתיצרו ריצה והעיבוד יסתיים.**

### `explore.sort.recent.tip`  _[hebrew]_
- current: מיון לפי זמן — ריצות החדשות ביותר מופיעות ראשונות
- HEB: חסרה ה"א הידיעה לפני "ריצות", ולכן המשפט נשמע לא טבעי.
- → **מיון לפי זמן — הריצות החדשות ביותר מופיעות ראשונות**

### `explore.sort.gain.tip`  _[hebrew]_
- current: מיון לפי שיפור — הפער בין ציון סופי לציון בסיס, מהגבוה לנמוך
- HEB: "ציון בסיס" ו"ציון סופי" נשמעים פחות טבעיים ומסתירים את מונחי ה-baseline/optimized score שמוכרים לקהל ML.
- → **מיון לפי שיפור — הפער בין ה-optimized score ל-baseline score, מהגבוה לנמוך**

### `explore.row.relevance.title`  _[hebrew]_
- current: ציון התאמה — קרבת כוונה בין השאילתה לריצה
- HEB: "קרבת כוונה" הוא צירוף לא אידיומטי בעברית.
- → **ציון התאמה — מידת ההתאמה הסמנטית בין השאילתה לריצה**

## Copy — clean (58 keys)

`score.progression`, `module.predict`, `optimizer.choice`, `lm.calls_count`, `lm.avg_response_time`, `lm_activity.stage.training`, `lm_activity.column.reflection`, `data.shuffle_explanation`, `data.split.train`, `data.split.val`, `data.split.test`, `config.section.summary`, `grid.quality_speed_combined`, `grid.avg_response_time_per_pair`, `react.mcp_url`, `react.tool_filter`, `submit.depth`, `submit.eval_rounds`, `code.signature`, `code.metric`, `code.predictions_table`, `serve.section_run`, `serve.api_url_run`, `serve.integration_code`, `analytics.runtime_vs_gain`, `analytics.runtime_minutes`, `analytics.submissions_per_day`, `tagger.upload_file`, `tagger.text_column`, `tagger.binary_question`, `tagger.multiclass_categories`, `tagger.freetext_instruction`, `trajectory.panel.title`, `trajectory.drawer.section.scores.explain`, `trajectory.drawer.section.minibatch.explain`, `trajectory.drawer.rejected.parent_score.explain`, `trajectory.drawer.rejected.proposal_score.explain`, `trajectory.drawer.rejected.peers_title.explain`, `trajectory.pareto.cell.inputs_label.explain`, `trajectory.pareto.cell.prediction_label.explain`, `trajectory.minibatch.question_label.explain`, `trajectory.minibatch.prediction_label.explain`, `trajectory.ghost.title`, `trajectory.node.section.children.explain`, `trajectory.node.section.rejected_from_here.explain`, `trajectory.node.section.adopted_from_parent.explain`, `trajectory.prompt.react.instructions.explain`, `trajectory.prompt.react.tools.explain`, `explore.results.empty.title`, `explore.results.empty.hint`, `explore.sort.relevance.tip`, `explore.filters.title`, `submit.probe.details.title`, `settings.title`, `settings.agent.shortcut.hint`, `settings.api.title`, `auto.features.agent.panel.components.datasetuploadcard.title`, `auto.features.agent.panel.components.conversationdrawer.title`