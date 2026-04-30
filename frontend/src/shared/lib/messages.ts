/**
 * Aggregated Hebrew UI catalog for the application.
 *
 * Per-feature slices live in ``features/<name>/messages.ts`` (and
 * ``shared/messages/messages.ts`` for cross-feature copy) and are
 * hand-edited — there is no codegen step for UI strings. This file
 * just re-exports the union and provides ``msg`` / ``formatMsg``
 * helpers. ESLint blocks inline Hebrew literals outside the slice
 * files and ``i18n/locales/he.json``.
 *
 * Backend i18n codes (errors, validations) take a different path:
 * they live in ``i18n/locales/he.json``, are regenerated into
 * ``shared/lib/generated/i18n-catalog.ts`` by
 * ``scripts/generate_i18n.py``, and are resolved via ``tI18n``.
 */

import { formatTemplate } from "@/shared/lib/i18n";
import { submitMessages } from "@/features/submit/messages";
import { dashboardMessages } from "@/features/dashboard/messages";
import { sidebarMessages } from "@/features/sidebar/messages";
import { exploreMessages } from "@/features/explore/messages";
import { compareMessages } from "@/features/compare/messages";
import { taggerMessages } from "@/features/tagger/messages";
import { tutorialMessages } from "@/features/tutorial/messages";
import { settingsMessages } from "@/features/settings/messages";
import { authMessages } from "@/features/auth/messages";
import { optimizationsMessages } from "@/features/optimizations/messages";
import { agentPanelMessages } from "@/features/agent-panel/messages";
import { sharedMessages } from "@/shared/messages/messages";

export const MESSAGES = {
  ...submitMessages,
  ...dashboardMessages,
  ...sidebarMessages,
  ...exploreMessages,
  ...compareMessages,
  ...taggerMessages,
  ...tutorialMessages,
  ...settingsMessages,
  ...authMessages,
  ...optimizationsMessages,
  ...agentPanelMessages,
  ...sharedMessages,
} as const;

export type MessageKey = keyof typeof MESSAGES;
type MessageParams = Record<string, string | number>;

/**
 * Look up a user-facing string by key and optionally interpolate placeholders.
 */
export function msg(key: MessageKey, params?: MessageParams): string {
  const template = MESSAGES[key];
  return params ? formatTemplate(template, params) : template;
}

export function formatMsg(key: MessageKey, params: MessageParams): string {
  return msg(key, params);
}
