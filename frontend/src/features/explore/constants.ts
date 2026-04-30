/**
 * Explore-slice tuning constants.
 *
 * Canvas geometry, interaction thresholds, and colors used by drawing code
 * (canvas 2D cannot resolve CSS variables at draw time, so the few tokens
 * referenced here mirror values defined in `app/globals.css`).
 */

export const PADDING = 48;
export const BASE_RADIUS = 4;
export const HOVER_RADIUS = 7;
export const FOCUS_RING_OFFSET = 3;

export const MIN_SCALE = 0.45;
export const MAX_SCALE = 24;
export const ZOOM_WHEEL_FACTOR = 0.0015;
export const ZOOM_DOUBLECLICK_IN = 1.8;
export const ZOOM_DOUBLECLICK_OUT = 1 / 1.8;

export const DRAG_THRESHOLD_PX = 4;

export const TOOLTIP_MAX_WIDTH = 260;
export const TOOLTIP_EDGE_INSET = 12;
export const TOOLTIP_ABOVE_THRESHOLD = 120;

export const POLL_INTERVAL_MS = 30_000;
export const POLL_CATCHUP_EPSILON_MS = 1_000;

export const FOCUS_RING_COLOR = "#C8A882";
export const GRID_AXIS_COLOR = "oklch(0.94 0.005 50)";
export const GRID_LINE_COLOR = "oklch(0.91 0.006 50)";
export const POINT_OUTLINE_COLOR = "oklch(0.2 0.02 40)";

// A cluster needs at least 3 points to form a triangle hull and to read
// as a region rather than as scattered noise.
export const CLUSTER_LABEL_MIN_POINTS = 3;
export const CLUSTER_LABEL_MAX_CHARS = 22;
