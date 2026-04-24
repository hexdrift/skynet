/**
 * Tutorial System — Step Definitions
 * Skynet prompt optimization platform
 *
 * Single comprehensive tutorial covering every feature.
 * Works even for users with zero optimizations.
 */

import {
  resetDemoSimulation,
  DEMO_DASHBOARD_JOBS,
  DEMO_DASHBOARD_ANALYTICS,
  DEMO_COMPARE_JOBS,
  DEMO_COMPARE_IDS,
  DEMO_COMPARE_EXAMPLES,
  DEMO_COMPARE_DATASET,
  DEMO_GRID_OPTIMIZATION_ID,
} from "./demo-data";
import { TERMS } from "@/shared/lib/terms";

export type TutorialTrack = "deep-dive";

export interface TutorialStep {
  id: string;
  title: string;
  description: string;
  target: string;
  placement?: "top" | "bottom" | "left" | "right" | "auto";
  beforeShow?: () => void | Promise<void>;
  track: TutorialTrack;
  readingTimeSec: number;
}

export interface TutorialTrackDefinition {
  id: TutorialTrack;
  name: string;
  description: string;
  icon: string;
  stepCount: number;
  steps: TutorialStep[];
}

/* ── Navigation helpers ── */

import {
  callTutorialHook,
  hasTutorialHook,
  setTutorialNavigating,
  queryTutorialHook,
  setPendingCompareDemo,
  setPendingCompareExamples,
} from "./bridge";

function navigateTo(path: string) {
  // Prefer in-app client navigation via the tutorial-overlay hook.
  // Fall back to a full reload if no overlay is mounted (e.g. tests).
  if (hasTutorialHook("routerPush")) {
    callTutorialHook("routerPush", path);
  } else {
    setTutorialNavigating(true);
    window.location.href = path;
  }
}

/** Wait for a selector to appear in the DOM (up to timeoutMs) */
function waitForElement(selector: string, timeoutMs = 3000): Promise<void> {
  return new Promise((resolve) => {
    if (document.querySelector(selector)) {
      resolve();
      return;
    }
    const start = Date.now();
    const check = () => {
      if (document.querySelector(selector) || Date.now() - start > timeoutMs) {
        resolve();
        return;
      }
      requestAnimationFrame(check);
    };
    requestAnimationFrame(check);
  });
}

/** Show a splash screen identical to the real submit animation */
function showSubmitSplash(): Promise<void> {
  callTutorialHook("showTutorialSplash");
  return new Promise((resolve) => setTimeout(resolve, 1500));
}

async function ensureDashboard() {
  if (window.location.pathname !== "/") {
    navigateTo("/");
    await waitForElement("[data-tutorial='dashboard-kpis']");
  }
}

/** Inject demo jobs + analytics into dashboard for the tutorial */
function injectDemoDashboardData() {
  callTutorialHook("setDemoJobs", DEMO_DASHBOARD_JOBS);
  callTutorialHook("setDemoAnalytics", DEMO_DASHBOARD_ANALYTICS);
}

async function ensureSubmit() {
  if (!window.location.pathname.startsWith("/submit")) {
    navigateTo("/submit");
    await waitForElement("[data-tutorial='wizard-stepper']");
  }
}

async function ensureDemoDetail() {
  if (window.location.pathname === "/optimizations/a7e3b291-4d2f-4f8c-b142-9d5e6f8a1c3b") return;
  navigateTo("/optimizations/a7e3b291-4d2f-4f8c-b142-9d5e6f8a1c3b");
  await waitForElement("[data-tutorial='detail-header']");
}

async function ensureCompareDemo() {
  const query = `?jobs=${DEMO_COMPARE_IDS.join(",")}`;
  const alreadyThere = window.location.pathname === "/compare" && window.location.search === query;
  if (alreadyThere) return;
  setPendingCompareDemo(DEMO_COMPARE_JOBS);
  setPendingCompareExamples({
    byJobId: DEMO_COMPARE_EXAMPLES,
    dataset: DEMO_COMPARE_DATASET,
  });
  navigateTo(`/compare${query}`);
  await waitForElement("[data-tutorial='compare-verdict']");
}

async function ensureGridDemo() {
  const path = `/optimizations/${DEMO_GRID_OPTIMIZATION_ID}`;
  if (window.location.pathname === path && !window.location.search.includes("pair=")) return;
  navigateTo(path);
  await waitForElement("[data-tutorial='grid-search']");
}

async function ensureGridPairDetail() {
  const path = `/optimizations/${DEMO_GRID_OPTIMIZATION_ID}`;
  const wantSearch = "?pair=0";
  const alreadyThere = window.location.pathname === path && window.location.search === wantSearch;
  if (alreadyThere) return;
  navigateTo(`${path}${wantSearch}`);
  await waitForElement("[data-tutorial='pair-detail']");
}

function setTab(tab: string) {
  callTutorialHook("setTab", tab);
}

function setWizardStep(step: number) {
  callTutorialHook("setWizardStep", step);
}

function setDetailTab(tab: string) {
  callTutorialHook("setDetailTab", tab);
}

function setCompareTab(tab: string) {
  callTutorialHook("setCompareTab", tab);
}

function setOptimizerName(name: string) {
  callTutorialHook("setOptimizerName", name);
}

async function ensureTagger() {
  if (!window.location.pathname.startsWith("/tagger")) {
    navigateTo("/tagger");
    await waitForElement("[data-tutorial='tagger-setup']");
  }
}

/** Inject demo data into tagger setup when empty and advance to the requested step */
function injectDemoTaggerData(targetStep: number) {
  if (!queryTutorialHook("hasTaggerData")) {
    const rows = [
      { id: 1, text: "השירות היה מעולה, ממליץ בחום!" },
      { id: 2, text: "המוצר הגיע שבור, מאוד מאכזב" },
      { id: 3, text: "משלוח מהיר, אריזה טובה" },
      { id: 4, text: "לא שווה את המחיר, איכות נמוכה" },
      { id: 5, text: "חוויית קנייה נעימה, אחזור שוב" },
    ];
    callTutorialHook("setTaggerDemoData", {
      rows,
      cols: ["text"],
      textCol: "text",
    });
  }
  callTutorialHook("setTaggerStep", targetStep);
}

/** Inject sample dataset + code into the wizard for the tutorial */
function injectSampleDataset() {
  const rows = [
    { email_text: "Click here to win $1000 now!", category: "spam" },
    { email_text: "Meeting moved to 3pm tomorrow", category: "important" },
    { email_text: "50% off all items this weekend only", category: "promotional" },
    { email_text: "Your quarterly report is ready for review", category: "important" },
    { email_text: "Free gift card waiting for you", category: "spam" },
    { email_text: "Team standup notes from Monday", category: "important" },
  ];
  callTutorialHook("setParsedDataset", {
    columns: ["email_text", "category"],
    rows,
    rowCount: rows.length,
  });
  callTutorialHook("setColumnRoles", {
    email_text: "input",
    category: "output",
  });
  callTutorialHook("setDatasetFileName", "emails_sample.csv");
  callTutorialHook(
    "setSignatureCode",
    `class EmailClassifier(dspy.Signature):
    """Classify an email into a category: spam, important, or promotional."""

    # inputs
    email_text: str = dspy.InputField(desc="The email content to classify")

    # outputs
    category: str = dspy.OutputField(desc="One of: spam, important, promotional")
`,
  );
  callTutorialHook(
    "setMetricCode",
    `def metric(example: dspy.Example, prediction: dspy.Prediction, trace: bool = None) -> float:
    return float(example.category.strip().lower() == prediction.category.strip().lower())
`,
  );
}

/* ═══════════════════════════════════════════════════════════
   Tutorial Steps
   ═══════════════════════════════════════════════════════════ */

const tutorialSteps: TutorialStep[] = [
  {
    id: "dd-kpis",
    title: "נתונים מרכזיים",
    description:
      "ארבע כרטיסיות שמסכמות את כל הפעילות: סה״כ ריצות, ריצות פעילות כרגע, ריצות שהצליחו וריצות שנכשלו — לצד אחוז ההצלחה/כישלון מתוך הסך הכולל.",
    target: "[data-tutorial='dashboard-kpis']",
    placement: "bottom",
    beforeShow: async () => {
      await ensureDashboard();
      injectDemoDashboardData();
      setTab("jobs");
    },
    track: "deep-dive",
    readingTimeSec: 4,
  },
  {
    id: "dd-table",
    title: `טבלת ${TERMS.optimizationPlural}`,
    description: `פירוט על כל הריצות. לחצו על כותרת עמודה למיון, על הפילטר לסינון, וגררו קצוות לשינוי רוחב. לחצו על פרטים כדי לפתוח את הפירוט על ה${TERMS.optimization}.`,
    target: "[data-tutorial='dashboard-table']",
    placement: "top",
    beforeShow: async () => {
      await ensureDashboard();
      injectDemoDashboardData();
      setTab("jobs");
    },
    track: "deep-dive",
    readingTimeSec: 6,
  },
  {
    id: "dd-sidebar",
    title: "סרגל צד",
    description: `למעלה: ניווט ללוח בקרה, הגשת ${TERMS.optimization} חדשה ותיוג טקסטים. למטה: חיפוש חופשי והיסטוריית ריצות לפי תאריך. לחצו ⋯ ליד ${TERMS.optimization} לשיתוף, שינוי שם, שכפול, הצמדה או מחיקה.`,
    target: "[data-tutorial='sidebar-full']",
    placement: "left",
    beforeShow: async () => {
      await ensureDashboard();
      injectDemoDashboardData();
      setTab("jobs");
    },
    track: "deep-dive",
    readingTimeSec: 7,
  },
  {
    id: "dd-analytics",
    title: "סטטיסטיקות",
    description: `גרפים אינטראקטיביים שמציגים ${TERMS.scorePlural}, יעילות, השוואת ${TERMS.optimizerPlural} וטבלת שיאים. לחצו על עמודה בגרף כדי לסנן ${TERMS.optimization} ספציפית.`,
    target: "[data-tutorial='dashboard-stats']",
    placement: "auto",
    beforeShow: async () => {
      await ensureDashboard();
      injectDemoDashboardData();
      setTab("analytics");
      await new Promise((r) => setTimeout(r, 100));
    },
    track: "deep-dive",
    readingTimeSec: 5,
  },

  {
    id: "dd-compare-trigger",
    title: `איך להשוות ${TERMS.optimizationPlural}`,
    description:
      "סמנו שתי ריצות או יותר שהושלמו בטבלה — סרגל פעולות יופיע בתחתית עם כפתור השוואה. לחיצה עליו פותחת את דף ההשוואה המפורט.",
    target: "[data-tutorial='compare-button']",
    placement: "top",
    beforeShow: async () => {
      await ensureDashboard();
      injectDemoDashboardData();
      setTab("jobs");
      callTutorialHook("setSelectedJobIds", ["demo-001", "demo-002"]);
      await waitForElement("[data-tutorial='compare-button']");
    },
    track: "deep-dive",
    readingTimeSec: 8,
  },
  {
    id: "dd-compare-verdict",
    title: `השוואת ${TERMS.optimizationPlural}`,
    description: `למעלה רואים את הזוכה — הריצה עם ה${TERMS.score} הגבוה ביותר, יחד עם אחוז השיפור, משך הריצה וה${TERMS.model} שבו השתמשה.`,
    target: "[data-tutorial='compare-verdict']",
    placement: "bottom",
    beforeShow: async () => {
      await ensureCompareDemo();
      setCompareTab("overview");
    },
    track: "deep-dive",
    readingTimeSec: 8,
  },
  {
    id: "dd-compare-scores",
    title: `השוואת ${TERMS.scorePlural}`,
    description: `גרף עמודות וטבלה שמציגים את ${TERMS.baselineScore} מול ה${TERMS.finalScore} לכל ריצה.`,
    target: "[data-tutorial='compare-scores']",
    placement: "top",
    beforeShow: async () => {
      await ensureCompareDemo();
      setCompareTab("overview");
      await waitForElement("[data-tutorial='compare-scores']");
    },
    track: "deep-dive",
    readingTimeSec: 8,
  },
  {
    id: "dd-compare-config",
    title: "השוואת הגדרות",
    description: `לשונית 'הגדרות' מראה איזה ${TERMS.module}, ${TERMS.optimizer}, ${TERMS.modelPlural} וגודל ${TERMS.dataset} שימשו בכל ריצה.`,
    target: "[data-tutorial='compare-config']",
    placement: "top",
    beforeShow: async () => {
      await ensureCompareDemo();
      setCompareTab("config");
      await waitForElement("[data-tutorial='compare-config']");
    },
    track: "deep-dive",
    readingTimeSec: 9,
  },
  {
    id: "dd-compare-prompts",
    title: "השוואת פרומפטים",
    description: `לשונית 'פרומפטים' מראה את ההוראות המאופטמות וה${TERMS.examplePlural} שכל ריצה ייצרה, זה לצד זה. ככה אפשר להבין בדיוק איך שינוי ב${TERMS.model} או בהגדרות השפיע על הפרומפט הסופי.`,
    target: "[data-tutorial='compare-prompts']",
    placement: "top",
    beforeShow: async () => {
      await ensureCompareDemo();
      setCompareTab("prompts");
      await waitForElement("[data-tutorial='compare-prompts']");
    },
    track: "deep-dive",
    readingTimeSec: 9,
  },
  {
    id: "dd-compare-examples",
    title: `השוואת ${TERMS.examplePlural}`,
    description: `לשונית '${TERMS.examplePlural}' עוברת דוגמה-דוגמה ומראה איך כל ריצה ענתה עליה ומה ה${TERMS.score} שקיבלה. אפשר לסנן רק ${TERMS.examplePlural} שבהן יש חוסר הסכמה בין הריצות — ככה קל לאתר בדיוק איפה הן נבדלות.`,
    target: "[data-tutorial='compare-examples']",
    placement: "top",
    beforeShow: async () => {
      await ensureCompareDemo();
      setCompareTab("examples");
      await waitForElement("[data-tutorial='compare-examples']");
    },
    track: "deep-dive",
    readingTimeSec: 9,
  },

  {
    id: "dd-stepper",
    title: "טופס הגשה",
    description: `שישה שלבים: פרטים בסיסיים, ${TERMS.dataset}, פרמטרים, קוד, ${TERMS.model}, סיכום ושליחה.`,
    target: "[data-tutorial='wizard-stepper']",
    placement: "bottom",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(0);
    },
    track: "deep-dive",
    readingTimeSec: 4,
  },

  {
    id: "dd-basics",
    title: "פרטים בסיסיים",
    description: `בשלב הראשון בוחרים שם, תיאור, וסוג ${TERMS.optimization} (${TERMS.optimizationTypeRun} או ${TERMS.optimizationTypeGrid} שמשווה כמה הגדרות במקביל).`,
    target: "[data-tutorial='wizard-step-1']",
    placement: "right",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(0);
    },
    track: "deep-dive",
    readingTimeSec: 5,
  },

  {
    id: "dd-data-upload",
    title: `העלאת ${TERMS.dataset}`,
    description: `גררו קובץ CSV, JSON או Excel לאזור ההעלאה. כל שורה היא דוגמה אחת שהמערכת תלמד ממנה. ככל שיש יותר ${TERMS.examplePlural} איכותיות, ה${TERMS.optimization} תהיה טובה יותר.`,
    target: "[data-tutorial='wizard-step-2']",
    placement: "right",
    beforeShow: async () => {
      await ensureSubmit();
      injectSampleDataset();
      setWizardStep(1);
    },
    track: "deep-dive",
    readingTimeSec: 7,
  },
  {
    id: "dd-columns",
    title: "מיפוי עמודות",
    description: `סמנו כל עמודה כקלט (נשלח ל${TERMS.model}), פלט (התשובה הרצויה שלפיה מודדים הצלחה), או התעלם. המיפוי הזה מגדיר את הפרומפט ההתחלתי אוטומטית.`,
    target: "[data-tutorial='column-mapping']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      injectSampleDataset();
      setWizardStep(1);
    },
    track: "deep-dive",
    readingTimeSec: 7,
  },

  {
    id: "dd-module",
    title: TERMS.module,
    description: `Predict שולח את הקלט ישירות ל${TERMS.model} ומקבל תשובה. Chain of Thought מוסיף שדה reasoning לפני הפלט, שמאלץ את ה${TERMS.model} לנמק את התשובה צעד אחר צעד לפני שהוא מחזיר תוצאה.`,
    target: "[data-tutorial='module-selector']",
    placement: "auto",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(2);
    },
    track: "deep-dive",
    readingTimeSec: 9,
  },
  {
    id: "dd-splits",
    title: "חלוקת נתונים",
    description: `${TERMS.splitTrain}: ה${TERMS.optimizer} לומד מה${TERMS.examplePlural} האלו. ${TERMS.splitVal}: בדיקה שהשיפור מתקיים גם על ${TERMS.examplePlural} שלא שימשו לאימון. ${TERMS.splitTest}: הערכה סופית על ${TERMS.examplePlural} שה${TERMS.optimizer} מעולם לא ראה.`,
    target: "[data-tutorial='data-splits']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(2);
    },
    track: "deep-dive",
    readingTimeSec: 10,
  },
  {
    id: "dd-auto-level",
    title: "רמת חיפוש",
    description:
      "קלה: מהירה, מעט ניסיונות. בינונית: מאוזנת בין מהירות לאיכות. מעמיקה: יסודית, הרבה ניסיונות. ככל שרמת החיפוש גבוהה יותר, הריצה לוקחת יותר זמן אבל הסיכוי לשיפור משמעותי גדל.",
    target: "[data-tutorial='auto-level']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(2);
    },
    track: "deep-dive",
    readingTimeSec: 8,
  },
  {
    id: "dd-gepa",
    title: "פרמטרי GEPA",
    description: `גודל מדגם לרפלקציה: כמה ${TERMS.examplePlural} ה${TERMS.model} מנתח בכל סבב כדי לזהות שגיאות. מקסימום סבבי הערכה: נקבע לפי רמת החיפוש, אפשר לכבות את הרמה באמצעות לחיצה על הרמה הנוכחית ולהגדיר ידנית. מיזוג מועמדים: משלב הוראות מכמה מועמדים טובים לפרומפט אחד משופר.`,
    target: "[data-tutorial='gepa-params']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      setOptimizerName("gepa");
      setWizardStep(2);
    },
    track: "deep-dive",
    readingTimeSec: 16,
  },

  {
    id: "dd-signature",
    title: "פרומפט התחלתי",
    description: `הפרומפט ההתחלתי מגדיר מה ה${TERMS.model} מקבל ומה הוא צריך להחזיר. הוא נוצר אוטומטית ממיפוי העמודות, אבל חשוב לערוך אותו ולהוסיף תיאורים מדויקים לכל שדה כדי שהוא יהיה איכותי.`,
    target: "[data-tutorial='signature-editor']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(3);
    },
    track: "deep-dive",
    readingTimeSec: 11,
  },
  {
    id: "dd-metric",
    title: TERMS.metric,
    description: `פונקציה שמחזירה ${TERMS.score} בין 0 ל-1 לכל תשובה. זו ההגדרה של מה נחשב ״תשובה טובה״, וה${TERMS.optimizer} ינסה למקסם את ה${TERMS.score} הזה לאורך כל הריצה.`,
    target: "[data-tutorial='metric-editor']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(3);
    },
    track: "deep-dive",
    readingTimeSec: 8,
  },

  {
    id: "dd-models",
    title: `בחירת ${TERMS.modelPlural}`,
    description: `${TERMS.generationModel} מייצר את התשובות. ${TERMS.reflectionModel} מנתח שגיאות ומציע שיפורים לפרומפט. אפשר לבחור ${TERMS.modelPlural} שונים לכל תפקיד.`,
    target: "[data-tutorial='model-catalog']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(4);
    },
    track: "deep-dive",
    readingTimeSec: 7,
  },

  {
    id: "dd-review",
    title: "סקירה",
    description: `סיכום כל ההגדרות בחמש לשוניות: כללי, ${TERMS.dataset}, ${TERMS.modelPlural}, ${TERMS.optimizer} וקוד. בדקו שהכל נכון לפני שליחה.`,
    target: "[data-tutorial='wizard-step-6']",
    placement: "right",
    beforeShow: async () => {
      await ensureSubmit();
      setOptimizerName("gepa");
      setWizardStep(5);
    },
    track: "deep-dive",
    readingTimeSec: 5,
  },
  {
    id: "dd-submit",
    title: `שליחת ${TERMS.optimization}`,
    description: `הכפתור שמפעיל את הכל. ברגע שלוחצים, המערכת מתחילה: מאמתת את הקלט, מחלקת את הנתונים, מריצה ${TERMS.baselineScore}, ואז מפעילה את ה${TERMS.optimizer}. אפשר לעקוב אחרי ההתקדמות בזמן אמת מדף התוצאות.`,
    target: "[data-tutorial='submit-button']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(5);
    },
    track: "deep-dive",
    readingTimeSec: 8,
  },

  {
    id: "dd-detail-header",
    title: "דף תוצאות",
    description: `אחרי שליחת ${TERMS.optimization} מגיעים לדף התוצאות. בראש הדף: שם ה${TERMS.optimization}, תיאור, סטטוס הריצה וזמן שעבר. כפתור שכפול יוצר ${TERMS.optimization} חדשה עם אותן הגדרות. בזמן ריצה פעילה מוצג כפתור ביטול, ולאחר סיום או כישלון — כפתור מחיקה.`,
    target: "[data-tutorial='detail-header']",
    placement: "bottom",
    beforeShow: async () => {
      if (window.location.pathname !== "/optimizations/a7e3b291-4d2f-4f8c-b142-9d5e6f8a1c3b") {
        // Coming from submit — reset so the simulation runs fresh
        resetDemoSimulation();
        await showSubmitSplash();
      }
      await ensureDemoDetail();
      setDetailTab("overview");
    },
    track: "deep-dive",
    readingTimeSec: 9,
  },
  {
    id: "dd-pipeline",
    title: "שלבי התהליך",
    description: `כל ${TERMS.optimization} עוברת חמישה שלבים: אימות הקלט, חלוקת הנתונים, ריצת ${TERMS.baselineScore} (לפני ${TERMS.optimization}), ה${TERMS.optimization} עצמה, והערכה סופית. כל שלב מתעדכן בזמן אמת.`,
    target: "[data-tutorial='pipeline-stages']",
    placement: "top",
    beforeShow: async () => {
      await ensureDemoDetail();
      setDetailTab("overview");
    },
    track: "deep-dive",
    readingTimeSec: 8,
  },
  {
    id: "dd-scores",
    title: `כרטיסי ${TERMS.scorePlural}`,
    description: `שלושה כרטיסים: ${TERMS.baselineScore} (לפני ${TERMS.optimization}), ${TERMS.optimizedScore} (אחרי), ואחוז השיפור ביניהם.`,
    target: "[data-tutorial='score-cards']",
    placement: "top",
    beforeShow: async () => {
      await ensureDemoDetail();
      setDetailTab("overview");
    },
    track: "deep-dive",
    readingTimeSec: 5,
  },
  {
    id: "dd-score-chart",
    title: `גרף ${TERMS.scorePlural}`,
    description: `עוקב אחרי ה${TERMS.score} לאורך כל הניסיונות של ה${TERMS.optimizer}. רואים בדיוק מתי נמצא שילוב טוב יותר ואיך ה${TERMS.score} השתנה לאורך הריצה.`,
    target: "[data-tutorial='score-chart']",
    placement: "top",
    beforeShow: async () => {
      await ensureDemoDetail();
      setDetailTab("overview");
    },
    track: "deep-dive",
    readingTimeSec: 7,
  },
  {
    id: "dd-data-tab",
    title: "לשונית נתונים",
    description: `כל דוגמה מה${TERMS.dataset} עם ${TERMS.score} בצבע (ירוק = גבוה, אדום = נמוך), תחזית ה${TERMS.model}, והחלוקה ל${TERMS.splitTrain}, ${TERMS.splitVal} ו${TERMS.splitTest}. אפשר למיין לפי ${TERMS.score} כדי לזהות דפוסים.`,
    target: "[data-tutorial='data-tab-trigger']",
    placement: "bottom",
    beforeShow: async () => {
      await ensureDemoDetail();
      setDetailTab("data");
    },
    track: "deep-dive",
    readingTimeSec: 9,
  },
  {
    id: "dd-playground",
    title: "שימוש",
    description: `אחרי שהריצה מסתיימת, אפשר לבדוק את הפרומפט המאופטם בזמן אמת. הזינו קלט חדש וקבלו תשובה מיידית מה${TERMS.model} עם הפרומפט המשופר.`,
    target: "[data-tutorial='playground-tab']",
    placement: "bottom",
    beforeShow: async () => {
      await ensureDemoDetail();
      setDetailTab("playground");
    },
    track: "deep-dive",
    readingTimeSec: 6,
  },
  {
    id: "dd-logs",
    title: "לוגים",
    description: `לוגים בזמן אמת מה${TERMS.optimizer}. מתעדכנים אוטומטית בזמן שהריצה פעילה. אפשר לסנן לפי רמה (info, warning, error ועוד), לפי שם ה-logger או pair_index, לחפש בטקסט חופשי ולמיין לפי זמן.`,
    target: "[data-tutorial='logs-tab-trigger']",
    placement: "bottom",
    beforeShow: async () => {
      await ensureDemoDetail();
      setDetailTab("logs");
    },
    track: "deep-dive",
    readingTimeSec: 6,
  },
  {
    id: "dd-config",
    title: "הגדרות הריצה",
    description: `כל ההגדרות של הריצה במקום אחד: ${TERMS.modelPlural}, פרמטרים וחלוקת נתונים.`,
    target: "[data-tutorial='config-tab-trigger']",
    placement: "bottom",
    beforeShow: async () => {
      await ensureDemoDetail();
      setDetailTab("config");
    },
    track: "deep-dive",
    readingTimeSec: 7,
  },

  {
    id: "dd-grid-overview",
    title: `סריקת ${TERMS.modelPlural} (Grid Search)`,
    description: `במקום ריצה של ${TERMS.model} יחיד, סריקה משווה כמה ${TERMS.pairPlural} של ${TERMS.generationModel} × ${TERMS.reflectionModel} על אותה ${TERMS.task}. כל שורה היא ${TERMS.pair}: מימין ${TERMS.score} האיכות, באמצע זמן התגובה הממוצע, ומשמאל ה${TERMS.score} המשולב (ממוצע הרמוני של איכות ומהירות). הזוכה הכללי מסומן בכתר.`,
    target: "[data-tutorial='grid-pair-list']",
    placement: "top",
    beforeShow: async () => {
      await ensureGridDemo();
      setDetailTab("overview");
      await waitForElement("[data-tutorial='grid-pair-list']");
    },
    track: "deep-dive",
    readingTimeSec: 14,
  },
  {
    id: "dd-grid-pair",
    title: `פרטי ${TERMS.pair} ${TERMS.modelPlural}`,
    description: `לחיצה על ${TERMS.pair} פותחת תצוגה מפורטת: ${TERMS.scorePlural} לפני/אחרי, ה${TERMS.modelPlural} ב${TERMS.pair}, משך הריצה, מספר הקריאות ל${TERMS.model} וגרף התקדמות.`,
    target: "[data-tutorial='pair-detail']",
    placement: "top",
    beforeShow: async () => {
      await ensureGridPairDetail();
    },
    track: "deep-dive",
    readingTimeSec: 11,
  },

  {
    id: "dd-tagger-intro",
    title: "תיוג טקסטים",
    description: `כלי לתיוג ${TERMS.dataset}ים ישירות באפליקציה. העלו קובץ CSV, JSON או Excel, בחרו מצב תיוג, ותייגו שורה אחרי שורה. בסיום אפשר לייצא את התוצאות בכל הפורמטים.`,
    target: "[data-tutorial='sidebar-tagger']",
    placement: "left",
    beforeShow: async () => {
      await ensureDashboard();
    },
    track: "deep-dive",
    readingTimeSec: 7,
  },
  {
    id: "dd-tagger-setup",
    title: "טופס הגדרת תיוג",
    description:
      "שלושה שלבים: בחירת קובץ ועמודת טקסט, בחירת מצב תיוג, והגדרת השאלה או הקטגוריות. אחרי ההגדרה מתחיל התיוג עם ניווט בחיצי מקלדת, קיצורי מקשים, וייצוא בלחיצה.",
    target: "[data-tutorial='tagger-setup']",
    placement: "top",
    beforeShow: async () => {
      await ensureTagger();
      injectDemoTaggerData(0);
    },
    track: "deep-dive",
    readingTimeSec: 8,
  },
  {
    id: "dd-tagger-modes",
    title: "מצבי תיוג",
    description:
      "סיווג בינארי: שאלה עם כן/לא — מתאים לסינון או זיהוי סנטימנט. קטגוריות: בחירה מרשימה שתגדירו — אפשר לבחור יותר מאחת. טקסט חופשי: כתיבת תגובה לכל שורה — מתאים לחילוץ מידע או תרגום.",
    target: "[data-tutorial='tagger-modes']",
    placement: "top",
    beforeShow: async () => {
      await ensureTagger();
      injectDemoTaggerData(1);
      await waitForElement("[data-tutorial='tagger-modes']");
    },
    track: "deep-dive",
    readingTimeSec: 9,
  },
  {
    id: "dd-done",
    title: "זהו!",
    description: `עכשיו אתם מכירים את כל מה ש-Skynet מציע. הגישו ${TERMS.optimization} ראשונה, עקבו אחרי ה${TERMS.scorePlural} בזמן אמת, ובדקו את הפרומפט המשופר בלשונית שימוש.`,
    target: "[data-tutorial='sidebar-full']",
    placement: "left",
    beforeShow: async () => {
      await ensureDashboard();
    },
    track: "deep-dive",
    readingTimeSec: 5,
  },
];

/* ═══════════════════════════════════════════════════════════
   Track Definition
   ═══════════════════════════════════════════════════════════ */

export const TUTORIAL_TRACKS: TutorialTrackDefinition[] = [
  {
    id: "deep-dive",
    name: "מדריך",
    description: "הכירו כל פינה באפליקציה",
    icon: "deep-dive",
    stepCount: tutorialSteps.length,
    steps: tutorialSteps,
  },
];

export function getTrack(trackId: TutorialTrack): TutorialTrackDefinition | undefined {
  return TUTORIAL_TRACKS.find((t) => t.id === trackId);
}

export function getStep(trackId: TutorialTrack, stepId: string): TutorialStep | undefined {
  const track = getTrack(trackId);
  return track?.steps.find((s) => s.id === stepId);
}
