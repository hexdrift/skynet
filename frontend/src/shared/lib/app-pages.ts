/**
 * The app's page registry: one entry per destination a user can navigate to.
 *
 * The sidebar renders its nav from the `sidebar` entries and the Cmd+K search
 * indexes every entry, so a page added here shows up in both. The route
 * coverage test (`app-pages.test.ts`) fails when a static route under
 * `src/app` is missing from this list, which keeps search from going stale.
 *
 * Kept import-free (plain data, string message keys) so the Node unit test can
 * load it directly; labels and icons resolve in `app-pages-ui.ts`.
 */

export type AppPageId =
  "dashboard" | "analytics" | "data" | "sessions" | "submit" | "explore" | "storage";

export type AppPage = {
  id: AppPageId;
  href: string;
  /** A message key, or a glossary term (see `terms.ts`) shown sentence-cased. */
  label: { key: string } | { term: string };
  descriptionKey?: string;
  /** Space/comma separated search keywords, localized. */
  keywordsKey: string;
  group: "quick" | "navigate";
  /** Rendered in the sidebar nav, in registry order. */
  sidebar?: boolean;
  /** Route prefixes that mark the sidebar item active (defaults to `href`). */
  match?: readonly string[];
};

export const APP_PAGES: readonly AppPage[] = [
  {
    id: "dashboard",
    href: "/",
    label: { key: "auto.features.sidebar.components.sidebar.literal.1" },
    keywordsKey: "app.shell.search.kw.dashboard",
    group: "navigate",
    sidebar: true,
  },
  // One entry covers the whole Data hub: the dataset library and the
  // labeling-session chooser are tabs of the same surface, so both route
  // prefixes light it up.
  {
    id: "data",
    href: "/datasets",
    label: { key: "sidebar.nav.data" },
    keywordsKey: "app.shell.search.kw.data",
    group: "navigate",
    sidebar: true,
    match: ["/datasets", "/tagger"],
  },
  {
    id: "submit",
    href: "/submit",
    label: { term: "notificationNewOpt" },
    descriptionKey: "app.shell.search.new_optimization_description",
    keywordsKey: "app.shell.search.kw.new_optimization",
    group: "quick",
    sidebar: true,
  },
  {
    id: "explore",
    href: "/explore",
    label: { key: "sidebar.nav.explore" },
    keywordsKey: "app.shell.search.kw.explore",
    group: "navigate",
    sidebar: true,
  },
  {
    id: "sessions",
    href: "/tagger",
    label: { key: "data.tabs.sessions" },
    descriptionKey: "app.shell.search.tagging_description",
    keywordsKey: "app.shell.search.kw.sessions",
    group: "quick",
  },
  {
    id: "analytics",
    href: "/?tab=analytics",
    label: { key: "auto.features.dashboard.components.dashboardview.1" },
    keywordsKey: "app.shell.search.kw.analytics",
    group: "navigate",
  },
  {
    id: "storage",
    href: "/storage",
    label: { key: "app.shell.search.storage" },
    keywordsKey: "app.shell.search.kw.storage",
    group: "navigate",
  },
];

/** Split a localized keyword string into search terms. */
export function splitKeywords(value: string): string[] {
  return value.split(/[\s,،、，]+/).filter(Boolean);
}

/**
 * Keep the items whose searchable text contains every query term.
 *
 * Matching per term (not the whole query as one substring) lets "api key"
 * or "delete account" find an item whose words are not adjacent.
 */
export function matchesQuery(haystack: ReadonlyArray<string | undefined>, query: string): boolean {
  const terms = query.toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return true;
  const text = haystack.filter(Boolean).join(" ").toLocaleLowerCase();
  return terms.every((term) => text.includes(term));
}
