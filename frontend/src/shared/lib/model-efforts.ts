import { msg } from "@/shared/lib/messages";

// Effort vocabularies are per-API, not universal, and providers silently
// clamp or reject levels outside their documented ladder — so each model
// family gets its own ladder and unknown ids fall back to the common one.
// "ultra" is a separate mode, not an effort level, so it is deliberately absent.
const DEFAULT_EFFORTS = ["low", "medium", "high"] as const;
const OPENAI_EFFORTS = ["none", "low", "medium", "high", "xhigh"] as const;
const ANTHROPIC_EFFORTS = ["low", "medium", "high", "xhigh", "max"] as const;

/** The reasoning-effort ladder a model actually supports. */
export function effortsFor(model: string | null): readonly string[] {
  if (!model) return DEFAULT_EFFORTS;
  if (model.includes("anthropic/claude")) return ANTHROPIC_EFFORTS;
  if (model.includes("openai/")) return OPENAI_EFFORTS;
  return DEFAULT_EFFORTS;
}

/** Localized display label for a reasoning-effort level. */
export function effortLabel(level: string): string {
  switch (level) {
    case "none":
      return msg("agent.model_menu.effort_none");
    case "minimal":
      return msg("agent.model_menu.effort_minimal");
    case "low":
      return msg("agent.model_menu.effort_low");
    case "medium":
      return msg("agent.model_menu.effort_medium");
    case "high":
      return msg("agent.model_menu.effort_high");
    case "xhigh":
      return msg("agent.model_menu.effort_xhigh");
    case "max":
      return msg("agent.model_menu.effort_max");
    default:
      return level;
  }
}
