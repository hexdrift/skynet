/**
 * Cross-file constants for the generalist agent panel.
 *
 * Width bounds and storage keys are referenced from both the panel
 * component (initial render and resize clamping) and the panel-state
 * hook (persistence + clamping on hydrate). Centralising them keeps
 * the two ends in lockstep and prevents the localStorage prefix from
 * drifting between sites.
 */

export const DEFAULT_WIDTH = 420;
export const MIN_WIDTH = 320;
export const MAX_WIDTH = 720;

export const NARROW_VIEWPORT_QUERY = "(max-width: 1023px)";

export const STORAGE_KEY_OPEN = "skynet.generalist-panel.open";
export const STORAGE_KEY_WIDTH = "skynet.generalist-panel.width";
export const STORAGE_KEY_FIRST_RUN_DISMISSED = "skynet.generalist-panel.first-run-dismissed";
