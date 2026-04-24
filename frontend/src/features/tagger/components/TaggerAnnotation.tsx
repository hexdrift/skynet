"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  ChevronRight,
  ChevronLeft,
  SkipBack,
  CircleMinus,
  Download,
  Keyboard,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Popover as PopoverPrimitive } from "radix-ui";
import { cn } from "@/shared/lib/utils";
import { exportAnnotations } from "../lib/export-csv";
import type { DataRow, Annotation, TaggerConfig } from "../lib/types";

interface Props {
  config: TaggerConfig;
  data: DataRow[];
  columns: string[];
  annotations: Record<string, Annotation>;
  currentIndex: number;
  taggedCount: number;
  distribution: Record<string, number>;
  onNavigate: (dir: 1 | -1) => void;
  onGoTo: (idx: number) => void;
  onJumpUntagged: () => void;
  onToggleBinary: (id: string, value: "yes" | "no") => void;
  onToggleCategory: (id: string, catId: string) => void;
  onSetFreetext: (id: string, text: string) => void;
  onBack: () => void;
}

export function TaggerAnnotation({
  config,
  data,
  columns,
  annotations,
  currentIndex,
  taggedCount,
  distribution,
  onNavigate,
  onGoTo,
  onJumpUntagged,
  onToggleBinary,
  onToggleCategory,
  onSetFreetext,
  onBack,
}: Props) {
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [showConfetti, setShowConfetti] = useState(false);
  const [exportConfirm, setExportConfirm] = useState<"csv" | "json" | "xlsx" | "xls" | null>(null);
  const confettiFired = useRef(false);
  const freetextRef = useRef<HTMLTextAreaElement>(null);

  const item = data[currentIndex];
  if (!item) return null;
  const id = String(item.id);
  const pct = data.length > 0 ? (taggedCount / data.length) * 100 : 0;
  const currentAnn = annotations[id];
  const isCurrentTagged =
    currentAnn !== undefined &&
    currentAnn !== "" &&
    !(Array.isArray(currentAnn) && currentAnn.length === 0);

  useEffect(() => {
    if (taggedCount === data.length && data.length > 0 && !confettiFired.current) {
      confettiFired.current = true;
      setShowConfetti(true);
      setTimeout(() => setShowConfetti(false), 4000);
    }
    if (taggedCount < data.length) confettiFired.current = false;
  }, [taggedCount, data.length]);

  const doExport = useCallback(
    (format: "csv" | "json" | "xlsx" | "xls") => {
      exportAnnotations(data, columns, annotations, config, format);
      setShowConfetti(true);
      setTimeout(() => setShowConfetti(false), 4000);
    },
    [data, columns, annotations, config],
  );

  const handleExport = useCallback(
    (format: "csv" | "json" | "xlsx" | "xls") => {
      if (taggedCount < data.length) {
        setExportConfirm(format);
      } else {
        doExport(format);
      }
    },
    [data.length, taggedCount, doExport],
  );

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "h") {
        e.preventDefault();
        setShowShortcuts((v) => !v);
        return;
      }
      if (e.key === "Escape") {
        if (showShortcuts) {
          setShowShortcuts(false);
          e.preventDefault();
          return;
        }
      }

      const tag = (e.target as HTMLElement).tagName;
      if (tag === "TEXTAREA" || tag === "INPUT") {
        if (e.key === "Escape") (e.target as HTMLElement).blur();
        return;
      }

      if (e.key === "ArrowLeft") {
        e.preventDefault();
        onNavigate(1);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        onNavigate(-1);
      } else if (e.key === "Home") {
        e.preventDefault();
        onGoTo(0);
      } else if (e.key === "u" || e.key === "U") {
        e.preventDefault();
        onJumpUntagged();
      } else if (e.key === "e" || e.key === "E") {
        e.preventDefault();
        handleExport("csv");
      } else if (config.mode === "binary") {
        if (e.key === "y" || e.key === "Y") {
          e.preventDefault();
          onToggleBinary(id, "yes");
        } else if (e.key === "n" || e.key === "N") {
          e.preventDefault();
          onToggleBinary(id, "no");
        }
      } else if (config.mode === "multiclass") {
        const num = parseInt(e.key);
        if (num >= 1 && num <= 9) {
          const cats = config.categories ?? [];
          if (num <= cats.length) {
            e.preventDefault();
            onToggleCategory(id, cats[num - 1]!.id);
          }
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [
    config,
    id,
    showShortcuts,
    onNavigate,
    onGoTo,
    onJumpUntagged,
    onToggleBinary,
    onToggleCategory,
    handleExport,
  ]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-muted-foreground px-5 pt-3">
        <a href="/" className="hover:text-foreground transition-colors">
          לוח בקרה
        </a>
        <ChevronLeft className="h-3 w-3" />
        <button
          type="button"
          onClick={onBack}
          className="hover:text-foreground transition-colors cursor-pointer"
        >
          הגדרות תיוג
        </button>
        <ChevronLeft className="h-3 w-3" />
        <span className="text-foreground font-medium">תיוג</span>
      </div>

      {/* Progress bar — full width with count */}
      <div className="flex items-center gap-2 px-5 py-1.5">
        <div className="h-1 flex-1 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{
              width: `${pct}%`,
              background: "linear-gradient(90deg, #c8a882, #a68b6b, #d4b896)",
            }}
          />
        </div>
        <span className="text-xs text-muted-foreground tabular-nums shrink-0">
          <span className="font-semibold text-primary">{taggedCount}</span>/{data.length}
        </span>
      </div>

      {/* Main Content */}
      <div className="flex flex-1 flex-col gap-3 p-5 overflow-hidden">
        {/* Text Card */}
        <Card className="flex flex-1 min-h-0 flex-col">
          <CardContent className="flex-1 overflow-y-auto px-6 py-5 text-base leading-relaxed text-foreground whitespace-pre-wrap" dir="auto">
            {item.text}
          </CardContent>
        </Card>

        {/* Annotation Card */}
        <Card className="flex flex-1 min-h-0 flex-col p-5">
          <CardTitle className="mb-3 text-center text-sm font-medium text-muted-foreground">
            {config.mode === "binary" && (config.question ?? "סיווג")}
            {config.mode === "multiclass" && "בחר קטגוריות"}
            {config.mode === "freetext" && (config.prompt ?? "הקלד טקסט")}
          </CardTitle>

          {config.mode === "binary" && (
            <div className="flex flex-1 min-h-0 flex-col gap-2">
              <Button
                variant={currentAnn === "yes" ? "default" : "outline"}
                onClick={() => onToggleBinary(id, "yes")}
                className={cn(
                  "flex-1 text-base font-medium rounded-xl gap-2 focus-visible:ring-0 focus-visible:border-transparent",
                  currentAnn === "yes" && "bg-emerald-600/15 hover:bg-emerald-600/20 border-emerald-600/40 text-emerald-700",
                )}
              >
                <Badge variant="ghost" size="sm" className="opacity-40 font-mono">Y</Badge>
                כן
              </Button>
              <Button
                variant={currentAnn === "no" ? "default" : "outline"}
                onClick={() => onToggleBinary(id, "no")}
                className={cn(
                  "flex-1 text-base font-medium rounded-xl gap-2 focus-visible:ring-0 focus-visible:border-transparent",
                  currentAnn === "no" && "bg-red-500/15 hover:bg-red-500/20 border-red-500/40 text-red-600",
                )}
              >
                <Badge variant="ghost" size="sm" className="opacity-40 font-mono">N</Badge>
                לא
              </Button>
            </div>
          )}

          {config.mode === "multiclass" && (
            <div
              className={cn(
                "flex flex-1 min-h-0 flex-col gap-1.5 overflow-y-auto",
                (config.categories?.length ?? 0) >= 7 && "gap-1",
              )}
            >
              {(config.categories ?? []).map((cat, i) => {
                const selected = Array.isArray(currentAnn) && currentAnn.includes(cat.id);
                return (
                  <Button
                    key={cat.id}
                    variant="outline"
                    onClick={() => onToggleCategory(id, cat.id)}
                    className={cn(
                      "flex-1 min-h-0 rounded-xl gap-2 focus-visible:ring-0 focus-visible:border-transparent",
                      (config.categories?.length ?? 0) >= 7 ? "text-sm" : "text-base",
                      "font-medium",
                      selected && "bg-primary/10 border-primary/40 text-primary",
                    )}
                  >
                    {i < 9 && (
                      <Badge variant="ghost" size="sm" className={cn("font-mono", selected ? "opacity-70" : "opacity-40")}>
                        {i + 1}
                      </Badge>
                    )}
                    {cat.label}
                  </Button>
                );
              })}
            </div>
          )}

          {config.mode === "freetext" && (
            <textarea
              ref={freetextRef}
              value={typeof currentAnn === "string" ? currentAnn : ""}
              onChange={(e) => onSetFreetext(id, e.target.value)}
              className="flex-1 min-h-0 resize-none rounded-xl border border-input/90 bg-background/75 px-4 py-3 text-sm leading-relaxed shadow-[inset_0_1px_0_rgba(255,255,255,0.72)] backdrop-blur-sm transition-[color,box-shadow,border-color] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
              placeholder={config.placeholder || ""}
              dir="auto"
            />
          )}
        </Card>

        {/* Navigation */}
        <div className="flex items-center justify-between">
          <Button
            variant="outline"
            onClick={() => onNavigate(-1)}
            disabled={currentIndex === 0}
            className="gap-2"
          >
            <ChevronRight className="size-4" />
            הקודם
          </Button>

          <div className="flex items-center gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon-sm" onClick={() => onGoTo(0)}>
                  <SkipBack className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>התחלה</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={onJumpUntagged}
                  disabled={taggedCount === data.length}
                >
                  <CircleMinus className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>קפיצה ללא מתויג</TooltipContent>
            </Tooltip>


            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon-sm" onClick={() => setShowShortcuts(true)}>
                  <Keyboard className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>קיצורי מקשים</TooltipContent>
            </Tooltip>
            <PopoverPrimitive.Root>
              <Tooltip>
                <TooltipTrigger asChild>
                  <PopoverPrimitive.Trigger asChild>
                    <Button variant="ghost" size="icon-sm">
                      <Download className="size-4" />
                    </Button>
                  </PopoverPrimitive.Trigger>
                </TooltipTrigger>
                <TooltipContent>ייצוא</TooltipContent>
              </Tooltip>
              <PopoverPrimitive.Portal>
                <PopoverPrimitive.Content
                  side="bottom"
                  sideOffset={8}
                  className="z-50 w-36 rounded-lg border bg-background p-1 shadow-lg animate-in fade-in-0 zoom-in-95"
                >
                  {(["csv", "json", "xlsx", "xls"] as const).map((fmt) => (
                    <PopoverPrimitive.Close key={fmt} asChild>
                      <button
                        type="button"
                        onClick={() => handleExport(fmt)}
                        className="flex w-full items-center rounded-md px-3 py-1.5 text-xs font-medium text-foreground cursor-pointer transition-colors hover:bg-accent"
                      >
                        {fmt.toUpperCase()}
                      </button>
                    </PopoverPrimitive.Close>
                  ))}
                </PopoverPrimitive.Content>
              </PopoverPrimitive.Portal>
            </PopoverPrimitive.Root>
          </div>

          <Button
            variant="outline"
            onClick={() => onNavigate(1)}
            disabled={currentIndex === data.length - 1}
            className="gap-2"
          >
            הבא
            <ChevronLeft className="size-4" />
          </Button>
        </div>
      </div>

      {/* Shortcuts Dialog */}
      <Dialog open={showShortcuts} onOpenChange={setShowShortcuts}>
        <DialogContent className="sm:max-w-sm" dir="rtl">
          <DialogHeader>
            <DialogTitle>קיצורי מקשים</DialogTitle>
          </DialogHeader>
          <div className="space-y-1.5">
            {config.mode === "binary" && (
              <>
                <ShortcutRow keys="Y" label="כן" />
                <ShortcutRow keys="N" label="לא" />
              </>
            )}
            {config.mode === "multiclass" &&
              (config.categories ?? []).slice(0, 9).map((cat, i) => (
                <ShortcutRow key={cat.id} keys={String(i + 1)} label={cat.label} />
              ))}
            <Separator className="my-2" />
            <ShortcutRow keys="← / →" label="הבא / הקודם" />
            <ShortcutRow keys="Home" label="התחלה" />
            <ShortcutRow keys="U" label="קפיצה ללא מתויג" />
            <ShortcutRow keys="E" label="ייצוא CSV" />
            <ShortcutRow keys="Ctrl+H" label="קיצורי מקשים" />
          </div>
        </DialogContent>
      </Dialog>

      {/* Export Confirm */}
      <Dialog open={!!exportConfirm} onOpenChange={(open) => { if (!open) setExportConfirm(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>ייצוא תיוגים</DialogTitle>
            <DialogDescription>
              נותרו{" "}
              <span className="font-mono font-medium text-foreground">
                {data.length - taggedCount}
              </span>{" "}
              טקסטים ללא תיוג. להמשיך בייצוא?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="grid grid-cols-2 gap-2">
            <Button
              variant="outline"
              onClick={() => setExportConfirm(null)}
              className="w-full justify-center"
            >
              ביטול
            </Button>
            <Button
              onClick={() => {
                if (exportConfirm) doExport(exportConfirm);
                setExportConfirm(null);
              }}
              className="w-full justify-center"
            >
              ייצוא
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confetti */}
      {showConfetti && <Confetti />}
    </div>
  );
}


function ShortcutRow({ keys, label }: { keys: string; label: string }) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <Badge variant="outline" size="sm" className="font-mono">
        {keys}
      </Badge>
    </div>
  );
}

function Confetti() {
  const colors = ["#3d2e22", "#5c4d40", "#8c7a6b", "#a69585", "#ddd6cc"];
  const shapes = ["rounded-full", "rounded-sm", "rounded-sm"];
  const pieces = Array.from({ length: 50 }, (_, i) => {
    const shape = shapes[i % shapes.length];
    const color = colors[i % colors.length];
    const left = Math.random() * 100;
    const delay = Math.random() * 0.5;
    const duration = 2 + Math.random() * 2;
    const size = 6 + Math.random() * 10;
    return (
      <div
        key={i}
        className={cn("absolute opacity-0", shape)}
        style={{
          backgroundColor: color,
          left: `${left}%`,
          width: `${size}px`,
          height: i % 3 === 2 ? `${size * 1.6}px` : `${size}px`,
          animation: `confetti-fall ${duration}s ${delay}s ease-out forwards`,
        }}
      />
    );
  });

  return (
    <div className="pointer-events-none fixed inset-0 z-[9999] overflow-hidden">
      <style>{`
        @keyframes confetti-fall {
          0% { opacity: 1; transform: translateY(-100px) rotate(0deg); }
          100% { opacity: 0; transform: translateY(100vh) rotate(720deg); }
        }
      `}</style>
      {pieces}
    </div>
  );
}
