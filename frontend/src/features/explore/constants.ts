/**
 * Explore-slice tuning constants.
 *
 * Polling cadence for the public-dashboard hook (`use-public-dashboard.ts`),
 * which refetches the corpus on an interval to keep counts and filter
 * options current.
 */

export const POLL_INTERVAL_MS = 30_000;
export const POLL_CATCHUP_EPSILON_MS = 1_000;
