export const ANIMATION = {
  TRANSITION_FAST: 150,
  TRANSITION_NORMAL: 300,
  TRANSITION_SLOW: 500,
  DEBOUNCE_SEARCH: 300,
  POLL_INTERVAL: 3000,
} as const satisfies Record<string, number>;
