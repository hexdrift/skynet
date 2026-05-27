import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Code2,
  Copy,
  Database,
  FileSearch,
  GitCompare,
  Layers,
  ListChecks,
  Pencil,
  Pin,
  Play,
  RefreshCw,
  Save,
  ScanSearch,
  ScrollText,
  Search,
  Square,
  Tags,
  Trash2,
  Wand2,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { TERMS } from "@/shared/lib/terms";
import { formatMsg, msg } from "@/shared/lib/messages";

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
    title: formatMsg("auto.features.agent.panel.lib.tool.meta.template.1", {
      p1: TERMS.optimization,
    }),
    description: formatMsg("auto.features.agent.panel.lib.tool.meta.template.2", {
      p1: TERMS.optimization,
    }),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.1"),
    severity: "destructive",
    icon: Trash2,
  },
  bulk_delete_jobs_optimizations_bulk_delete_post: {
    title: formatMsg("auto.features.agent.panel.lib.tool.meta.template.3", {
      p1: TERMS.optimizationPlural,
    }),
    description: formatMsg("auto.features.agent.panel.lib.tool.meta.template.4", {
      p1: TERMS.optimizationPlural,
    }),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.2"),
    severity: "destructive",
    icon: Trash2,
  },
  delete_template_templates: {
    title: msg("auto.features.agent.panel.lib.tool.meta.literal.3"),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.4"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.5"),
    severity: "destructive",
    icon: Trash2,
  },
  cancel_job_optimizations: {
    title: formatMsg("auto.features.agent.panel.lib.tool.meta.template.5", {
      p1: TERMS.optimization,
    }),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.6"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.7"),
    severity: "warning",
    icon: Square,
  },
  bulk_cancel_jobs_optimizations_bulk_cancel_post: {
    title: formatMsg("auto.features.agent.panel.lib.tool.meta.template.26", {
      p1: TERMS.optimizationPlural,
    }),
    description: formatMsg("auto.features.agent.panel.lib.tool.meta.template.27", {
      p1: TERMS.optimizationPlural,
    }),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.69"),
    severity: "warning",
    icon: Square,
  },
  submit_job_run_post: {
    title: formatMsg("auto.features.agent.panel.lib.tool.meta.template.6", {
      p1: TERMS.optimization,
    }),
    description: formatMsg("auto.features.agent.panel.lib.tool.meta.template.7", {
      p1: TERMS.optimizationTypeRun,
    }),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.8"),
    severity: "warning",
    icon: Play,
  },
  submit_grid_search_grid_search_post: {
    title: formatMsg("auto.features.agent.panel.lib.tool.meta.template.8", {
      p1: TERMS.optimizationTypeGrid,
    }),
    description: msg("auto.features.agent.panel.lib.tool.meta.template.9"),
    confirmLabel: formatMsg("auto.features.agent.panel.lib.tool.meta.template.10", {
      p1: TERMS.optimizationTypeGrid,
    }),
    severity: "warning",
    icon: Play,
  },
  rename_job_optimizations: {
    title: formatMsg("auto.features.agent.panel.lib.tool.meta.template.11", {
      p1: TERMS.optimization,
    }),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.9"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.10"),
    severity: "info",
    icon: Pencil,
  },
  toggle_pin_job_optimizations: {
    title: msg("auto.features.agent.panel.lib.tool.meta.literal.11"),
    description: formatMsg("auto.features.agent.panel.lib.tool.meta.template.12", {
      p1: TERMS.optimization,
    }),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.12"),
    severity: "info",
    icon: Pin,
  },
  create_template_templates_post: {
    title: msg("auto.features.agent.panel.lib.tool.meta.literal.15"),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.16"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.17"),
    severity: "info",
    icon: Save,
  },
  edit_code_optimizations_edit_code_post: {
    title: msg("auto.features.agent.panel.lib.tool.meta.literal.18"),
    description: formatMsg("auto.features.agent.panel.lib.tool.meta.template.14", {
      p1: TERMS.signature,
      p2: TERMS.metric,
    }),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.19"),
    severity: "info",
    icon: Code2,
  },
  validate_code_validate_code_post: {
    title: msg("auto.features.agent.panel.lib.tool.meta.literal.20"),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.21"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.22"),
    severity: "info",
    icon: CheckCircle2,
  },
  profile_datasets_profile_post: {
    title: formatMsg("auto.features.agent.panel.lib.tool.meta.template.15", { p1: TERMS.dataset }),
    description: formatMsg("auto.features.agent.panel.lib.tool.meta.template.16", {
      p1: TERMS.dataset,
    }),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.23"),
    severity: "info",
    icon: FileSearch,
  },
  discover_models_models_discover_post: {
    title: msg("auto.features.agent.panel.lib.tool.meta.literal.24"),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.25"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.26"),
    severity: "info",
    icon: Search,
  },
  serve_program_serve: {
    title: msg("auto.features.agent.panel.lib.tool.meta.literal.27"),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.28"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.29"),
    severity: "warning",
    icon: Zap,
  },
  clone_job_optimizations: {
    title: formatMsg("auto.features.agent.panel.lib.tool.meta.template.17", {
      p1: TERMS.optimization,
    }),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.30"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.31"),
    severity: "warning",
    icon: Copy,
  },
  retry_job_optimizations: {
    title: formatMsg("auto.features.agent.panel.lib.tool.meta.template.18", {
      p1: TERMS.optimization,
    }),
    description: formatMsg("auto.features.agent.panel.lib.tool.meta.template.19", {
      p1: TERMS.optimizationTypeRun,
    }),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.32"),
    severity: "warning",
    icon: RefreshCw,
  },
  compare_jobs_optimizations_compare_post: {
    title: formatMsg("auto.features.agent.panel.lib.tool.meta.template.20", {
      p1: TERMS.optimizationPlural,
    }),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.33"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.34"),
    severity: "info",
    icon: GitCompare,
  },
  bulk_pin_jobs_optimizations_bulk_pin_post: {
    title: formatMsg("auto.features.agent.panel.lib.tool.meta.template.21", {
      p1: TERMS.optimizationPlural,
    }),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.35"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.36"),
    severity: "info",
    icon: Pin,
  },
  update_template_templates: {
    title: msg("auto.features.agent.panel.lib.tool.meta.literal.39"),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.40"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.41"),
    severity: "info",
    icon: Pencil,
  },
  apply_template_templates: {
    title: msg("auto.features.agent.panel.lib.tool.meta.literal.42"),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.43"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.44"),
    severity: "info",
    icon: Layers,
  },
  stage_sample_dataset_datasets_samples: {
    title: formatMsg("auto.features.agent.panel.lib.tool.meta.template.23", { p1: TERMS.dataset }),
    description: formatMsg("auto.features.agent.panel.lib.tool.meta.template.24", {
      p1: TERMS.dataset,
    }),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.45"),
    severity: "info",
    icon: Database,
  },
  set_column_roles_datasets_column_roles_post: {
    title: msg("auto.features.agent.panel.lib.tool.meta.literal.46"),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.47"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.48"),
    severity: "info",
    icon: Tags,
  },
  list_jobs_optimizations_get: {
    title: formatMsg("auto.features.agent.panel.lib.tool.meta.template.25", {
      p1: TERMS.optimizationPlural,
    }),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.49"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.50"),
    severity: "info",
    icon: FileSearch,
  },
  update_wizard_state: {
    title: msg("auto.features.agent.panel.lib.tool.meta.literal.54"),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.55"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.56"),
    severity: "info",
    icon: Wand2,
  },
  public_search_dashboard_search_post: {
    title: msg("auto.features.agent.panel.lib.tool.meta.literal.57"),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.58"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.59"),
    severity: "info",
    icon: ScanSearch,
  },
  get_test_results_optimizations: {
    title: msg("auto.features.agent.panel.lib.tool.meta.literal.60"),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.61"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.62"),
    severity: "info",
    icon: ListChecks,
  },
  get_job_logs_optimizations: {
    title: msg("auto.features.agent.panel.lib.tool.meta.literal.63"),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.64"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.65"),
    severity: "info",
    icon: ScrollText,
  },
  get_analytics_summary_analytics_summary_get: {
    title: msg("auto.features.agent.panel.lib.tool.meta.literal.66"),
    description: msg("auto.features.agent.panel.lib.tool.meta.literal.67"),
    confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.68"),
    severity: "info",
    icon: BarChart3,
  },
};

export const DEFAULT_META: ToolMeta = {
  title: msg("auto.features.agent.panel.lib.tool.meta.literal.51"),
  description: msg("auto.features.agent.panel.lib.tool.meta.literal.52"),
  confirmLabel: msg("auto.features.agent.panel.lib.tool.meta.literal.53"),
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
