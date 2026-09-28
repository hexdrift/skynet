"use client";

import { Kbd } from "@/shared/ui/kbd";
import * as React from "react";
import { useRouter } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import { ArrowUpRight, GraduationCap, MagnifyingGlass, Robot, SignOut } from "@/shared/ui/icons";
import type { Icon } from "@/shared/ui/icons";

import { useGeneralistPanelStateOptional } from "@/features/agent-panel";
import { SETTINGS_TABS, useSettingsModal, visibleSettingsTabs } from "@/features/settings";
import { useTutorialContext } from "@/features/tutorial";
import { APP_PAGES, matchesQuery, splitKeywords } from "@/shared/lib/app-pages";
import {
  APP_PAGE_ICONS,
  appPageDescription,
  appPageKeywords,
  appPageLabel,
} from "@/shared/lib/app-pages-ui";
import { useLocale } from "@/shared/providers";
import { dirForLocale } from "@/shared/lib/locale";
import { msg } from "@/shared/lib/messages";
import { cn } from "@/shared/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/primitives/dialog";

type SearchGroup = "quick" | "navigate" | "actions" | "settings";

type SearchItem = {
  id: string;
  group: SearchGroup;
  label: string;
  description?: string;
  keywords: string[];
  icon: Icon;
  run: () => void;
};

const GROUP_ORDER: SearchGroup[] = ["quick", "navigate", "actions", "settings"];

/** Render the global navigation/search trigger and its command palette. */
export function GlobalSearch() {
  const router = useRouter();
  const { locale } = useLocale();
  const dir = dirForLocale(locale);
  const { data: session } = useSession();
  const isAdmin = session?.user?.role === "admin";
  const { open: settingsOpen, openTo } = useSettingsModal();
  const agentPanel = useGeneralistPanelStateOptional();
  const { startTrack } = useTutorialContext();
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement | null>(null);

  // Built from the same registries the sidebar and Settings rail render from,
  // so new pages and settings tabs become searchable without touching this file.
  const items = React.useMemo<SearchItem[]>(() => {
    const pages: SearchItem[] = APP_PAGES.map((page) => ({
      id: `page-${page.id}`,
      group: page.group,
      label: appPageLabel(page),
      description: appPageDescription(page),
      keywords: appPageKeywords(page),
      icon: APP_PAGE_ICONS[page.id],
      run: () => router.push(page.href),
    }));
    const actions: SearchItem[] = [
      ...(agentPanel
        ? [
            {
              id: "action-agent",
              group: "actions" as const,
              label: msg("auto.features.agent.panel.components.minimizedpill.literal.1"),
              keywords: splitKeywords(msg("app.shell.search.kw.open_agent")),
              icon: Robot,
              run: () => agentPanel.setOpen(true),
            },
          ]
        : []),
      {
        id: "action-tour",
        group: "actions",
        label: msg("app.shell.search.action.tour"),
        keywords: splitKeywords(msg("app.shell.search.kw.tour")),
        icon: GraduationCap,
        run: () => startTrack("quick"),
      },
      {
        id: "action-sign-out",
        group: "actions",
        label: msg("app.shell.logout"),
        keywords: splitKeywords(msg("app.shell.search.kw.sign_out")),
        icon: SignOut,
        run: () => void signOut({ callbackUrl: "/login" }),
      },
    ];
    const settings: SearchItem[] = visibleSettingsTabs(isAdmin).map((tab) => ({
      id: `settings-${tab}`,
      group: "settings",
      label: msg(SETTINGS_TABS[tab].labelKey),
      description: msg("app.shell.search.settings_description"),
      keywords: splitKeywords(msg(SETTINGS_TABS[tab].keywordsKey)),
      icon: SETTINGS_TABS[tab].icon,
      run: () => openTo(tab),
    }));
    return [...pages, ...actions, ...settings];
  }, [agentPanel, isAdmin, openTo, router, startTrack, locale]);

  const filteredItems = React.useMemo(() => {
    if (!query.trim()) return items.filter((item) => item.group !== "settings");
    return items.filter((item) =>
      matchesQuery([item.label, item.description, ...item.keywords], query),
    );
  }, [items, query]);

  React.useEffect(() => {
    setActiveIndex(0);
  }, [filteredItems.length, query]);

  React.useEffect(() => {
    if (!open) {
      setQuery("");
      return;
    }
    const frame = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open]);

  React.useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        if (settingsOpen) return;
        event.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [settingsOpen]);

  const selectItem = (item: SearchItem) => {
    setOpen(false);
    item.run();
  };

  const handleInputKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % Math.max(filteredItems.length, 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex(
        (index) =>
          (index - 1 + Math.max(filteredItems.length, 1)) % Math.max(filteredItems.length, 1),
      );
    } else if (event.key === "Enter" && filteredItems[activeIndex]) {
      event.preventDefault();
      selectItem(filteredItems[activeIndex]);
    }
  };

  const groupLabels: Record<SearchGroup, string> = {
    quick: msg("app.shell.search.quick_actions"),
    navigate: msg("app.shell.search.navigate"),
    actions: msg("app.shell.search.actions"),
    settings: msg("app.shell.search.settings"),
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        dir={dir}
        className="group inline-flex size-[44px] shrink-0 items-center justify-center gap-3 rounded-xl border border-border/70 bg-background/80 px-2.5 text-muted-foreground shadow-none transition-[background-color,border-color,color,box-shadow] duration-150 hover:border-border hover:bg-accent/50 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/35 lg:h-8 lg:w-64 lg:justify-between"
        aria-label={msg("app.shell.search.button_aria")}
        aria-keyshortcuts="Control+K Meta+K"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="global-search-dialog"
      >
        <span className="flex min-w-0 items-center gap-1.5">
          <MagnifyingGlass
            className="size-4 shrink-0 text-muted-foreground transition-colors duration-150 group-hover:text-primary"
            aria-hidden="true"
          />
          <span
            dir="auto"
            className="hidden truncate text-start text-[0.8rem] font-normal tracking-tight text-muted-foreground lg:block"
          >
            {msg("app.shell.search.label")}
          </span>
        </span>
        <span dir="ltr" className="hidden shrink-0 items-center gap-1 lg:flex" aria-hidden="true">
          <Kbd>{msg("app.shell.search.command_key")}</Kbd>
          <Kbd>{msg("app.shell.search.k_key")}</Kbd>
        </span>
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          id="global-search-dialog"
          showCloseButton={false}
          dir={dir}
          className="max-w-[calc(100%-1.5rem)] gap-0 overflow-hidden rounded-2xl border border-border/75 bg-background p-0 shadow-[0_16px_48px_rgba(28,22,18,0.16)] sm:max-w-xl"
        >
          <DialogHeader className="sr-only">
            <DialogTitle>{msg("app.shell.search.title")}</DialogTitle>
            <DialogDescription>{msg("app.shell.search.description")}</DialogDescription>
          </DialogHeader>
          <div className="group flex h-[58px] items-center gap-3 border-b border-border/60 px-4 focus-within:bg-white/50">
            <MagnifyingGlass
              className="size-5 shrink-0 text-primary/60 transition-colors group-focus-within:text-primary"
              aria-hidden="true"
            />
            <input
              ref={inputRef}
              id="global-search-input"
              name="global-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={handleInputKeyDown}
              placeholder={msg("app.shell.search.placeholder")}
              aria-label={msg("app.shell.search.placeholder")}
              aria-controls="global-search-results"
              aria-activedescendant={
                filteredItems[activeIndex]
                  ? `global-search-${filteredItems[activeIndex].id}`
                  : undefined
              }
              role="combobox"
              aria-expanded="true"
              autoComplete="off"
              spellCheck={false}
              dir={dir}
              className="h-full min-w-0 flex-1 bg-transparent text-start text-[0.95rem] text-foreground outline-none placeholder:text-start placeholder:text-muted-foreground/90"
            />
          </div>

          <div
            id="global-search-results"
            role="listbox"
            aria-label={msg("app.shell.search.results")}
            className="max-h-[min(28rem,60vh)] overflow-y-auto p-2"
          >
            {filteredItems.length > 0 ? (
              GROUP_ORDER.map((group) => {
                const groupItems = filteredItems.filter((item) => item.group === group);
                if (groupItems.length === 0) return null;
                return (
                  <section key={group} className="pb-2 last:pb-0">
                    <p className="px-2 pb-1.5 pt-2 text-[0.65rem] font-semibold uppercase tracking-[0.12em] text-muted-foreground/65">
                      {groupLabels[group]}
                    </p>
                    <div className="space-y-0.5">
                      {groupItems.map((item) => {
                        const index = filteredItems.indexOf(item);
                        const selected = activeIndex === index;
                        const Icon = item.icon;
                        return (
                          <button
                            key={item.id}
                            id={`global-search-${item.id}`}
                            type="button"
                            role="option"
                            aria-selected={selected}
                            onMouseEnter={() => setActiveIndex(index)}
                            onClick={() => selectItem(item)}
                            className={cn(
                              "group/item flex w-full items-center gap-3 rounded-xl px-2.5 py-2 text-start outline-none transition-[background-color,color] duration-100",
                              selected
                                ? "bg-primary/[0.09] text-foreground"
                                : "text-foreground/80 hover:bg-accent/55",
                            )}
                          >
                            <span
                              className={cn(
                                "flex size-9 shrink-0 items-center justify-center rounded-xl transition-colors duration-100",
                                selected
                                  ? "bg-primary/[0.12] text-primary"
                                  : "bg-muted/70 text-muted-foreground group-hover/item:text-primary",
                              )}
                            >
                              <Icon className="size-[1.05rem]" aria-hidden="true" />
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-medium">
                                {item.label}
                              </span>
                              {item.description && (
                                <span className="mt-0.5 block truncate text-xs text-muted-foreground/75">
                                  {item.description}
                                </span>
                              )}
                            </span>
                            {selected && (
                              <span className="hidden shrink-0 items-center gap-1.5 text-xs font-medium text-muted-foreground sm:flex">
                                {msg("app.shell.search.open")}
                                <ArrowUpRight className="size-3.5" aria-hidden="true" />
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </section>
                );
              })
            ) : (
              <div className="flex min-h-36 flex-col items-center justify-center gap-2 px-6 text-center">
                <MagnifyingGlass className="size-5 text-primary/30" aria-hidden="true" />
                <p className="text-sm font-medium text-foreground/75">
                  {msg("app.shell.search.no_results")}
                </p>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
