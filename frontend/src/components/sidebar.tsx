"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { LayoutDashboard, Send, Play, Trash2, Search, PanelRightClose, PanelRightOpen, X, MoreHorizontal, Share2, Pencil, Pin, Loader2, Grid2x2, ChevronLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { listJobs, listJobsSidebar, deleteJob, renameOptimization, togglePinOptimization } from "@/lib/api";
import type { SidebarJobItem } from "@/lib/api";
import { ACTIVE_STATUSES, STATUS_LABELS } from "@/lib/constants";
import type { OptimizationSummaryResponse } from "@/lib/types";
// Sidebar now uses SidebarJobItem from api.ts but falls back to OptimizationSummaryResponse shape
import { toast } from "react-toastify";
import { useSession } from "next-auth/react";
import { groupJobsByRecency, matchesJobSearch } from "@/features/sidebar";
import { msg } from "@/features/shared/messages";

const NAV_ITEMS = [
  { href: "/", label: "לוח בקרה", icon: LayoutDashboard },
  { href: "/submit", label: "אופטימיזציה חדשה", icon: Send },
] as const;

const PAGE_SIZE = 20;

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const activePairParam = searchParams.get("pair");
  const activePairIndex = activePairParam != null ? parseInt(activePairParam, 10) : null;
  const { data: session } = useSession();
  const sessionUser = session?.user?.name ?? "";
  const isAdmin = (session?.user as Record<string, unknown> | undefined)?.role === "admin";
  const [collapsed, setCollapsed] = React.useState(false);

  // Listen for external collapse requests (e.g. submit splash transition)
  React.useEffect(() => {
    const handler = () => setCollapsed(true);
    window.addEventListener("sidebar:collapse", handler);
    return () => window.removeEventListener("sidebar:collapse", handler);
  }, []);

  const [jobs, setJobs] = React.useState<SidebarJobItem[]>([]);
  const [totalJobs, setTotalJobs] = React.useState(0);
  const [activeCount, setActiveCount] = React.useState(0);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [loadedAll, setLoadedAll] = React.useState(false);
  const listRef = React.useRef<HTMLDivElement>(null);
  const searchRef = React.useRef<HTMLInputElement>(null);

  const fetchData = React.useCallback(async () => {
    try {
      const res = await listJobsSidebar({
        username: isAdmin ? undefined : (sessionUser || undefined),
        limit: PAGE_SIZE,
        offset: 0,
      });
      setJobs(res.items);
      setTotalJobs(res.total);
      setActiveCount(res.items.filter(j => ACTIVE_STATUSES.has(j.status as never)).length);
      setLoadedAll(res.items.length >= res.total);
    } catch { /* ignore */ }
  }, [sessionUser, isAdmin]);

  React.useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    // Listen for cross-component invalidation (dashboard delete, etc.)
    const onJobsChanged = () => fetchData();
    window.addEventListener("optimizations-changed", onJobsChanged);
    return () => {
      clearInterval(interval);
      window.removeEventListener("optimizations-changed", onJobsChanged);
    };
  }, [fetchData]);

  const loadMore = async () => {
    if (loadedAll) return;
    try {
      const res = await listJobsSidebar({
        username: isAdmin ? undefined : (sessionUser || undefined),
        limit: PAGE_SIZE,
        offset: jobs.length,
      });
      setJobs(prev => [...prev, ...res.items]);
      setLoadedAll(jobs.length + res.items.length >= res.total);
    } catch { /* ignore */ }
  };

  const [deleteConfirm, setDeleteConfirm] = React.useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = React.useState(false);

  const handleDelete = (e: React.MouseEvent, optimizationId: string) => {
    e.preventDefault();
    e.stopPropagation();
    setDeleteConfirm(optimizationId);
  };

  const confirmDelete = async () => {
    const optimizationId = deleteConfirm;
    if (!optimizationId) return;
    setDeleteLoading(true);
    setJobs((prev) => prev.filter((j) => j.optimization_id !== optimizationId));
    setTotalJobs((prev) => Math.max(0, prev - 1));
    try {
      await deleteJob(optimizationId);
      toast.success(msg("sidebar.delete.success"));
      window.dispatchEvent(new Event("optimizations-changed"));
      if (pathname === `/optimizations/${optimizationId}`) router.push("/");
    } catch {
      toast.error(msg("sidebar.delete.failed"));
      fetchData();
    } finally {
      setDeleteLoading(false);
      setDeleteConfirm(null);
    }
  };

  // Filter + group jobs via the pure helpers in features/sidebar
  const filteredJobs = React.useMemo(
    () => jobs.filter((j) => matchesJobSearch(j, searchQuery)),
    [jobs, searchQuery],
  );
  const groupedJobs = React.useMemo(() => groupJobsByRecency(filteredJobs), [filteredJobs]);

  // Scroll to load more
  const handleScroll = () => {
    const el = listRef.current;
    if (!el || loadedAll) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 40) {
      loadMore();
    }
  };

  return (
    <aside
      className={cn(
        "relative flex h-full shrink-0 flex-col border-l border-sidebar-border/60 bg-sidebar/80 backdrop-blur-xl overflow-hidden transition-[width] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]"
      )}
      style={{ width: collapsed ? "3rem" : "clamp(200px, 16vw, 240px)" }}
      dir="rtl"
      data-tutorial="sidebar-full"
    >
      {/* Collapsed view */}
      <div className={cn(
        "absolute inset-0 flex flex-col items-center py-3 gap-2 transition-opacity duration-200",
        collapsed ? "opacity-100 pointer-events-auto delay-150" : "opacity-0 pointer-events-none"
      )}>
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className="p-2 rounded-lg hover:bg-sidebar-accent/40 cursor-pointer transition-colors"
          title="פתח סרגל צד"
          aria-label="פתח סרגל צד"
        >
          <PanelRightOpen className="size-4 text-muted-foreground" />
        </button>
        <div className="w-6 h-px bg-border/40 my-1" />
        {NAV_ITEMS.map(({ href, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "p-2 rounded-lg transition-colors",
                active ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-sidebar-accent/40 hover:text-foreground"
              )}
              title={NAV_ITEMS.find(n => n.href === href)?.label}
              aria-label={NAV_ITEMS.find(n => n.href === href)?.label}
            >
              <Icon className="size-4" />
            </Link>
          );
        })}
      </div>

      {/* Expanded view */}
      <div className={cn(
        "flex flex-col h-full min-w-[14rem] transition-opacity duration-200",
        collapsed ? "opacity-0 pointer-events-none" : "opacity-100 pointer-events-auto delay-150"
      )}>
      {/* Header with collapse */}
      <div className="flex items-center justify-between px-3 py-3 border-b border-sidebar-border/60">
        <div className="flex items-center gap-2">
          <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground/80 px-2" data-tutorial="sidebar-logo">
            Skynet
          </div>
        </div>
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          className="p-1.5 rounded-lg hover:bg-sidebar-accent/40 cursor-pointer transition-colors text-muted-foreground"
          title="כווץ סרגל צד"
          aria-label="כווץ סרגל צד"
        >
          <PanelRightClose className="size-3.5" />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-1 px-3 py-3" role="navigation" aria-label="ניווט ראשי" data-tutorial="sidebar-nav">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          const showBadge = href === "/" && activeCount > 0;
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200",
                active
                  ? "text-primary"
                  : "text-sidebar-foreground/60 hover:bg-sidebar-accent/40 hover:text-sidebar-foreground hover:translate-x-[-2px]"
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
                <Icon className={cn("size-4 transition-colors duration-200", active ? "text-primary" : "group-hover:text-sidebar-foreground")} />
                {label}
                {showBadge && (
                  <span className="mr-auto text-[10px] font-bold bg-primary/10 text-primary px-1.5 py-0.5 rounded-full tabular-nums">
                    {activeCount}
                  </span>
                )}
              </span>
            </Link>
          );
        })}
      </nav>

      {/* Jobs list */}
      <div className="flex-1 overflow-hidden flex flex-col min-h-0">
        {/* Search */}
        <div className="px-3 py-2">
          <div className="relative">
            <Search className="absolute end-2.5 top-1/2 -translate-y-1/2 size-3 text-muted-foreground/40 pointer-events-none" />
            <input
              ref={searchRef}
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="חיפוש..."
              aria-label="חיפוש אופטימיזציות"
              dir="rtl"
              className="w-full text-[11px] bg-sidebar-accent/30 border border-border/30 rounded-lg pe-7 ps-7 py-1.5 outline-none focus:border-primary/30 transition-colors placeholder:text-muted-foreground/40"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute start-2.5 top-1/2 -translate-y-1/2 cursor-pointer text-muted-foreground/40 hover:text-muted-foreground"
                aria-label="נקה חיפוש"
              >
                <X className="size-3" />
              </button>
            )}
          </div>
        </div>
        <div
          ref={listRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto px-3 pb-2 no-scrollbar"
        >
          {groupedJobs.length === 0 && searchQuery && (
            <p className="text-[10px] text-muted-foreground/50 text-center py-4">לא נמצאו תוצאות</p>
          )}
          {groupedJobs.map(group => (
            <div key={group.label} className="mb-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-foreground/50 px-2 py-1.5">
                {group.label}
              </p>
              {group.jobs.map(job => (
                <JobRow
                  key={job.optimization_id}
                  job={job}
                  isActive={pathname === `/optimizations/${job.optimization_id}`}
                  activePair={pathname === `/optimizations/${job.optimization_id}` ? activePairIndex : null}
                  onDelete={handleDelete}
                  onUse={(e, id) => { e.preventDefault(); e.stopPropagation(); router.push(`/optimizations/${id}?tab=playground`); }}
                  onRefresh={fetchData}
                />
              ))}
            </div>
          ))}
          {!loadedAll && filteredJobs.length > 0 && (
            <button
              type="button"
              onClick={loadMore}
              className="w-full text-[10px] text-muted-foreground/50 hover:text-muted-foreground py-2 cursor-pointer transition-colors"
            >
              טען עוד ({totalJobs - jobs.length} נוספים)
            </button>
          )}
        </div>
      </div>

      </div>

      {/* Delete confirmation dialog */}
      <Dialog open={deleteConfirm !== null} onOpenChange={(open) => { if (!open) setDeleteConfirm(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>מחיקת אופטימיזציה</DialogTitle>
            <DialogDescription>
              האם למחוק את האופטימיזציה{" "}
              <span className="font-mono font-medium text-foreground break-all">{deleteConfirm}</span>
              ?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="grid grid-cols-2 gap-2">
            <Button variant="outline" onClick={() => setDeleteConfirm(null)} disabled={deleteLoading} className="w-full justify-center">
              ביטול
            </Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={deleteLoading} className="w-full justify-center">
              {deleteLoading ? <Loader2 className="size-4 animate-spin" /> : "מחיקה"}
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
  onUse,
  onRefresh,
}: {
  job: SidebarJobItem;
  isActive: boolean;
  activePair: number | null;
  onDelete: (e: React.MouseEvent, id: string) => void;
  onUse: (e: React.MouseEvent, id: string) => void;
  onRefresh: () => void;
}) {
  const [menuOpen, setMenuOpen] = React.useState(false);
  const [renaming, setRenaming] = React.useState(false);
  const [renameValue, setRenameValue] = React.useState("");
  const [menuPos, setMenuPos] = React.useState<{ top: number; left: number } | null>(null);
  const [expanded, setExpanded] = React.useState(isActive && activePair !== null);
  const menuRef = React.useRef<HTMLDivElement>(null);
  const btnRef = React.useRef<HTMLButtonElement>(null);
  const renameRef = React.useRef<HTMLInputElement>(null);
  const isLive = ACTIVE_STATUSES.has(job.status as never);
  const isSuccess = job.status === "success";
  const isGridSearch = job.optimization_type === "grid_search" && (job.total_pairs ?? 0) > 0;
  const displayName = job.name || [job.module_name, job.optimizer_name].filter(Boolean).join(" · ") || job.optimization_id.slice(0, 8);

  const dropdownRef = React.useRef<HTMLDivElement>(null);

  // Close menu on outside click
  React.useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (menuRef.current?.contains(target)) return;
      if (dropdownRef.current?.contains(target)) return;
      setMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  // Focus rename input
  React.useEffect(() => {
    if (renaming) renameRef.current?.focus();
  }, [renaming]);

  const handleShare = () => {
    const url = `${window.location.origin}/optimizations/${job.optimization_id}`;
    navigator.clipboard.writeText(url);
    toast.success(msg("sidebar.link.copied"));
    setMenuOpen(false);
  };

  const handleRename = async () => {
    const newName = renameValue.trim();
    if (!newName) { setRenaming(false); return; }
    try {
      await renameOptimization(job.optimization_id, newName);
      toast.success(msg("sidebar.rename.success"));
      window.dispatchEvent(new CustomEvent("optimization-renamed", { detail: { optimizationId: job.optimization_id, name: newName } }));
      window.dispatchEvent(new Event("optimizations-changed"));
      onRefresh();
    } catch {
      toast.error(msg("sidebar.rename.failed"));
    }
    setRenaming(false);
  };


  const handlePin = async () => {
    try {
      const res = await togglePinOptimization(job.optimization_id);
      toast.success(res.pinned ? msg("sidebar.pin.on") : msg("sidebar.pin.off"));
      window.dispatchEvent(new CustomEvent("optimization-updated", { detail: { optimizationId: job.optimization_id } }));
      window.dispatchEvent(new Event("optimizations-changed"));
      onRefresh();
    } catch {
      toast.error(msg("sidebar.generic_error"));
    }
    setMenuOpen(false);
  };

  // Rename mode
  if (renaming) {
    return (
      <div className="px-2 py-1.5">
        <input
          ref={renameRef}
          type="text"
          value={renameValue}
          onChange={e => setRenameValue(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") handleRename(); if (e.key === "Escape") setRenaming(false); }}
          onBlur={handleRename}
          className="w-full text-[11px] bg-sidebar-accent/30 border border-primary/30 rounded-md px-2 py-1 outline-none font-medium"
          dir="auto"
        />
      </div>
    );
  }

  return (
    <div className="relative" ref={menuRef}>
      <div className={cn(
        "flex items-center gap-1.5 rounded-lg px-2 py-2 text-[11px] transition-all duration-150",
        isActive
          ? "bg-primary/[0.07] text-foreground"
          : "text-muted-foreground hover:bg-sidebar-accent/30 hover:text-foreground"
      )}>
        <Link
          href={`/optimizations/${job.optimization_id}`}
          className="flex items-center gap-2 min-w-0 flex-1 overflow-hidden"
        >
          <StatusDot status={job.status} />
          {job.pinned && <Pin className="size-2.5 text-muted-foreground/60 shrink-0" />}
          <span className="truncate font-medium leading-tight min-w-0 block" dir="auto" title={displayName}>
            {displayName}
          </span>
          {isGridSearch && (
            <span className="inline-flex items-center gap-0.5 text-[9px] font-semibold text-muted-foreground/60 bg-muted/40 px-1 py-0.5 rounded shrink-0" title={`סריקה · ${job.total_pairs ?? "?"} זוגות`}>
              <Grid2x2 className="size-2.5" />
              {job.total_pairs ?? "?"}
            </span>
          )}

        </Link>
        {isGridSearch && (
          <button
            type="button"
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); setExpanded(o => !o); }}
            className="p-0.5 rounded cursor-pointer text-muted-foreground/40 hover:text-foreground transition-colors shrink-0"
            aria-label={expanded ? "כווץ ריצות" : "הרחב ריצות"}
          >
            <ChevronLeft className={cn("size-3.5 transition-transform duration-200", expanded && "-rotate-90")} />
          </button>
        )}
        {(
          <button
            ref={btnRef}
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              if (!menuOpen && btnRef.current) {
                const rect = btnRef.current.getBoundingClientRect();
                // Menu's right edge aligns with button's right edge
                setMenuPos({ top: rect.bottom + 4, left: rect.right - 140 });
              }
              setMenuOpen(o => !o);
            }}
            className="p-0.5 rounded cursor-pointer text-muted-foreground/40 hover:text-foreground transition-colors shrink-0"
            aria-label={`אפשרויות עבור ${displayName}`}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            <MoreHorizontal className="size-3.5" />
          </button>
        )}
      </div>

      {/* Expanded pair sub-items for grid search */}
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
              {Array.from({ length: job.total_pairs! }, (_, i) => {
                const isPairActive = isActive && activePair === i;
                return (
                  <Link
                    key={i}
                    href={`/optimizations/${job.optimization_id}?pair=${i}`}
                    className={cn(
                      "flex items-center gap-2 rounded-md px-2 py-1.5 text-[10px] transition-all duration-150",
                      isPairActive
                        ? "bg-primary/[0.07] text-foreground font-semibold"
                        : "text-muted-foreground/70 hover:bg-sidebar-accent/30 hover:text-foreground"
                    )}
                  >
                    <StatusDot status={job.status} />
                    <span>ריצה {i + 1}</span>
                  </Link>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Dropdown menu — portaled to body to escape overflow clipping */}
      {menuOpen && menuPos && createPortal(
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
            {/* Share */}
            <button
              type="button"
              role="menuitem"
              onClick={handleShare}
              className="w-full flex items-center gap-2.5 px-3 py-1.5 text-[11px] text-foreground hover:bg-muted/40 cursor-pointer transition-colors"
            >
              <Share2 className="size-3.5 text-muted-foreground" />
              שיתוף
            </button>

            {/* Rename */}
            <button
              type="button"
              role="menuitem"
              onClick={() => { setMenuOpen(false); setRenameValue(job.name ?? displayName); setRenaming(true); }}
              className="w-full flex items-center gap-2.5 px-3 py-1.5 text-[11px] text-foreground hover:bg-muted/40 cursor-pointer transition-colors"
            >
              <Pencil className="size-3.5 text-muted-foreground" />
              שינוי שם
            </button>

            <div className="h-px bg-border/20 mx-2 my-1" />

            {/* Pin */}
            <button
              type="button"
              role="menuitem"
              onClick={handlePin}
              className="w-full flex items-center gap-2.5 px-3 py-1.5 text-[11px] text-foreground hover:bg-muted/40 cursor-pointer transition-colors"
            >
              <Pin className={cn("size-3.5", job.pinned ? "text-foreground" : "text-muted-foreground")} />
              {job.pinned ? "הסר הצמדה" : "הצמדה"}
            </button>

            {/* Delete */}
            <button
              type="button"
              role="menuitem"
              onClick={(e) => { setMenuOpen(false); onDelete(e, job.optimization_id); }}
              className="w-full flex items-center gap-2.5 px-3 py-1.5 text-[11px] text-red-500 hover:bg-red-500/5 cursor-pointer transition-colors"
            >
              <Trash2 className="size-3.5" />
              מחיקה
            </button>
          </motion.div>,
        document.body,
      )}
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const isRunning = ACTIVE_STATUSES.has(status as never);
  return (
    <span className="relative flex size-2 shrink-0">
      {isRunning && (
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--warning)]/60" />
      )}
      <span className={cn(
        "relative inline-flex rounded-full size-2",
        status === "success" ? "bg-[var(--success)]" :
        status === "failed" ? "bg-[var(--danger)]" :
        status === "cancelled" ? "bg-[#6b6058]" :
        "bg-[var(--warning)]"
      )} />
    </span>
  );
}
