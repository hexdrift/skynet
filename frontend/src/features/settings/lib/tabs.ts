/**
 * The Settings modal's tabs: order, rail grouping, label, icon and search keywords.
 *
 * The modal renders its rail from this table and the Cmd+K search indexes it,
 * so a tab added here is searchable with no change to the search palette. The
 * `Record` over every tab makes a missing keyword key a type error.
 */

import { HardDrive, Info, Key, Plug, Robot, Sparkle, Tag, User } from "@/shared/ui/icons";
import type { Icon } from "@/shared/ui/icons";
import type { msg } from "@/shared/lib/messages";

type MessageKey = Parameters<typeof msg>[0];

export const SETTINGS_TAB_ORDER = [
  "wizard",
  "tagging",
  "agent",
  "account",
  "providers",
  "api",
  "admin",
  "about",
] as const;

export type SettingsTab = (typeof SETTINGS_TAB_ORDER)[number];

export type SettingsTabMeta = {
  icon: Icon;
  labelKey: MessageKey;
  /** Space/comma separated terms for what the tab contains, localized. */
  keywordsKey: MessageKey;
  group: "workflows" | "assistants" | "preferences" | "access" | "system";
  adminOnly?: boolean;
};

export const SETTINGS_TABS: Record<SettingsTab, SettingsTabMeta> = {
  wizard: {
    icon: Sparkle,
    labelKey: "settings.tab.wizard",
    keywordsKey: "app.shell.search.kw.wizard",
    group: "workflows",
  },
  tagging: {
    icon: Tag,
    labelKey: "settings.tab.tagging",
    keywordsKey: "app.shell.search.kw.tagging",
    group: "workflows",
  },
  agent: {
    icon: Robot,
    labelKey: "settings.tab.agent",
    keywordsKey: "app.shell.search.kw.agent",
    group: "assistants",
  },
  account: {
    icon: User,
    labelKey: "settings.tab.account",
    keywordsKey: "app.shell.search.kw.account",
    group: "preferences",
  },
  providers: {
    icon: Plug,
    labelKey: "settings.tab.providers",
    keywordsKey: "app.shell.search.kw.providers",
    group: "access",
  },
  api: {
    icon: Key,
    labelKey: "settings.tab.api",
    keywordsKey: "app.shell.search.kw.api",
    group: "access",
  },
  admin: {
    icon: HardDrive,
    labelKey: "settings.tab.admin",
    keywordsKey: "app.shell.search.kw.admin",
    group: "system",
    adminOnly: true,
  },
  about: {
    icon: Info,
    labelKey: "settings.tab.about",
    keywordsKey: "app.shell.search.kw.about",
    group: "system",
  },
};

/** List the tabs this user may open, in rail order. */
export function visibleSettingsTabs(isAdmin: boolean): SettingsTab[] {
  return SETTINGS_TAB_ORDER.filter((tab) => isAdmin || !SETTINGS_TABS[tab].adminOnly);
}
