/** Locale and icon bindings for the page registry in `app-pages.ts`. */

import {
  ChartBar,
  Compass,
  Database,
  HardDrive,
  PaperPlaneTilt,
  SquaresFour,
  Tag,
} from "@/shared/ui/icons";
import type { Icon } from "@/shared/ui/icons";
import { sentenceCase } from "@/shared/lib/formatters";
import { msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";

import { splitKeywords, type AppPage, type AppPageId } from "./app-pages";

type MessageKey = Parameters<typeof msg>[0];

// A Record over every id makes a new registry entry a type error until it has an icon.
export const APP_PAGE_ICONS: Record<AppPageId, Icon> = {
  dashboard: SquaresFour,
  analytics: ChartBar,
  data: Database,
  sessions: Tag,
  submit: PaperPlaneTilt,
  explore: Compass,
  storage: HardDrive,
};

/** Resolve a registry page's label in the active locale. */
export function appPageLabel(page: AppPage): string {
  return "term" in page.label
    ? sentenceCase(TERMS[page.label.term as keyof typeof TERMS])
    : msg(page.label.key as MessageKey);
}

/** Resolve a registry page's optional description in the active locale. */
export function appPageDescription(page: AppPage): string | undefined {
  return page.descriptionKey ? msg(page.descriptionKey as MessageKey) : undefined;
}

/** Resolve a registry page's search keywords in the active locale. */
export function appPageKeywords(page: AppPage): string[] {
  return splitKeywords(msg(page.keywordsKey as MessageKey));
}
