"use client";

import * as React from "react";
import { Check, ChevronDown, Search, Loader2, RefreshCw } from "lucide-react";

import { cn } from "@/shared/lib/utils";
import { getModelCatalog, cachedCatalog, discoverModels } from "@/shared/lib/model-catalog";
import type { CatalogModel, CatalogProvider } from "@/shared/types/api";

interface ModelPickerProps {
  value: string;
  onChange: (next: string) => void;
  id?: string;
  placeholder?: string;
  /** If set, also fetch models from this base URL's /v1/models endpoint. */
  discoverUrl?: string;
  discoverApiKey?: string;
  disabled?: boolean;
  className?: string;
  /** Constrain picks to this provider slug (e.g. "openai"). */
  providerFilter?: string;
}

interface EnrichedModel extends CatalogModel {
  fromDiscovery?: boolean;
}

function formatCtx(tokens?: number): string {
  if (!tokens) return "";
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
  return `${Math.round(tokens / 1000)}K`;
}

/** Searchable combobox for DSPy model IDs. Curated static catalog + live discovery. */
export function ModelPicker({
  value,
  onChange,
  id,
  placeholder = "בחר מודל...",
  discoverUrl,
  discoverApiKey,
  disabled,
  className,
  providerFilter,
}: ModelPickerProps) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  // Use cached catalog instantly (prefetched on module load); fallback to async
  const [catalog, setCatalog] = React.useState<{
    providers: CatalogProvider[];
    models: CatalogModel[];
  } | null>(cachedCatalog);
  const [catalogError, setCatalogError] = React.useState<string | null>(null);
  const [discovered, setDiscovered] = React.useState<string[]>([]);
  const [discovering, setDiscovering] = React.useState(false);
  const [discoveryError, setDiscoveryError] = React.useState<string | null>(null);

  const rootRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // If cache wasn't ready at mount time, await it once
  React.useEffect(() => {
    if (catalog) return;
    let cancelled = false;
    getModelCatalog()
      .then((c) => {
        if (!cancelled) setCatalog(c);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [catalog]);

  const runDiscover = React.useCallback(async () => {
    if (!discoverUrl) {
      setDiscovered([]);
      setDiscoveryError(null);
      return;
    }
    setDiscovering(true);
    setDiscoveryError(null);
    try {
      const res = await discoverModels(discoverUrl, discoverApiKey);
      setDiscovered(res.models);
      if (res.error) setDiscoveryError(res.error);
    } catch (e) {
      setDiscoveryError(e instanceof Error ? e.message : "שגיאה בגילוי מודלים");
    } finally {
      setDiscovering(false);
    }
  }, [discoverUrl, discoverApiKey]);

  // Auto-run discovery when URL stabilizes
  React.useEffect(() => {
    if (!discoverUrl) {
      setDiscovered([]);
      setDiscoveryError(null);
      return;
    }
    const t = setTimeout(() => {
      runDiscover();
    }, 400);
    return () => clearTimeout(t);
  }, [discoverUrl, runDiscover]);

  React.useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  React.useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  const allModels: EnrichedModel[] = React.useMemo(() => {
    const staticModels = catalog?.models ?? [];
    const filtered = providerFilter
      ? staticModels.filter((m) => m.provider === providerFilter)
      : staticModels;
    if (discovered.length === 0) return filtered;
    const existingValues = new Set(filtered.map((m) => m.value));
    const discoveredEntries: EnrichedModel[] = discovered
      .filter((id) => !existingValues.has(id))
      .map((id) => ({
        value: id,
        label: id,
        provider: "discovered",
        supports_thinking: false,
        available: true,
        fromDiscovery: true,
      }));
    return [...discoveredEntries, ...filtered];
  }, [catalog, discovered, providerFilter]);

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return allModels;
    return allModels.filter(
      (m) => m.value.toLowerCase().includes(q) || m.label.toLowerCase().includes(q),
    );
  }, [allModels, query]);

  const grouped = React.useMemo(() => {
    const groups = new Map<string, EnrichedModel[]>();
    for (const m of filtered) {
      const arr = groups.get(m.provider) ?? [];
      arr.push(m);
      groups.set(m.provider, arr);
    }
    return groups;
  }, [filtered]);

  const providerLabel = React.useCallback(
    (slug: string): string => {
      if (slug === "discovered") return `מהשרת (${discoverUrl ?? ""})`;
      return catalog?.providers.find((p) => p.slug === slug)?.label ?? slug;
    },
    [catalog, discoverUrl],
  );

  const selectedModel = allModels.find((m) => m.value === value);

  const commit = (next: string) => {
    onChange(next);
    setOpen(false);
    setQuery("");
  };

  return (
    <div ref={rootRef} className={cn("relative w-full", className)}>
      <button
        type="button"
        id={id}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "flex w-full items-center justify-between gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm",
          "shadow-xs cursor-pointer transition-[border-color,background-color,box-shadow] duration-120",
          "hover:border-foreground/20 hover:bg-accent/40",
          "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none",
          "disabled:cursor-not-allowed disabled:opacity-50",
          open && "border-foreground/25 bg-accent/40",
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        {value ? (
          <span className="flex min-w-0 flex-1 items-center gap-2" dir="ltr">
            <span className="truncate font-mono text-[0.8125rem]">{selectedModel?.label ?? value}</span>
          </span>
        ) : (
          <span className="flex min-w-0 flex-1 items-center gap-2 text-muted-foreground">
            {placeholder}
          </span>
        )}
        <ChevronDown
          className={cn(
            "size-4 shrink-0 text-muted-foreground transition-transform duration-150",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div
          className={cn(
            "absolute z-50 mt-1 w-full overflow-hidden rounded-xl border border-border/70 bg-popover shadow-lg",
            "animate-in fade-in-0 zoom-in-95 slide-in-from-top-1",
          )}
          role="listbox"
        >
          {/* Search */}
          <div className="flex items-center gap-2 border-b border-border/50 px-3 py-2">
            <Search className="size-3.5 shrink-0 text-muted-foreground" />
            <input
              ref={inputRef}
              dir="ltr"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search models..."
              className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setOpen(false);
                }
              }}
            />
            {discoverUrl && (
              <button
                type="button"
                onClick={runDiscover}
                disabled={discovering}
                className="flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-[0.6875rem] font-medium text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
                title="רענן מודלים מהשרת"
              >
                {discovering ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : (
                  <RefreshCw className="size-3" />
                )}
                רענן
              </button>
            )}
          </div>

          {/* List */}
          <div className="max-h-[120px] overflow-y-auto py-1">
            {discoveryError && discoverUrl && (
              <div className="px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
                לא ניתן לגלות מודלים מ-{discoverUrl}: {discoveryError}
              </div>
            )}
            {filtered.length === 0 && (
              <div className="px-3 py-8 text-center text-xs text-muted-foreground">
                לא נמצאו מודלים
              </div>
            )}
            {Array.from(grouped.entries()).map(([provider, items]) => (
              <div key={provider} className="py-1">
                <div
                  className="px-3 py-1 text-[0.625rem] font-semibold uppercase tracking-wider text-muted-foreground text-start"
                  dir="ltr"
                >
                  {providerLabel(provider)}
                </div>
                {items.map((m) => (
                  <button
                    key={m.value}
                    type="button"
                    onClick={() => commit(m.value)}
                    className={cn(
                      "flex w-full items-center gap-2 px-3 py-1.5 text-start text-sm transition-colors",
                      "hover:bg-accent/70",
                      value === m.value && "bg-accent/50",
                      !m.available && "opacity-60",
                    )}
                    role="option"
                    aria-selected={value === m.value}
                  >
                    <span className="flex min-w-0 flex-1 items-center gap-1.5" dir="ltr">
                      <span className="truncate text-[0.8125rem]">{m.label}</span>
                      {m.max_input_tokens && (
                        <span className="shrink-0 text-[9px] tabular-nums text-muted-foreground">
                          {formatCtx(m.max_input_tokens)}
                        </span>
                      )}
                    </span>
                    <Check
                      className={cn(
                        "size-3.5 shrink-0",
                        value === m.value ? "opacity-100" : "opacity-0",
                      )}
                    />
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** Is this a model that supports reasoning_effort? Trusts the LiteLLM catalog flag exclusively. */
export function modelSupportsThinking(modelValue: string, models?: CatalogModel[]): boolean {
  if (!modelValue || !models) return false;
  const hit = models.find((m) => m.value === modelValue);
  return hit?.supports_thinking ?? false;
}
