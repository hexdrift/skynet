/**
 * Shared application constants
 * Single source of truth for pagination, animation timing, form constraints, UI dimensions, and API timeouts
 */

export const PAGINATION = {
  DEFAULT_PAGE_SIZE: 20,
  SIDEBAR_PAGE_SIZE: 20,
  DASHBOARD_PAGE_SIZE: 50,
  MAX_PAGE_SIZE: 100,
} as const satisfies Record<string, number>;

export const ANIMATION = {
  TRANSITION_FAST: 150,
  TRANSITION_NORMAL: 300,
  TRANSITION_SLOW: 500,
  DEBOUNCE_SEARCH: 300,
  POLL_INTERVAL: 3000,
} as const satisfies Record<string, number>;

export const FORM_CONSTRAINTS = {
  MAX_JOB_NAME_LENGTH: 100,
  MAX_DESCRIPTION_LENGTH: 500,
  MAX_RECENT_CONFIGS: 5,
  MIN_PASSWORD_LENGTH: 8,
} as const satisfies Record<string, number>;

export const UI_DIMENSIONS = {
  SIDEBAR_WIDTH: 320,
  SIDEBAR_COLLAPSED_WIDTH: 60,
  TOUCH_TARGET_MIN_SIZE: 44,
  CHART_HEIGHT_DEFAULT: 400,
} as const satisfies Record<string, number>;

export const API_TIMEOUTS = {
  DEFAULT_TIMEOUT: 30000,
  LONG_RUNNING_TIMEOUT: 120000,
  POLLING_TIMEOUT: 5000,
} as const satisfies Record<string, number>;
