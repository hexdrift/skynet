import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  Code2,
  Copy,
  Database,
  FileSearch,
  GitCompare,
  Layers,
  Pencil,
  Pin,
  Play,
  RefreshCw,
  Save,
  Search,
  Square,
  Tags,
  Trash2,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { TERMS } from "@/shared/lib/terms";

export type ApprovalSeverity = "destructive" | "warning" | "info";

export interface ToolMeta {
  title: string;
  description: string;
  confirmLabel: string;
  severity: ApprovalSeverity;
  icon: LucideIcon;
}

export const TOOL_META: Record<string, ToolMeta> = {
  delete_job_optimizations: {
    title: `מחיקת ${TERMS.optimization}`,
    description: `הפעולה לא הפיכה — ה${TERMS.optimization} תוסר לצמיתות.`,
    confirmLabel: "מחק",
    severity: "destructive",
    icon: Trash2,
  },
  bulk_delete_jobs_optimizations_bulk_delete_post: {
    title: `מחיקת כמה ${TERMS.optimizationPlural}`,
    description: `כל ה${TERMS.optimizationPlural} הנבחרות יימחקו לצמיתות.`,
    confirmLabel: "מחק הכל",
    severity: "destructive",
    icon: Trash2,
  },
  delete_template_templates: {
    title: "מחיקת תבנית",
    description: "התבנית תימחק ולא תהיה זמינה לשימוש חוזר.",
    confirmLabel: "מחק",
    severity: "destructive",
    icon: Trash2,
  },
  cancel_job_optimizations: {
    title: `עצירת ${TERMS.optimization} שרצה`,
    description: "הריצה תיעצר כעת. התוצאות שכבר הושגו יישמרו, אבל לא ניתן להמשיך מנקודה זו.",
    confirmLabel: "עצור",
    severity: "warning",
    icon: Square,
  },
  submit_job_run_post: {
    title: `הרצת ${TERMS.optimization} חדשה`,
    description: `תיפתח ${TERMS.optimizationTypeRun} חדשה — הפעולה צורכת קרדיטים ועשויה לקחת זמן.`,
    confirmLabel: "הרץ",
    severity: "warning",
    icon: Play,
  },
  submit_grid_search_grid_search_post: {
    title: `הרצת ${TERMS.optimizationTypeGrid} (Grid Search)`,
    description: `תיפתח סדרת ריצות הבוחנת שילובי פרמטרים שונים. הפעולה צורכת קרדיטים רבים.`,
    confirmLabel: `הרץ ${TERMS.optimizationTypeGrid}`,
    severity: "warning",
    icon: Play,
  },
  rename_job_optimizations: {
    title: `שינוי שם ל${TERMS.optimization}`,
    description: "השם החדש יוצג במקום השם הנוכחי בכל המקומות.",
    confirmLabel: "שנה שם",
    severity: "info",
    icon: Pencil,
  },
  toggle_pin_job_optimizations: {
    title: "הצמדה או ביטול הצמדה",
    description: `ה${TERMS.optimization} תסומן כמועדפת ותוצב בראש הרשימה.`,
    confirmLabel: "עדכן",
    severity: "info",
    icon: Pin,
  },
  toggle_archive_job_optimizations: {
    title: "ארכוב או שחזור",
    description: `ה${TERMS.optimization} תועבר לארכיון (או תחזור ממנו) ותוסתר מהרשימה הראשית.`,
    confirmLabel: "עדכן",
    severity: "info",
    icon: Archive,
  },
  create_template_templates_post: {
    title: "שמירת תבנית חדשה",
    description: "ההגדרות הנוכחיות יישמרו כתבנית לשימוש בריצות עתידיות.",
    confirmLabel: "שמור",
    severity: "info",
    icon: Save,
  },
  edit_code_optimizations_edit_code_post: {
    title: "עריכת קוד",
    description: `הסוכן יערוך את הקוד של ה${TERMS.signature} או ${TERMS.metric} שלך.`,
    confirmLabel: "ערוך",
    severity: "info",
    icon: Code2,
  },
  validate_code_validate_code_post: {
    title: "בדיקת תקינות קוד",
    description: "הקוד ייבדק מבחינה תחבירית בלבד — ללא שינוי או ריצה אמיתית.",
    confirmLabel: "בדוק",
    severity: "info",
    icon: CheckCircle2,
  },
  profile_datasets_profile_post: {
    title: `ניתוח ${TERMS.dataset}`,
    description: `הסוכן ינתח את מבנה ה${TERMS.dataset} כדי לזהות את העמודות וסוגיהן.`,
    confirmLabel: "נתח",
    severity: "info",
    icon: FileSearch,
  },
  discover_models_models_discover_post: {
    title: "גילוי מודלים זמינים",
    description: "חיפוש מודלי LLM חדשים מהספקים שהגדרת.",
    confirmLabel: "חפש",
    severity: "info",
    icon: Search,
  },
  serve_program_serve: {
    title: "פרסום תוכנית כשירות API",
    description: "התוכנית תעלה לאוויר ותהיה זמינה לקריאות API חיצוניות.",
    confirmLabel: "פרסם",
    severity: "warning",
    icon: Zap,
  },
  clone_job_optimizations: {
    title: `שכפול ${TERMS.optimization}`,
    description: "יוצר עותקים חדשים שירוצו מיד. כל עותק צורך קרדיטים.",
    confirmLabel: "שכפל",
    severity: "warning",
    icon: Copy,
  },
  retry_job_optimizations: {
    title: `הרצה חוזרת של ${TERMS.optimization}`,
    description: `מריץ מחדש, עם אותה תצורה, ${TERMS.optimizationTypeRun} שנכשלה או בוטלה. הפעולה צורכת קרדיטים.`,
    confirmLabel: "הרץ שוב",
    severity: "warning",
    icon: RefreshCw,
  },
  compare_jobs_optimizations_compare_post: {
    title: `השוואת ${TERMS.optimizationPlural}`,
    description: "פעולה לקריאה בלבד — מרכזת ציונים של כמה ריצות בטבלה אחת.",
    confirmLabel: "השווה",
    severity: "info",
    icon: GitCompare,
  },
  bulk_pin_jobs_optimizations_bulk_pin_post: {
    title: `עדכון הצמדה לכמה ${TERMS.optimizationPlural}`,
    description: "כל הריצות שנבחרו יקבלו את אותו מצב הצמדה בבת אחת.",
    confirmLabel: "עדכן",
    severity: "info",
    icon: Pin,
  },
  bulk_archive_jobs_optimizations_bulk_archive_post: {
    title: `ארכוב לכמה ${TERMS.optimizationPlural}`,
    description: "הריצות שנבחרו יועברו לארכיון (או יחזרו ממנו) בלי למחוק דבר.",
    confirmLabel: "עדכן",
    severity: "info",
    icon: Archive,
  },
  update_template_templates: {
    title: "עדכון תבנית שמורה",
    description: "השדות שעודכנו ייכתבו מעל התבנית הקיימת. ריצות קודמות לא משתנות.",
    confirmLabel: "עדכן תבנית",
    severity: "info",
    icon: Pencil,
  },
  apply_template_templates: {
    title: "טעינת תבנית לטופס",
    description: "התצורה של התבנית תטען לטופס. תמיד אפשר לערוך לפני הריצה.",
    confirmLabel: "טען",
    severity: "info",
    icon: Layers,
  },
  stage_sample_dataset_datasets_samples: {
    title: `טעינת ${TERMS.dataset} לדוגמה`,
    description: `${TERMS.dataset} מוכן ייטען לטופס כדי לנסות את המערכת מיד, ללא העלאה.`,
    confirmLabel: "טען דוגמה",
    severity: "info",
    icon: Database,
  },
  set_column_roles_datasets_column_roles_post: {
    title: "הגדרת תפקידי עמודות",
    description: "הסוכן יסמן אילו עמודות הן קלט ואילו פלט. אפשר לערוך ידנית בכל שלב.",
    confirmLabel: "עדכן תפקידים",
    severity: "info",
    icon: Tags,
  },
  list_jobs_optimizations_get: {
    title: `קריאת רשימת ${TERMS.optimizationPlural}`,
    description: "שליפת רשימת הריצות כדי להבין את מצב המערכת.",
    confirmLabel: "קרא",
    severity: "info",
    icon: FileSearch,
  },
};

export const DEFAULT_META: ToolMeta = {
  title: "אישור פעולה",
  description: "הסוכן מבקש אישור לפעולה שדורשת את הסכמתך לפני שהיא תתבצע.",
  confirmLabel: "אשר",
  severity: "warning",
  icon: AlertTriangle,
};

export function prettifyToolName(tool: string): string {
  return tool
    .replace(/_(post|get|put|delete|patch)$/i, "")
    .replace(/_/g, " ")
    .trim();
}

export function getToolMeta(tool: string): ToolMeta {
  return TOOL_META[tool] ?? DEFAULT_META;
}

export function getToolTitle(tool: string): string {
  return TOOL_META[tool]?.title ?? prettifyToolName(tool);
}
