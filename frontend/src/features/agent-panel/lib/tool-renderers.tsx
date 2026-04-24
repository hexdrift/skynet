import * as React from "react";

import type { AgentToolCall } from "@/shared/ui/agent/types";
import { TERMS } from "@/shared/lib/terms";

import { SubmitSummaryCard } from "../components/SubmitSummaryCard";
import { UUID_RE } from "./entry-row";

export interface ToolRenderer {
  card?: (call: AgentToolCall) => React.ReactNode;
  summary?: (call: AgentToolCall) => string | null;
}

function getArgs(call: AgentToolCall): Record<string, unknown> {
  const p = (call.payload ?? {}) as Record<string, unknown>;
  const a = p.arguments;
  return a && typeof a === "object" && !Array.isArray(a) ? (a as Record<string, unknown>) : {};
}

function getResult(call: AgentToolCall): unknown {
  const p = (call.payload ?? {}) as Record<string, unknown>;
  return p.result;
}

function shortId(v: unknown): string | undefined {
  if (typeof v !== "string") return undefined;
  return UUID_RE.test(v) ? v.slice(0, 8) : v;
}

function pickId(args: Record<string, unknown>): string | undefined {
  return shortId(
    args.id ?? args.optimization_id ?? args.job_id ?? args.template_id ?? args.sample_id,
  );
}

function pickIds(args: Record<string, unknown>): string[] {
  const raw = args.ids ?? args.optimization_ids;
  if (!Array.isArray(raw)) return [];
  return raw.filter((x): x is string => typeof x === "string");
}

function byStatus(
  call: AgentToolCall,
  map: { running: string; done: string; error?: string },
): string {
  if (call.status === "running") return map.running;
  if (call.status === "error") return map.error ?? map.done;
  return map.done;
}

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

const RENDERERS: Record<string, ToolRenderer> = {
  submit_optimization: {
    card: (call) => <SubmitSummaryCard call={call} />,
    summary: (call) => (call.status === "running" ? `מגיש ${TERMS.optimization} חדשה…` : null),
  },

  delete_job_optimizations: {
    summary: (call) => {
      const id = pickId(getArgs(call));
      return byStatus(call, {
        running: id ? `מוחק ${id}…` : `מוחק ${TERMS.optimization}…`,
        done: id ? `נמחקה ${id}` : `נמחקה ${TERMS.optimization}`,
        error: "המחיקה נכשלה",
      });
    },
  },

  bulk_delete_jobs_optimizations_bulk_delete_post: {
    summary: (call) => {
      const n = pickIds(getArgs(call)).length;
      return byStatus(call, {
        running: n ? `מוחק ${n} ${TERMS.optimizationPlural}…` : `מוחק ${TERMS.optimizationPlural}…`,
        done: n ? `נמחקו ${n} ${TERMS.optimizationPlural}` : `נמחקו ${TERMS.optimizationPlural}`,
        error: "המחיקה הקבוצתית נכשלה",
      });
    },
  },

  rename_job_optimizations: {
    summary: (call) => {
      const args = getArgs(call);
      const raw =
        typeof args.new_name === "string"
          ? args.new_name
          : typeof args.name === "string"
            ? args.name
            : undefined;
      const name = raw ? truncate(raw, 26) : undefined;
      return byStatus(call, {
        running: name ? `משנה שם ל־"${name}"…` : "משנה שם…",
        done: name ? `השם שונה ל־"${name}"` : "השם שונה",
        error: "שינוי השם נכשל",
      });
    },
  },

  toggle_pin_job_optimizations: {
    summary: (call) => {
      const args = getArgs(call);
      const pin = Boolean(args.pinned ?? args.value);
      return byStatus(call, {
        running: pin ? "מצמיד…" : "מבטל הצמדה…",
        done: pin ? "הוצמדה" : "ההצמדה בוטלה",
        error: "עדכון ההצמדה נכשל",
      });
    },
  },

  toggle_archive_job_optimizations: {
    summary: (call) => {
      const args = getArgs(call);
      const arch = Boolean(args.archived ?? args.value);
      return byStatus(call, {
        running: arch ? "מעביר לארכיון…" : "משחזר מהארכיון…",
        done: arch ? "הועברה לארכיון" : "שוחזרה מהארכיון",
        error: "עדכון הארכיון נכשל",
      });
    },
  },

  bulk_pin_jobs_optimizations_bulk_pin_post: {
    summary: (call) => {
      const args = getArgs(call);
      const n = pickIds(args).length;
      const pin = Boolean(args.pinned ?? args.value);
      return byStatus(call, {
        running: pin ? `מצמיד ${n}…` : `מבטל הצמדה ל־${n}…`,
        done: pin ? `${n} הוצמדו` : `הוסרה הצמדה מ־${n}`,
        error: "עדכון הצמדה קבוצתי נכשל",
      });
    },
  },

  bulk_archive_jobs_optimizations_bulk_archive_post: {
    summary: (call) => {
      const args = getArgs(call);
      const n = pickIds(args).length;
      const arch = Boolean(args.archived ?? args.value);
      return byStatus(call, {
        running: arch ? `מעביר ${n} לארכיון…` : `משחזר ${n} מהארכיון…`,
        done: arch ? `${n} הועברו לארכיון` : `${n} שוחזרו מהארכיון`,
        error: "עדכון ארכיון קבוצתי נכשל",
      });
    },
  },

  cancel_job_optimizations: {
    summary: (call) => {
      const id = pickId(getArgs(call));
      return byStatus(call, {
        running: "עוצר את הריצה…",
        done: id ? `הריצה נעצרה (${id})` : "הריצה נעצרה",
        error: "העצירה נכשלה",
      });
    },
  },

  clone_job_optimizations: {
    summary: (call) => {
      const args = getArgs(call);
      const n = typeof args.count === "number" && args.count > 0 ? args.count : 1;
      return byStatus(call, {
        running: n > 1 ? `משכפל ${n} עותקים…` : "משכפל…",
        done: n > 1 ? `שוכפלו ${n} עותקים` : `שוכפלה ${TERMS.optimization}`,
        error: "השכפול נכשל",
      });
    },
  },

  retry_job_optimizations: {
    summary: (call) =>
      byStatus(call, {
        running: "מריץ מחדש…",
        done: "הורצה מחדש",
        error: "הריצה החוזרת נכשלה",
      }),
  },

  submit_job_run_post: {
    summary: (call) => {
      const args = getArgs(call);
      const raw = typeof args.job_name === "string" ? args.job_name : undefined;
      const name = raw ? truncate(raw, 24) : undefined;
      return byStatus(call, {
        running: name ? `מריץ "${name}"…` : `מתחיל ${TERMS.optimizationTypeRun}…`,
        done: name
          ? `התחילה ${TERMS.optimizationTypeRun} "${name}"`
          : `התחילה ${TERMS.optimizationTypeRun} חדשה`,
        error: `ה${TERMS.optimizationTypeRun} נכשלה`,
      });
    },
  },

  submit_grid_search_grid_search_post: {
    summary: (call) =>
      byStatus(call, {
        running: `מתחילה ${TERMS.optimizationTypeGrid}…`,
        done: `התחילה ${TERMS.optimizationTypeGrid}`,
        error: `ה${TERMS.optimizationTypeGrid} נכשלה`,
      }),
  },

  list_jobs_optimizations_get: {
    summary: (call) => {
      if (call.status === "running") return `קורא רשימת ${TERMS.optimizationPlural}…`;
      if (call.status === "error") return "הקריאה נכשלה";
      const result = getResult(call);
      let count: number | null = null;
      if (Array.isArray(result)) count = result.length;
      else if (result && typeof result === "object") {
        const r = result as Record<string, unknown>;
        const items = r.items ?? r.jobs ?? r.optimizations;
        if (Array.isArray(items)) count = items.length;
      }
      return count !== null ? `${count} ${TERMS.optimizationPlural}` : "הרשימה נקראה";
    },
  },

  create_template_templates_post: {
    summary: (call) => {
      const args = getArgs(call);
      const raw = typeof args.name === "string" ? args.name : undefined;
      const name = raw ? truncate(raw, 24) : undefined;
      return byStatus(call, {
        running: "שומר תבנית…",
        done: name ? `נשמרה תבנית "${name}"` : "התבנית נשמרה",
        error: "שמירת התבנית נכשלה",
      });
    },
  },

  update_template_templates: {
    summary: (call) =>
      byStatus(call, {
        running: "מעדכן תבנית…",
        done: "התבנית עודכנה",
        error: "עדכון התבנית נכשל",
      }),
  },

  delete_template_templates: {
    summary: (call) =>
      byStatus(call, {
        running: "מוחק תבנית…",
        done: "התבנית נמחקה",
        error: "מחיקת התבנית נכשלה",
      }),
  },

  apply_template_templates: {
    summary: (call) =>
      byStatus(call, {
        running: "טוען תבנית…",
        done: "התבנית נטענה",
        error: "טעינת התבנית נכשלה",
      }),
  },

  compare_jobs_optimizations_compare_post: {
    summary: (call) => {
      const n = pickIds(getArgs(call)).length;
      return byStatus(call, {
        running: n ? `משווה ${n} ריצות…` : "משווה ריצות…",
        done: n ? `הושוו ${n} ריצות` : "ההשוואה הושלמה",
        error: "ההשוואה נכשלה",
      });
    },
  },

  validate_code_validate_code_post: {
    summary: (call) => {
      if (call.status === "running") return "בודק תקינות קוד…";
      const result = getResult(call);
      if (result && typeof result === "object") {
        const valid = (result as Record<string, unknown>).valid;
        if (valid === true) return "הקוד תקין";
        if (valid === false) return "הקוד לא תקין";
      }
      return byStatus(call, { running: "בודק…", done: "הקוד נבדק" });
    },
  },

  edit_code_optimizations_edit_code_post: {
    summary: (call) =>
      byStatus(call, {
        running: "עורך קוד…",
        done: "הקוד נערך",
        error: "עריכת הקוד נכשלה",
      }),
  },

  profile_datasets_profile_post: {
    summary: (call) =>
      byStatus(call, {
        running: `מנתח ${TERMS.dataset}…`,
        done: "הניתוח הושלם",
        error: "הניתוח נכשל",
      }),
  },

  discover_models_models_discover_post: {
    summary: (call) =>
      byStatus(call, {
        running: "מחפש מודלים זמינים…",
        done: "החיפוש הושלם",
        error: "החיפוש נכשל",
      }),
  },

  stage_sample_dataset_datasets_samples: {
    summary: (call) =>
      byStatus(call, {
        running: `טוען ${TERMS.dataset} לדוגמה…`,
        done: `ה${TERMS.dataset} נטען`,
        error: "הטעינה נכשלה",
      }),
  },

  set_column_roles_datasets_column_roles_post: {
    summary: (call) =>
      byStatus(call, {
        running: "מגדיר תפקידי עמודות…",
        done: "תפקידי העמודות הוגדרו",
        error: "ההגדרה נכשלה",
      }),
  },

  serve_program_serve: {
    summary: (call) =>
      byStatus(call, {
        running: "מפרסם תוכנית…",
        done: "התוכנית פורסמה כשירות",
        error: "הפרסום נכשל",
      }),
  },
};

export function getToolRenderer(tool: string): ToolRenderer | undefined {
  return RENDERERS[tool];
}
