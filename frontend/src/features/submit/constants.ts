import type { ModelConfig, SplitFractions } from "@/shared/types/api";

export const emptyModelConfig = (): ModelConfig => ({
  name: "",
  temperature: 0.7,
  max_tokens: 1024,
});

export const defaultSplit: SplitFractions = { train: 0.7, val: 0.15, test: 0.15 };

export const STEPS = [
  { id: "basics", label: "פרטים בסיסיים" },
  { id: "data", label: "דאטאסט" },
  { id: "model", label: "מודל" },
  { id: "code", label: "קוד" },
  { id: "params", label: "פרמטרים" },
  { id: "review", label: "סיכום ושליחה" },
] as const;

export const RECENT_KEY = "skynet:recent-model-configs";
export const MAX_RECENT = 5;

/* ── Slide animation variants (RTL: forward = slide from left, backward = slide from right) ── */
export const slideVariants = {
  enter: (direction: number) => ({
    x: direction > 0 ? -80 : 80,
    opacity: 0,
    scale: 0.97,
  }),
  center: {
    x: 0,
    opacity: 1,
    scale: 1,
  },
  exit: (direction: number) => ({
    x: direction > 0 ? 80 : -80,
    opacity: 0,
    scale: 0.97,
  }),
};
