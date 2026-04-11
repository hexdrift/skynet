/**
 * Tutorial System — Step Definitions
 * Skynet prompt optimization platform
 *
 * Single comprehensive tutorial covering every feature.
 * Works even for users with zero optimizations.
 */

import { resetDemoSimulation } from "./tutorial-demo-data";

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

import { callTutorialHook, hasTutorialHook, setTutorialNavigating } from "./tutorial-bridge";

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

function setTab(tab: string) {
  callTutorialHook("setTab", tab);
}

function setWizardStep(step: number) {
  callTutorialHook("setWizardStep", step);
}

function setDetailTab(tab: string) {
  callTutorialHook("setDetailTab", tab);
}

function setOptimizerName(name: string) {
  callTutorialHook("setOptimizerName", name);
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
  // ══════════════════════════════════════
  // Dashboard (4 steps)
  // ══════════════════════════════════════
  {
    id: "dd-kpis",
    title: "מדדים מרכזיים",
    description:
      "ארבע כרטיסיות שמסכמות את כל הפעילות: סה״כ ריצות, ריצות פעילות כרגע, אחוז הצלחה כולל, ומספר כשלונות.",
    target: "[data-tutorial='dashboard-kpis']",
    placement: "bottom",
    beforeShow: async () => {
      await ensureDashboard();
      setTab("jobs");
    },
    track: "deep-dive",
    readingTimeSec: 4,
  },
  {
    id: "dd-table",
    title: "טבלת אופטימיזציות",
    description:
      "פירוט על כל הריצות. לחצו על כותרת עמודה למיון, על הפליטר לסינון, וגררו קצוות לשינוי רוחב. לחצו על פרטים כדי לפתוח את הפירוט על האופטמיזציה.",
    target: "[data-tutorial='dashboard-table']",
    placement: "top",
    beforeShow: async () => {
      await ensureDashboard();
      setTab("jobs");
    },
    track: "deep-dive",
    readingTimeSec: 6,
  },
  {
    id: "dd-sidebar",
    title: "סרגל צד",
    description:
      "למעלה: ניווט ללוח בקרה והגשת אופטימיזציה חדשה. למטה: חיפוש חופשי והיסטוריית ריצות לפי תאריך. לחצו ⋯ ליד אופטימיזציה לשינוי שם, הצמדה, שיתוף או מחיקה.",
    target: "[data-tutorial='sidebar-full']",
    placement: "left",
    beforeShow: async () => {
      await ensureDashboard();
      setTab("jobs");
    },
    track: "deep-dive",
    readingTimeSec: 7,
  },
  {
    id: "dd-analytics",
    title: "סטטיסטיקות",
    description:
      "גרפים אינטראקטיביים שמציגים ציונים, יעילות, השוואת אופטימייזרים וטבלת שיאים. לחצו על עמודה בגרף כדי לסנן אופטימיזציה ספציפית.",
    target: "[data-tutorial='dashboard-stats']",
    placement: "auto",
    beforeShow: async () => {
      await ensureDashboard();
      setTab("analytics");
      await new Promise((r) => setTimeout(r, 100));
    },
    track: "deep-dive",
    readingTimeSec: 5,
  },

  // ══════════════════════════════════════
  // Submit wizard — sequential step order
  // ══════════════════════════════════════

  // ── Stepper overview ──
  {
    id: "dd-stepper",
    title: "טופס הגשה",
    description: "שישה שלבים: פרטים בסיסיים, דאטאסט, מודל, קוד, פרמטרים, סיכום ושליחה.",
    target: "[data-tutorial='wizard-stepper']",
    placement: "bottom",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(0);
    },
    track: "deep-dive",
    readingTimeSec: 4,
  },

  // ── Step 1: Basics ──
  {
    id: "dd-basics",
    title: "פרטים בסיסיים",
    description:
      "בשלב הראשון בוחרים שם, תיאור, וסוג אופטימיזציה (ריצה בודדת או סריקה שמשווה כמה הגדרות במקביל).",
    target: "[data-tutorial='wizard-step-1']",
    placement: "right",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(0);
    },
    track: "deep-dive",
    readingTimeSec: 5,
  },

  // ── Step 2: Dataset ──
  {
    id: "dd-data-upload",
    title: "העלאת דאטאסט",
    description:
      "גררו קובץ CSV או Excel לאזור ההעלאה. כל שורה היא דוגמה אחת שהמערכת תלמד ממנה. ככל שיש יותר דוגמאות איכותיות, האופטימיזציה תהיה טובה יותר.",
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
    description:
      "סמנו כל עמודה כקלט (נשלח למודל), פלט (התשובה הרצויה שלפיה מודדים הצלחה), או התעלם. המיפוי הזה מגדיר את החתימה אוטומטית.",
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

  // ── Step 3: Model & Optimizer ──
  {
    id: "dd-module",
    title: "מודול",
    description:
      "Predict שולח את הקלט ישירות למודל ומקבל תשובה. Chain of Thought מוסיף שדה reasoning לפני הפלט, שמאלץ את המודל לנמק את התשובה צעד אחר צעד לפני שהוא מחזיר תוצאה.",
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
    id: "dd-optimizer",
    title: "אופטימייזר",
    description:
      "MIPROv2: מייצר הנחיות ודוגמאות, ומחפש את השילוב הטוב ביותר ביניהם. GEPA: מנתח שגיאות בריצות קודמות ומשכתב את הפרומפט צעד אחר צעד בעזרת רפלקציה.",
    target: "[data-tutorial='optimizer-selector']",
    placement: "auto",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(2);
    },
    track: "deep-dive",
    readingTimeSec: 9,
  },
  {
    id: "dd-models",
    title: "בחירת מודלים",
    description:
      "מודל יצירה מייצר את התשובות. מודל רפלקציה מנתח שגיאות ומציע שיפורים לפרומפט. אפשר לבחור מודלים שונים לכל תפקיד.",
    target: "[data-tutorial='model-catalog']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(2);
    },
    track: "deep-dive",
    readingTimeSec: 7,
  },

  // ── Step 4: Code ──
  {
    id: "dd-signature",
    title: "חתימה",
    description:
      "החתימה מגדירה מה המודל מקבל ומה הוא צריך להחזיר. היא נוצרת אוטומטית ממיפוי העמודות, אבל חשוב לערוך אותה ולהוסיף תיאורים מדויקים לכל שדה כדי שהפרומפט ההתחלתי יהיה איכותי.",
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
    title: "מטריקה",
    description:
      "פונקציה שמחזירה ציון בין 0 ל-1 לכל תשובה. זו ההגדרה של מה נחשב ״תשובה טובה״, והאופטימייזר ינסה למקסם את הציון הזה לאורך כל הריצה.",
    target: "[data-tutorial='metric-editor']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(3);
    },
    track: "deep-dive",
    readingTimeSec: 8,
  },

  // ── Step 5: Parameters ──
  {
    id: "dd-splits",
    title: "חלוקת נתונים",
    description:
      "אימון: האופטימייזר לומד מהדוגמאות האלו. אימות: בדיקה שהשיפור מתקיים גם על דוגמאות שלא שימשו לאימון. בדיקה: הערכה סופית על דוגמאות שהאופטימייזר מעולם לא ראה.",
    target: "[data-tutorial='data-splits']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(4);
    },
    track: "deep-dive",
    readingTimeSec: 10,
  },
  {
    id: "dd-auto-level",
    title: "רמת חיפוש",
    description:
      "קלה: מהיר, מעט ניסיונות. בינונית: מאוזן בין מהירות לאיכות. מעמיקה: יסודי, הרבה ניסיונות. ככל שרמת החיפוש גבוהה יותר, הריצה לוקחת יותר זמן אבל הסיכוי לשיפור משמעותי גדל.",
    target: "[data-tutorial='auto-level']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(4);
    },
    track: "deep-dive",
    readingTimeSec: 8,
  },
  {
    id: "dd-mipro",
    title: "פרמטרי MIPROv2",
    description:
      "דוגמאות אוטומטיות: דוגמאות שהמערכת מייצרת מהנתונים. דוגמאות מהנתונים: דוגמאות קלט/פלט מהדאטאסט שמוצגות למודל. מספר ניסיונות: נקבע לפי רמת החיפוש, אפשר לכבות את הרמה באמצעות לחיצה על הרמה הנוכחית ולהגדיר ידנית. גודל מדגם: כמה דוגמאות נבדקות בכל סבב הערכה. בדיקה חלקית: כשפעיל, ההערכה רצה על מדגם קטן במקום הדאטאסט המלא.",
    target: "[data-tutorial='mipro-params']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      setOptimizerName("miprov2");
      setWizardStep(4);
    },
    track: "deep-dive",
    readingTimeSec: 25,
  },
  {
    id: "dd-gepa",
    title: "פרמטרי GEPA",
    description:
      "גודל מדגם לרפלקציה: כמה דוגמאות המודל מנתח בכל סבב כדי לזהות שגיאות. מקסימום סבבי הערכה: נקבע לפי רמת החיפוש, אפשר לכבות את הרמה באמצעות לחיצה על הרמה הנוכחית ולהגדיר ידנית. מיזוג מועמדים: משלב הוראות מכמה מועמדים טובים לפרומפט אחד משופר.",
    target: "[data-tutorial='gepa-params']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      setOptimizerName("gepa");
      setWizardStep(4);
    },
    track: "deep-dive",
    readingTimeSec: 16,
  },

  // ── Step 6: Review & Submit ──
  {
    id: "dd-review",
    title: "סקירה",
    description:
      "סיכום כל ההגדרות בחמש לשוניות: כללי, דאטאסט, מודלים, אופטימייזר וקוד. בדקו שהכל נכון לפני שליחה.",
    target: "[data-tutorial='wizard-step-6']",
    placement: "right",
    beforeShow: async () => {
      await ensureSubmit();
      setOptimizerName("miprov2");
      setWizardStep(5);
    },
    track: "deep-dive",
    readingTimeSec: 5,
  },
  {
    id: "dd-submit",
    title: "שליחת אופטימיזציה",
    description:
      "הכפתור שמפעיל את הכל. ברגע שלוחצים, המערכת מתחילה: מאמתת את הקלט, מחלקת את הנתונים, מריצה ציון בסיס, ואז מפעילה את האופטימייזר. אפשר לעקוב אחרי ההתקדמות בזמן אמת מדף התוצאות.",
    target: "[data-tutorial='submit-button']",
    placement: "top",
    beforeShow: async () => {
      await ensureSubmit();
      setWizardStep(5);
    },
    track: "deep-dive",
    readingTimeSec: 8,
  },

  // ══════════════════════════════════════
  // Optimization detail page (demo simulation)
  // ══════════════════════════════════════
  {
    id: "dd-detail-header",
    title: "דף תוצאות",
    description:
      "אחרי שליחת אופטימיזציה מגיעים לדף התוצאות. בראש הדף: שם האופטימיזציה, תיאור, סטטוס הריצה וזמן שעבר. כפתור שכפול יוצר אופטימיזציה חדשה עם אותן הגדרות, וכפתור מחיקה מוחק את הריצה.",
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
    description:
      "כל אופטימיזציה עוברת חמישה שלבים: אימות הקלט, חלוקת הנתונים, ריצת ציון בסיס (לפני אופטימיזציה), האופטימיזציה עצמה, והערכה סופית. כל שלב מתעדכן בזמן אמת.",
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
    title: "כרטיסי ציונים",
    description:
      "שלושה כרטיסים: ציון התחלתי (לפני אופטימיזציה), ציון משופר (אחרי), ואחוז השיפור ביניהם.",
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
    title: "גרף ציונים",
    description:
      "עוקב אחרי הציון לאורך כל הניסיונות של האופטימייזר. רואים בדיוק מתי נמצא שילוב טוב יותר ואיך הציון השתנה לאורך הריצה.",
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
    description:
      "כל דוגמה מהדאטאסט עם ציון בצבע (ירוק = גבוה, אדום = נמוך), תחזית המודל, והחלוקה לאימון, אימות ובדיקה. אפשר למיין לפי ציון כדי לזהות דפוסים.",
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
    description:
      "אחרי שהריצה מסתיימת, אפשר לבדוק את הפרומפט המאופטם בזמן אמת. הזינו קלט חדש וקבלו תשובה מיידית מהמודל עם הפרומפט המשופר.",
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
    description:
      "לוגים בזמן אמת מהאופטימייזר. מתעדכנים אוטומטית בזמן שהריצה פעילה. אפשר לסנן לפי רמה (error, warning), לחפש בטקסט חופשי ולמיין לפי זמן.",
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
    description:
      "כל ההגדרות של הריצה במקום אחד: מודלים, פרמטרים וחלוקת נתונים. שימושי כשרוצים להשוות הגדרות בין ריצות שונות כדי להבין מה עבד הכי טוב.",
    target: "[data-tutorial='config-tab-trigger']",
    placement: "bottom",
    beforeShow: async () => {
      await ensureDemoDetail();
      setDetailTab("config");
    },
    track: "deep-dive",
    readingTimeSec: 7,
  },

  // ── Done ──
  {
    id: "dd-done",
    title: "זהו!",
    description:
      "עכשיו אתם מכירים את כל מה ש-Skynet מציע. הגישו אופטימיזציה ראשונה, עקבו אחרי הציונים בזמן אמת, ובדקו את הפרומפט המשופר בלשונית שימוש.",
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
