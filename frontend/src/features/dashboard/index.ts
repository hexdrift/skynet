/**
 * Dashboard feature — public API.
 *
 * The page lives in `app/page.tsx`; this module exposes the pure helpers,
 * status badge renderers, and constants it consumes.
 */
export { PAGE_SIZE, STATUS_COLORS } from "./constants";
export {
  formatElapsed,
  formatDate,
  formatRelativeTime,
  formatPercent,
  formatId,
  normalizeImprovement,
  extractScoreParts,
} from "./lib/formatters";
export { statusBadge, typeBadge, formatScore } from "./lib/status-badges";
