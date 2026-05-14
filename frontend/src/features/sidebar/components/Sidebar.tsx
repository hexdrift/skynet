"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  Send,
  Tags,
  Trash2,
  Search,
  PanelRightClose,
  PanelRightOpen,
  X,
  MoreHorizontal,
  Share2,
  Pencil,
  Pin,
  Loader2,
  Grid2x2,
  ChevronLeft,
  CopyPlus,
} from "lucide-react";
import { Skeleton } from "@/shared/ui/bone-skeleton";
import { sidebarMoreBones } from "../lib/bones";
import { cn } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/primitives/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/primitives/dialog";
import {
  listJobsSidebar,
  deleteJob,
  renameOptimization,
  togglePinOptimization,
} from "@/shared/lib/api";
import type { SidebarJobItem } from "@/shared/lib/api";
import { isActiveStatus } from "@/shared/constants/job-status";
import { toast } from "react-toastify";
import { useSession } from "next-auth/react";
import { groupJobsByRecency, matchesJobSearch } from "@/features/sidebar";
import { SettingsTrigger, useUserPrefs } from "@/features/settings";
import { formatMsg, msg } from "@/shared/lib/messages";
import { TERMS } from "@/shared/lib/terms";

const NAV_ITEMS = [
  {
    href: "/",
    label: msg("auto.features.sidebar.components.sidebar.literal.1"),
    icon: LayoutDashboard,
  },
  { href: "/tagger", label: msg("auto.features.sidebar.components.sidebar.literal.2"), icon: Tags },
  { href: "/submit", label: TERMS.notificationNewOpt, icon: Send },
] as const;

const PAGE_SIZE = 20;

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const activePairParam = searchParams.get("pair");
  const parsedPair = activePairParam != null ? parseInt(activePairParam, 10) : NaN;
  const activePairIndex = Number.isFinite(parsedPair) ? parsedPair : null;
  const { data: session } = useSession();
  const sessionUser = session?.user?.name ?? "";
  const isAdmin = (session?.user as { role?: string } | undefined)?.role === "admin";
  const [collapsed, setCollapsed] = React.useState(false);

  // Listen for external collapse requests (e.g. submit splash transition)
  React.useEffect(() => {
    const handler = () => setCollapsed(true);
    window.addEventListener("sidebar:collapse", handler);
    return () => window.removeEventListener("sidebar:collapse", handler);
  }, []);

  // Auto-collapse when viewport is narrow (< 1024px) — fires on threshold
  // crossing only. Never auto-expands so manual expand is respected.
  React.useEffect(() => {
    const mql = window.matchMedia("(max-width: 1023px)");
    if (mql.matches) setCollapsed(true);
    const handler = (e: MediaQueryListEvent) => {
      if (e.matches) setCollapsed(true);
    };
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  const [jobs, setJobs] = React.useState<SidebarJobItem[]>([]);
  const [activeCount, setActiveCount] = React.useState(0);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [loadedAll, setLoadedAll] = React.useState(false);
  const [loadingMore, setLoadingMore] = React.useState(false);
  // Sidebar infinite scroll: fetchData (polling + external invalidation)
  // re-requests ``max(PAGE_SIZE, loadedItemsRef.current)`` rows so a
  // background 30s refresh doesn't truncate the user's scrolled position
  // back to page 1. The ref lives outside React state so fetchData doesn't
  // need to be re-created when the loaded count changes.
  const loadedItemsRef = React.useRef(0);
  // Synchronous in-flight guard: setLoadingMore is async, so the observer
  // can fire twice before React re-renders. The ref blocks the second call.
  const loadingMoreRef = React.useRef(false);
  const listRef = React.useRef<HTMLDivElement>(null);
  const sentinelRef = React.useRef<HTMLDivElement | null>(null);
  const searchRef = React.useRef<HTMLInputElement>(null);

  const fetchData = React.useCallback(async () => {
    try {
      const limit = Math.min(200, Math.max(PAGE_SIZE, loadedItemsRef.current));
      const res = await listJobsSidebar({
        username: isAdmin ? undefined : sessionUser || undefined,
        limit,
        offset: 0,
      });
      setJobs(res.items);
      setActiveCount(res.items.filter((j) => isActiveStatus(j.status)).length);
      setLoadedAll(res.items.length >= res.total);
      loadedItemsRef.current = res.items.length;
    } catch (err) {
      console.warn("sidebar fetch failed:", err);
    }
  }, [sessionUser, isAdmin]);

  React.useEffect(() => {
    // Dep change (login / admin toggle) — reset depth so the next fetch
    // starts fresh at one page.
    loadedItemsRef.current = 0;
    void fetchData();
    const tick = () => {
      if (document.visibilityState === "visible") void fetchData();
    };
    const interval = setInterval(tick, 30000);
    // Catch up immediately when the tab becomes visible after being hidden.
    const onVisibility = () => {
      if (document.visibilityState === "visible") void fetchData();
    };
    document.addEventListener("visibilitychange", onVisibility);
    const onJobsChanged = () => fetchData();
    window.addEventListener("optimizations-changed", onJobsChanged);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("optimizations-changed", onJobsChanged);
    };
  }, [fetchData]);

  const loadMore = React.useCallback(async () => {
    if (loadingMoreRef.current || loadedAll) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    try {
      const res = await listJobsSidebar({
        username: isAdmin ? undefined : sessionUser || undefined,
        limit: PAGE_SIZE,
        offset: jobs.length,
      });
      setJobs((prev) => {
        // Dedupe by optimization_id in case a new job was inserted above
        // the offset between the previous fetch and this one.
        const existing = new Set(prev.map((j) => j.optimization_id));
        const appended = res.items.filter((j) => !existing.has(j.optimization_id));
        const merged = [...prev, ...appended];
        loadedItemsRef.current = merged.length;
        setLoadedAll(merged.length >= res.total);
        return merged;
      });
    } catch (err) {
      console.warn("sidebar loadMore failed:", err);
    } finally {
      loadingMoreRef.current = false;
      setLoadingMore(false);
    }
  }, [loadedAll, isAdmin, sessionUser, jobs.length]);

  // Infinite-scroll sentinel. The sidebar scrolls in its own container
  // (``listRef``), so the observer's root must point at that element — not
  // the default viewport — otherwise the sentinel would appear "in view"
  // based on page scroll rather than sidebar scroll and fire incorrectly.
  React.useEffect(() => {
    const node = sentinelRef.current;
    const root = listRef.current;
    if (!node || !root) return;
    if (loadedAll) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) void loadMore();
      },
      { root, rootMargin: "120px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [loadedAll, loadMore, jobs.length]);

  const [deleteConfirm, setDeleteConfirm] = React.useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = React.useState(false);

  const handleDelete = React.useCallback((e: React.MouseEvent, optimizationId: string) => {
    e.preventDefault();
    e.stopPropagation();
    setDeleteConfirm(optimizationId);
  }, []);

  const confirmDelete = async () => {
    const optimizationId = deleteConfirm;
    if (!optimizationId) return;
    setDeleteLoading(true);
    setJobs((prev) => prev.filter((j) => j.optimization_id !== optimizationId));
    try {
      await deleteJob(optimizationId);
      toast.success(msg("sidebar.delete.success"));
      window.dispatchEvent(new Event("optimizations-changed"));
      if (pathname === `/optimizations/${optimizationId}`) router.push("/");
    } catch {
      toast.error(msg("sidebar.delete.failed"));
      void fetchData();
    } finally {
      setDeleteLoading(false);
      setDeleteConfirm(null);
    }
  };

  const filteredJobs = React.useMemo(
    () => jobs.filter((j) => matchesJobSearch(j, searchQuery)),
    [jobs, searchQuery],
  );
  const groupedJobs = React.useMemo(() => groupJobsByRecency(filteredJobs), [filteredJobs]);

  const deleteJobInfo = React.useMemo(() => {
    if (!deleteConfirm) return null;
    const job = jobs.find((j) => j.optimization_id === deleteConfirm);
    if (!job) return { name: deleteConfirm, id: deleteConfirm };
    const name =
      job.name ||
      [job.module_name, job.optimizer_name].filter(Boolean).join(" · ") ||
      job.optimization_id.slice(0, 8);
    return { name, id: job.optimization_id };
  }, [deleteConfirm, jobs]);

  return (
    <aside
      className={cn(
        "relative flex h-full shrink-0 flex-col border-l border-sidebar-border/60 bg-sidebar/80 backdrop-blur-xl overflow-hidden transition-[width] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
      )}
      style={{ width: collapsed ? "3rem" : "clamp(200px, 16vw, 240px)" }}
      dir="rtl"
      data-tutorial="sidebar-full"
    >
      <div
        className={cn(
          "absolute inset-0 flex flex-col items-center py-3 gap-2 transition-opacity duration-200",
          collapsed ? "opacity-100 pointer-events-auto delay-150" : "opacity-0 pointer-events-none",
        )}
      >
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className="p-2 rounded-lg hover:bg-sidebar-accent/40 cursor-pointer transition-colors"
          title={msg("auto.features.sidebar.components.sidebar.literal.3")}
          aria-label={msg("auto.features.sidebar.components.sidebar.literal.4")}
        >
          <PanelRightOpen className="size-4 text-muted-foreground" />
        </button>
        <div className="w-6 h-px bg-border/40 my-1" />
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              {...(href === "/tagger" && collapsed ? { "data-tutorial": "sidebar-tagger" } : {})}
              className={cn(
                "p-2 rounded-lg transition-colors",
                active
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-sidebar-accent/40 hover:text-foreground",
              )}
              title={label}
              aria-label={label}
            >
              <Icon className="size-4" />
            </Link>
          );
        })}
        <div className="mt-auto" />
        <SettingsTrigger collapsed />
      </div>

      <div
        className={cn(
          "flex flex-col h-full min-w-[14rem] transition-opacity duration-200",
          collapsed ? "opacity-0 pointer-events-none" : "opacity-100 pointer-events-auto delay-150",
        )}
      >
        <div className="flex items-center justify-between px-3 py-3 border-b border-sidebar-border/60">
          <div className="flex items-center gap-2">
            <div
              className="text-[0.6875rem] font-semibold uppercase tracking-[0.1em] text-muted-foreground/80 px-2"
              data-tutorial="sidebar-logo"
            >
              {msg("auto.features.sidebar.components.sidebar.1")}
            </div>
          </div>
          <button
            type="button"
            onClick={() => setCollapsed(true)}
            className="p-1.5 rounded-lg hover:bg-sidebar-accent/40 cursor-pointer transition-colors text-muted-foreground"
            title={msg("auto.features.sidebar.components.sidebar.literal.5")}
            aria-label={msg("auto.features.sidebar.components.sidebar.literal.6")}
          >
            <PanelRightClose className="size-3.5" />
          </button>
        </div>

        <nav
          className="flex flex-col gap-1 px-3 py-3"
          role="navigation"
          aria-label={msg("auto.features.sidebar.components.sidebar.literal.7")}
          data-tutorial="sidebar-nav"
        >
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            const showBadge = href === "/" && activeCount > 0;
            return (
              <Link
                key={href}
                href={href}
                {...(href === "/tagger" && !collapsed ? { "data-tutorial": "sidebar-tagger" } : {})}
                className={cn(
                  "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200",
                  active
                    ? "text-primary"
                    : "text-sidebar-foreground/60 hover:bg-sidebar-accent/40 hover:text-sidebar-foreground hover:translate-x-[-2px]",
                )}
              >
                {active && (
                  <motion.div
                    layoutId="sidebar-active"
                    className="absolute inset-0 rounded-lg bg-primary/[0.08] ring-1 ring-primary/10"
                    style={{ borderRight: "3px solid var(--primary)" }}
                    transition={{ type: "spring", stiffness: 350, damping: 28 }}
                  />
                )}
                <span className="relative z-10 flex items-center gap-3 flex-1">
                  <Icon
                    className={cn(
                      "size-4 transition-colors duration-200",
                      active ? "text-primary" : "group-hover:text-sidebar-foreground",
                    )}
                  />
                  {label}
                  {showBadge && (
                    <span className="mr-auto text-[0.625rem] font-bold bg-primary/10 text-primary px-1.5 py-0.5 rounded-full tabular-nums">
                      {activeCount}
                    </span>
                  )}
                </span>
              </Link>
            );
          })}
        </nav>

        <div className="flex-1 overflow-hidden flex flex-col min-h-0">
          <div className="px-3 py-2">
            <div className="relative">
              <Search className="absolute end-2.5 top-1/2 -translate-y-1/2 size-3 text-muted-foreground/40 pointer-events-none" />
              <input
                ref={searchRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={msg("auto.features.sidebar.components.sidebar.literal.8")}
                aria-label={formatMsg("auto.features.sidebar.components.sidebar.template.1", {
                  p1: TERMS.optimizationPlural,
                })}
                dir="rtl"
                className="w-full text-[0.6875rem] bg-sidebar-accent/30 border border-border/30 rounded-lg pe-7 ps-7 py-1.5 outline-none focus:border-primary/30 transition-colors placeholder:text-muted-foreground/40"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute start-2.5 top-1/2 -translate-y-1/2 cursor-pointer text-muted-foreground/40 hover:text-muted-foreground"
                  aria-label={msg("auto.features.sidebar.components.sidebar.literal.9")}
                >
                  <X className="size-3" />
                </button>
              )}
            </div>
          </div>
          <div ref={listRef} className="flex-1 overflow-y-auto px-3 pb-2 no-scrollbar">
            {groupedJobs.length === 0 && searchQuery && (
              <p className="text-[0.625rem] text-muted-foreground/50 text-center py-4">
                {msg("auto.features.sidebar.components.sidebar.2")}
              </p>
            )}
            {groupedJobs.map((group) => (
              <div key={group.label} className="mb-2">
                <p className="flex items-center gap-1.5 text-[0.625rem] font-semibold uppercase tracking-[0.1em] text-muted-foreground/50 px-2 py-1.5">
                  <span>{group.label}</span>
                  <span className="tabular-nums text-muted-foreground/40 font-normal">
                    {group.jobs.length}
                  </span>
                </p>
                {group.jobs.map((job) => (
                  <JobRow
                    key={job.optimization_id}
                    job={job}
                    isActive={pathname === `/optimizations/${job.optimization_id}`}
                    activePair={
                      pathname === `/optimizations/${job.optimization_id}` ? activePairIndex : null
                    }
                    onDelete={handleDelete}
                    onRefresh={fetchData}
                  />
                ))}
              </div>
            ))}
            {loadingMore && (
              <div className="px-1 pt-1 pb-2" aria-hidden="true">
                <Skeleton
                  name="sidebar-more"
                  loading={true}
                  initialBones={sidebarMoreBones}
                  color="var(--muted)"
                  animate="shimmer"
                >
                  <div />
                </Skeleton>
              </div>
            )}
            {!loadedAll && !searchQuery && (
              <div ref={sentinelRef} aria-hidden="true" className="h-1 w-full" />
            )}
          </div>
        </div>

        <div className="px-3 py-2 border-t border-sidebar-border/60">
          <SettingsTrigger />
        </div>
      </div>

      <Dialog
        open={deleteConfirm !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteConfirm(null);
        }}
      >
        <DialogContent className="max-w-sm sm:max-w-sm" showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>
              {msg("auto.features.sidebar.components.sidebar.3")}
              {TERMS.optimization}
            </DialogTitle>
            <DialogDescription>
              {msg("auto.features.sidebar.components.sidebar.4")}
              {TERMS.optimization}{" "}
              <span className="font-medium text-foreground break-words" dir="auto">
                {deleteJobInfo?.name}
              </span>
              ?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-2 gap-3">
            <Button
              variant="outline"
              onClick={() => setDeleteConfirm(null)}
              disabled={deleteLoading}
              className="w-full justify-center"
            >
              {msg("auto.features.sidebar.components.sidebar.5")}
            </Button>
            <Button
              variant="destructive"
              onClick={confirmDelete}
              disabled={deleteLoading}
              className="w-full justify-center"
            >
              {deleteLoading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                msg("auto.features.sidebar.components.sidebar.literal.10")
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </aside>
  );
}

function JobRow({
  job,
  isActive,
  activePair,
  onDelete,
  onRefresh,
}: {
  job: SidebarJobItem;
  isActive: boolean;
  activePair: number | null;
  onDelete: (e: React.MouseEvent, id: string) => void;
  onRefresh: () => void;
}) {
  const router = useRouter();
  const { prefs } = useUserPrefs();
  const [menuOpen, setMenuOpen] = React.useState(false);
  const [renaming, setRenaming] = React.useState(false);
  const [renameValue, setRenameValue] = React.useState("");
  const [menuPos, setMenuPos] = React.useState<{ top: number; left: number } | null>(null);
  const [expanded, setExpanded] = React.useState(isActive && activePair !== null);
  const menuRef = React.useRef<HTMLDivElement>(null);
  const btnRef = React.useRef<HTMLButtonElement>(null);
  const renameRef = React.useRef<HTMLInputElement>(null);
  const isGridSearch =
    prefs.advancedMode &&
    job.optimization_type === "grid_search" &&
    (job.total_pairs ?? 0) > 0;
  const displayName =
    job.name ||
    [job.module_name, job.optimizer_name].filter(Boolean).join(" · ") ||
    job.optimization_id.slice(0, 8);

  const dropdownRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node;
      if (menuRef.current?.contains(target)) return;
      if (dropdownRef.current?.contains(target)) return;
      setMenuOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuOpen(false);
        btnRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  React.useEffect(() => {
    if (renaming) renameRef.current?.focus();
  }, [renaming]);

  const handleShare = () => {
    const url = `${window.location.origin}/optimizations/${job.optimization_id}`;
    navigator.clipboard
      .writeText(url)
      .then(() => toast.success(msg("sidebar.link.copied")))
      .catch(() => toast.error(msg("clipboard.copy_failed")));
    setMenuOpen(false);
  };

  const handleClone = () => {
    setMenuOpen(false);
    router.push(`/submit?clone=${job.optimization_id}`);
  };

  // Enter triggers handleRename, then setRenaming(false) blurs the input,
  // which fires onBlur → handleRename again. Guard against the double-fire.
  const renameSubmittedRef = React.useRef(false);
  const handleRename = async () => {
    if (renameSubmittedRef.current) return;
    renameSubmittedRef.current = true;
    const newName = renameValue.trim();
    if (!newName || newName === (job.name ?? "")) {
      setRenaming(false);
      renameSubmittedRef.current = false;
      return;
    }
    try {
      await renameOptimization(job.optimization_id, newName);
      toast.success(msg("sidebar.rename.success"));
      window.dispatchEvent(
        new CustomEvent("optimization-renamed", {
          detail: { optimizationId: job.optimization_id, name: newName },
        }),
      );
      window.dispatchEvent(new Event("optimizations-changed"));
      onRefresh();
    } catch {
      toast.error(msg("sidebar.rename.failed"));
    }
    setRenaming(false);
    renameSubmittedRef.current = false;
  };

  const handlePin = async () => {
    try {
      const res = await togglePinOptimization(job.optimization_id);
      toast.success(res.pinned ? msg("sidebar.pin.on") : msg("sidebar.pin.off"));
      window.dispatchEvent(
        new CustomEvent("optimization-updated", {
          detail: { optimizationId: job.optimization_id },
        }),
      );
      window.dispatchEvent(new Event("optimizations-changed"));
      onRefresh();
    } catch {
      toast.error(msg("sidebar.generic_error"));
    }
    setMenuOpen(false);
  };

  if (renaming) {
    return (
      <div className="px-2 py-1.5">
        <input
          ref={renameRef}
          type="text"
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void handleRename();
            }
            if (e.key === "Escape") {
              renameSubmittedRef.current = true;
              setRenaming(false);
              renameSubmittedRef.current = false;
            }
          }}
          onBlur={handleRename}
          maxLength={120}
          className="w-full text-[0.6875rem] bg-sidebar-accent/30 border border-primary/30 rounded-md px-2 py-1 outline-none font-medium"
          dir="auto"
        />
      </div>
    );
  }

  return (
    <div className="relative" ref={menuRef}>
      <div
        className={cn(
          "flex items-center gap-1.5 rounded-lg px-2 py-2 text-[0.6875rem] transition-all duration-150",
          isActive
            ? "bg-primary/[0.07] text-foreground"
            : "text-muted-foreground hover:bg-sidebar-accent/30 hover:text-foreground",
        )}
      >
        <Link
          href={`/optimizations/${job.optimization_id}`}
          className="flex items-center gap-2 min-w-0 flex-1 overflow-hidden"
        >
          <StatusDot status={job.status} />
          {job.pinned && <Pin className="size-2.5 text-muted-foreground/60 shrink-0" />}
          <span
            className="truncate font-medium leading-tight min-w-0 block"
            dir="auto"
            title={displayName}
          >
            {displayName}
          </span>
          {isGridSearch && (
            <span
              className="inline-flex items-center gap-0.5 text-[9px] font-semibold text-muted-foreground/60 bg-muted/40 px-1 py-0.5 rounded shrink-0"
              title={formatMsg("auto.features.sidebar.components.sidebar.template.2", {
                p1: job.total_pairs ?? "?",
              })}
            >
              <Grid2x2 className="size-2.5" />
              {job.total_pairs ?? "?"}
            </span>
          )}
        </Link>
        {isGridSearch && (
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setExpanded((o) => !o);
            }}
            className="p-0.5 rounded cursor-pointer text-muted-foreground/40 hover:text-foreground transition-colors shrink-0"
            aria-label={
              expanded
                ? msg("auto.features.sidebar.components.sidebar.literal.11")
                : msg("auto.features.sidebar.components.sidebar.literal.12")
            }
          >
            <ChevronLeft
              className={cn("size-3.5 transition-transform duration-200", expanded && "-rotate-90")}
            />
          </button>
        )}
        {
          <button
            ref={btnRef}
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              if (!menuOpen && btnRef.current) {
                const rect = btnRef.current.getBoundingClientRect();
                const menuWidth = 140;
                const menuHeightEstimate = 200;
                const margin = 8;
                // Right-align by default; clamp to viewport so the menu
                // never overflows the screen edge on narrow windows.
                const left = Math.max(
                  margin,
                  Math.min(rect.right - menuWidth, window.innerWidth - menuWidth - margin),
                );
                const top =
                  rect.bottom + menuHeightEstimate + margin > window.innerHeight
                    ? Math.max(margin, rect.top - menuHeightEstimate - 4)
                    : rect.bottom + 4;
                setMenuPos({ top, left });
              }
              setMenuOpen((o) => !o);
            }}
            className="p-0.5 rounded cursor-pointer text-muted-foreground/40 hover:text-foreground transition-colors shrink-0"
            aria-label={formatMsg("auto.features.sidebar.components.sidebar.template.3", {
              p1: displayName,
            })}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            <MoreHorizontal className="size-3.5" />
          </button>
        }
      </div>

      <AnimatePresence>
        {expanded && isGridSearch && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="ps-6 pe-2 pb-1">
              {Array.from({ length: job.total_pairs ?? 0 }, (_, i) => {
                const isPairActive = isActive && activePair === i;
                const pairStatus = derivePairStatus(
                  i,
                  job.status,
                  job.completed_pairs ?? 0,
                  job.failed_pairs ?? 0,
                );
                return (
                  <Link
                    key={i}
                    href={`/optimizations/${job.optimization_id}?pair=${i}`}
                    className={cn(
                      "flex items-center gap-2 rounded-md px-2 py-1.5 text-[0.625rem] transition-all duration-150",
                      isPairActive
                        ? "bg-primary/[0.07] text-foreground font-semibold"
                        : "text-muted-foreground/70 hover:bg-sidebar-accent/30 hover:text-foreground",
                    )}
                  >
                    <StatusDot status={pairStatus} />
                    <span>
                      {msg("auto.features.sidebar.components.sidebar.6")}
                      {i + 1}
                    </span>
                  </Link>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Dropdown menu — portaled to body to escape overflow clipping */}
      {menuOpen &&
        menuPos &&
        createPortal(
          <motion.div
            ref={dropdownRef}
            role="menu"
            initial={{ opacity: 0, scale: 0.95, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -4 }}
            transition={{ duration: 0.12 }}
            className="fixed z-[9999] min-w-[140px] rounded-2xl border border-border/40 bg-card shadow-[0_4px_24px_rgba(28,22,18,0.1)] py-1.5"
            style={{ top: menuPos.top, left: menuPos.left, right: "auto" }}
          >
            <button
              type="button"
              role="menuitem"
              onClick={handleShare}
              className="w-full flex items-center gap-2.5 px-3 py-1.5 text-[0.6875rem] text-foreground hover:bg-muted/40 cursor-pointer transition-colors"
            >
              <Share2 className="size-3.5 text-muted-foreground" />
              {msg("auto.features.sidebar.components.sidebar.7")}
            </button>

            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setMenuOpen(false);
                setRenameValue(job.name ?? displayName);
                setRenaming(true);
              }}
              className="w-full flex items-center gap-2.5 px-3 py-1.5 text-[0.6875rem] text-foreground hover:bg-muted/40 cursor-pointer transition-colors"
            >
              <Pencil className="size-3.5 text-muted-foreground" />
              {msg("auto.features.sidebar.components.sidebar.8")}
            </button>

            <button
              type="button"
              role="menuitem"
              onClick={handleClone}
              className="w-full flex items-center gap-2.5 px-3 py-1.5 text-[0.6875rem] text-foreground hover:bg-muted/40 cursor-pointer transition-colors"
            >
              <CopyPlus className="size-3.5 text-muted-foreground" />
              {msg("auto.features.sidebar.components.sidebar.9")}
            </button>

            <div className="h-px bg-border/20 mx-2 my-1" />

            <button
              type="button"
              role="menuitem"
              onClick={handlePin}
              className="w-full flex items-center gap-2.5 px-3 py-1.5 text-[0.6875rem] text-foreground hover:bg-muted/40 cursor-pointer transition-colors"
            >
              <Pin
                className={cn("size-3.5", job.pinned ? "text-foreground" : "text-muted-foreground")}
              />
              {job.pinned
                ? msg("auto.features.sidebar.components.sidebar.literal.13")
                : msg("auto.features.sidebar.components.sidebar.literal.14")}
            </button>

            <button
              type="button"
              role="menuitem"
              onClick={(e) => {
                setMenuOpen(false);
                onDelete(e, job.optimization_id);
              }}
              className="w-full flex items-center gap-2.5 px-3 py-1.5 text-[0.6875rem] text-red-500 hover:bg-red-500/5 cursor-pointer transition-colors"
            >
              <Trash2 className="size-3.5" />
              {msg("auto.features.sidebar.components.sidebar.10")}
            </button>
          </motion.div>,
          document.body,
        )}
    </div>
  );
}

function derivePairStatus(
  index: number,
  parentStatus: string,
  completedPairs: number,
  failedPairs: number,
): string {
  if (index < completedPairs) return "success";
  if (index < completedPairs + failedPairs) return "failed";
  return parentStatus;
}

function StatusDot({ status }: { status: string }) {
  const isRunning = isActiveStatus(status);
  return (
    <span className="relative flex size-2 shrink-0">
      {isRunning && (
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--warning)]/60" />
      )}
      <span
        className={cn(
          "relative inline-flex rounded-full size-2",
          status === "success"
            ? "bg-[var(--success)]"
            : status === "failed"
              ? "bg-[var(--danger)]"
              : status === "cancelled"
                ? "bg-[#6b6058]"
                : "bg-[var(--warning)]",
        )}
      />
    </span>
  );
}
