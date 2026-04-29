/**
 * Aggregated Hebrew UI catalog for the application.
 *
 * Per-feature slices live in ``features/<name>/messages.ts``; this
 * file just re-exports the union and provides ``msg`` / ``formatMsg``
 * helpers. ESLint blocks new inline Hebrew literals outside the
 * slice files and ``i18n/locales/he.json`` (PER-83 phase 4).
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

/**
 * Look up a user-facing string by key. Silently returns the key
 * itself if not found so missing messages surface as a dev-visible
 * "key not translated" artifact instead of a silent blank.
 */
export function msg(key: MessageKey): string {
  return MESSAGES[key] ?? key;
}

export function formatMsg(
  key: MessageKey,
  params: Record<string, string | number>,
): string {
  return formatTemplate(msg(key), params);
}
