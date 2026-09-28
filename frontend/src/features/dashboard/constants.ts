import { STATUS_DOT_COLOR } from "@/shared/constants/job-status";

export const FETCH_PAGE_SIZE = 50;

export const STATUS_COLORS = STATUS_DOT_COLOR;

export type StatAccent = "default" | "success" | "warning" | "danger";

export const ACCENT_DOT: Record<StatAccent, string> = {
  default: "bg-foreground/25",
  success: "bg-[var(--success)]",
  warning: "bg-[var(--warning)]",
  danger: "bg-[var(--danger)]",
};

export const ACCENT_TEXT: Record<StatAccent, string> = {
  default: "text-foreground",
  success: "text-[var(--success)]",
  warning: "text-[var(--warning)]",
  danger: "text-[var(--danger)]",
};
