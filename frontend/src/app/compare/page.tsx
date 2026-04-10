"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ChevronLeft,
  Loader2,
  XCircle,
  ArrowLeftRight,
  Trophy,
  Clock,
  Cpu,
  Database,
  Layers,
  Sparkles,
  Clipboard,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { motion } from "framer-motion";
import { FadeIn, StaggerContainer, StaggerItem, TiltCard } from "@/components/motion";
import { getJob } from "@/lib/api";
import { STATUS_LABELS } from "@/lib/constants";
import type { OptimizationStatusResponse, OptimizedPredictor } from "@/lib/types";
import { Skeleton } from "boneyard-js/react";
import { compareBones } from "@/components/compare-bones";
import { HelpTip } from "@/components/help-tip";

/* ── Formatters ── */

function fmt(v: number | undefined | null): string {
  if (v == null) return "—";
  const pct = Math.abs(v) > 1 ? v : v * 100;
  return `${pct.toFixed(1)}%`;
}

function fmtImprovement(v: number | undefined | null): string {
  if (v == null) return "—";
  const pct = Math.abs(v) > 1 ? v : v * 100;
  return pct >= 0 ? `+${pct.toFixed(1)}%` : `${pct.toFixed(1)}%`;
}

function fmtElapsed(s?: number | null): string {
  if (s == null) return "—";
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = Math.floor(s % 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  if (hrs > 0) return `${hrs}:${pad(mins)}:${pad(secs)}`;
  return `${mins}:${pad(secs)}`;
}

/* ── Score Card ── */

function ScoreCard({
  label,
  valueA,
  valueB,
  winner,
  delay,
}: {
  label: React.ReactNode;
  valueA: string;
  valueB: string;
  winner?: "a" | "b" | null;
  delay: number;
}) {
  return (
    <StaggerItem>
      <div className="rounded-xl border border-border/50 bg-gradient-to-b from-white/95 to-[#F8F4EF] p-4 shadow-[0_1px_3px_rgba(28,22,18,0.03),0_4px_16px_rgba(28,22,18,0.025)]">
        <p className="text-[11px] text-muted-foreground font-medium tracking-wide text-center mb-3">
          {label}
        </p>
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
          {/* A */}
          <div
            className={`text-center rounded-lg py-2 px-3 transition-colors ${winner === "a" ? "bg-emerald-50 border border-emerald-200/60" : "bg-muted/30"}`}
          >
            <span
              className={`text-base font-mono font-bold tabular-nums ${winner === "a" ? "text-emerald-700" : "text-foreground"}`}
            >
              {valueA}
            </span>
            {winner === "a" && (
              <Trophy className="size-3 text-emerald-500 inline-block ms-1.5 -mt-0.5" />
            )}
          </div>
          {/* VS */}
          <span className="text-[10px] text-muted-foreground/50 font-bold">VS</span>
          {/* B */}
          <div
            className={`text-center rounded-lg py-2 px-3 transition-colors ${winner === "b" ? "bg-emerald-50 border border-emerald-200/60" : "bg-muted/30"}`}
          >
            <span
              className={`text-base font-mono font-bold tabular-nums ${winner === "b" ? "text-emerald-700" : "text-foreground"}`}
            >
              {valueB}
            </span>
            {winner === "b" && (
              <Trophy className="size-3 text-emerald-500 inline-block ms-1.5 -mt-0.5" />
            )}
          </div>
        </div>
      </div>
    </StaggerItem>
  );
}

/* ── Config Row ── */

function ConfigRow({
  icon: Icon,
  label,
  a,
  b,
}: {
  icon: React.ElementType;
  label: string;
  a: string;
  b: string;
}) {
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 sm:gap-4 py-2.5">
      <span className="text-xs sm:text-sm font-mono text-end tabular-nums text-foreground truncate">
        {a}
      </span>
      <span className="flex items-center gap-1 sm:gap-1.5 text-[10px] sm:text-[11px] text-muted-foreground min-w-[60px] sm:min-w-[100px] justify-center">
        <Icon className="size-3 opacity-50 shrink-0" />
        <span className="truncate">{label}</span>
      </span>
      <span className="text-xs sm:text-sm font-mono tabular-nums text-foreground truncate">
        {b}
      </span>
    </div>
  );
}

/* ── Copy Button ── */

function CopyBtn({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(() => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [text]);
  return (
    <button
      type="button"
      onClick={copy}
      className="absolute top-2 end-2 p-1.5 rounded cursor-pointer opacity-0 group-hover/ins:opacity-100 transition-opacity duration-200 hover:bg-black/5"
      aria-label="העתק"
    >
      {copied ? (
        <Check className="size-3.5 text-emerald-600" />
      ) : (
        <Clipboard className="size-3.5 text-muted-foreground" />
      )}
    </button>
  );
}

/* ── Prompt Block ── */

function PromptBlock({
  prompt,
  label,
}: {
  prompt: OptimizedPredictor | null | undefined;
  label: string;
}) {
  if (!prompt) {
    return (
      <div className="flex items-center justify-center h-32 rounded-xl border border-dashed border-border/60 bg-muted/20">
        <p className="text-sm text-muted-foreground italic">אין פרומפט זמין</p>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <h4 className="text-sm font-semibold truncate" dir="auto">
        {label}
      </h4>

      {/* Instructions */}
      <div className="space-y-1.5">
        <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
          <HelpTip text="ההנחיות שהאופטימייזר יצר למודל — מתארות את המשימה ואיך לבצע אותה">
            הנחיות (Instructions)
          </HelpTip>
        </p>
        <div className="relative group/ins rounded-lg border border-border/40 bg-muted/20 p-3 pr-9">
          <pre
            className="text-xs font-mono whitespace-pre-wrap break-words leading-relaxed text-foreground/80"
            dir="ltr"
          >
            {prompt.instructions}
          </pre>
          <CopyBtn text={prompt.instructions} />
        </div>
      </div>

      {/* Demos */}
      {prompt.demos.length > 0 && (
        <div className="space-y-2">
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
            {prompt.demos.length} דוגמאות (Demos)
          </p>
          <div className="space-y-2">
            {prompt.demos.map((demo, i) => (
              <div
                key={i}
                className="rounded-lg border border-border/40 bg-gradient-to-br from-muted/20 to-transparent p-3 text-xs space-y-1.5 hover:border-border/60 transition-colors"
              >
                {Object.entries(demo.inputs).map(([k, v]) => (
                  <div key={k} className="flex gap-1.5">
                    <span className="text-muted-foreground shrink-0 font-medium">{k}:</span>
                    <span className="font-mono break-all" dir="ltr">
                      {String(v)}
                    </span>
                  </div>
                ))}
                <Separator className="my-1.5" />
                {Object.entries(demo.outputs).map(([k, v]) => (
                  <div key={k} className="flex gap-1.5">
                    <span className="text-primary shrink-0 font-semibold">{k}:</span>
                    <span className="font-mono break-all" dir="ltr">
                      {String(v)}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Page ── */

export default function ComparePage() {
  const searchParams = useSearchParams();
  const optimizationIds = (searchParams.get("jobs") ?? "").split(",").filter(Boolean);

  const [jobs, setJobs] = useState<(OptimizationStatusResponse | null)[]>([null, null]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const [idA, idB] = optimizationIds;
    if (!idA || !idB) {
      setError("בחר שתי אופטימיזציות מלוח הבקרה כדי להשוות ביניהן");
      setLoading(false);
      return;
    }
    Promise.all([getJob(idA), getJob(idB)])
      .then(([a, b]) => {
        setJobs([a, b]);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "שגיאה בטעינת האופטימיזציות"))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <Skeleton
        name="compare"
        loading
        initialBones={compareBones}
        color="var(--muted)"
        animate="shimmer"
      >
        <div className="min-h-[60vh]" />
      </Skeleton>
    );
  }

  if (error || !jobs[0] || !jobs[1]) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <XCircle className="size-12 text-destructive" />
        <p className="text-lg text-muted-foreground">{error ?? "לא ניתן לטעון את האופטימיזציות"}</p>
        <Button variant="outline" asChild>
          <Link href="/">חזרה</Link>
        </Button>
      </div>
    );
  }

  const [a, b] = jobs as [OptimizationStatusResponse, OptimizationStatusResponse];

  // Extract metrics
  const aBaseline =
    a.result?.baseline_test_metric ?? a.grid_result?.best_pair?.baseline_test_metric;
  const bBaseline =
    b.result?.baseline_test_metric ?? b.grid_result?.best_pair?.baseline_test_metric;
  const aOptimized =
    a.result?.optimized_test_metric ?? a.grid_result?.best_pair?.optimized_test_metric;
  const bOptimized =
    b.result?.optimized_test_metric ?? b.grid_result?.best_pair?.optimized_test_metric;
  const aImprovement =
    a.result?.metric_improvement ??
    (a.grid_result?.best_pair
      ? (a.grid_result.best_pair.optimized_test_metric ?? 0) -
        (a.grid_result.best_pair.baseline_test_metric ?? 0)
      : undefined);
  const bImprovement =
    b.result?.metric_improvement ??
    (b.grid_result?.best_pair
      ? (b.grid_result.best_pair.optimized_test_metric ?? 0) -
        (b.grid_result.best_pair.baseline_test_metric ?? 0)
      : undefined);

  const betterOptimized =
    aOptimized != null && bOptimized != null
      ? aOptimized > bOptimized
        ? "a"
        : aOptimized < bOptimized
          ? "b"
          : null
      : null;
  const betterImprovement =
    aImprovement != null && bImprovement != null
      ? aImprovement > bImprovement
        ? "a"
        : aImprovement < bImprovement
          ? "b"
          : null
      : null;

  // Prompts
  const aPrompt =
    a.result?.program_artifact?.optimized_prompt ??
    a.grid_result?.best_pair?.program_artifact?.optimized_prompt;
  const bPrompt =
    b.result?.program_artifact?.optimized_prompt ??
    b.grid_result?.best_pair?.program_artifact?.optimized_prompt;

  const nameA = a.name || a.optimization_id.slice(0, 8);
  const nameB = b.name || b.optimization_id.slice(0, 8);

  return (
    <motion.div
      className="space-y-8 pb-16"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.2, 0.8, 0.2, 1] }}
    >
      {/* Breadcrumb */}
      <FadeIn>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Link href="/" className="hover:text-foreground transition-colors">
            לוח בקרה
          </Link>
          <ChevronLeft className="h-3 w-3" />
          <span className="text-foreground font-medium">השוואת אופטימיזציות</span>
        </div>
      </FadeIn>

      {/* Header with job cards */}
      <FadeIn delay={0.05}>
        <div className="rounded-2xl border border-border/40 bg-gradient-to-b from-white/95 to-[#F8F4EF] p-6 shadow-[0_1px_3px_rgba(28,22,18,0.03),0_4px_16px_rgba(28,22,18,0.025)]">
          <div className="flex items-center gap-3 mb-5">
            <div className="size-9 rounded-lg bg-gradient-to-br from-[#3D2E22] to-[#5A4232] flex items-center justify-center shadow-sm">
              <ArrowLeftRight className="size-4 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold" data-tutorial="compare-button">
                <HelpTip text="השוואה מפורטת בין שתי הרצות — ציונים, הגדרות, ופרומפטים">
                  השוואת אופטימיזציות
                </HelpTip>
              </h1>
              <p className="text-[11px] text-muted-foreground">השוואה מפורטת בין שתי הרצות</p>
            </div>
          </div>

          {/* Optimization identity cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[
              { job: a, label: "A", name: nameA },
              { job: b, label: "B", name: nameB },
            ].map(({ job, label, name }) => (
              <Link
                key={job.optimization_id}
                href={`/optimizations/${job.optimization_id}`}
                className="group relative rounded-lg border border-border/50 bg-white/80 px-4 py-2.5 pe-5 hover:border-primary/30 transition-all duration-300 overflow-hidden flex items-center justify-between gap-3"
              >
                <div
                  className={`absolute inset-y-0 end-0 w-1 ${label === "A" ? "bg-[#3D2E22]" : "bg-[#7C6350]"}`}
                />
                <p
                  className="text-sm font-semibold truncate group-hover:text-primary transition-colors"
                  dir="auto"
                >
                  {name}
                </p>
                <Badge variant="outline" className="text-[10px] shrink-0">
                  {STATUS_LABELS[job.status] ?? job.status}
                </Badge>
              </Link>
            ))}
          </div>
        </div>
      </FadeIn>

      {/* Scores — card grid */}
      <FadeIn delay={0.15}>
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
            <Trophy className="size-3.5" />
            <HelpTip text="ציוני המדידה לפני ואחרי האופטימיזציה לכל הרצה">ציונים</HelpTip>
          </h2>
          <StaggerContainer
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3"
            staggerDelay={0.06}
          >
            <ScoreCard
              label={<HelpTip text="ציון המדידה לפני אופטימיזציה">ציון התחלתי</HelpTip>}
              valueA={fmt(aBaseline)}
              valueB={fmt(bBaseline)}
              delay={0}
            />
            <ScoreCard
              label={<HelpTip text="ציון המדידה אחרי אופטימיזציה">ציון מאופטם</HelpTip>}
              valueA={fmt(aOptimized)}
              valueB={fmt(bOptimized)}
              winner={betterOptimized}
              delay={0.05}
            />
            <ScoreCard
              label={<HelpTip text="ההפרש בין הציון המשופר לציון ההתחלתי">שיפור</HelpTip>}
              valueA={fmtImprovement(aImprovement)}
              valueB={fmtImprovement(bImprovement)}
              winner={betterImprovement}
              delay={0.1}
            />
            <ScoreCard
              label="זמן ריצה"
              valueA={fmtElapsed(a.result?.runtime_seconds)}
              valueB={fmtElapsed(b.result?.runtime_seconds)}
              delay={0.15}
            />
          </StaggerContainer>
        </div>
      </FadeIn>

      {/* Config comparison */}
      <FadeIn delay={0.25}>
        <Card className="overflow-hidden">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2 text-muted-foreground font-semibold">
              <Cpu className="size-3.5" />
              <HelpTip text="השוואת ההגדרות שנבחרו לכל הרצה — מודל, אופטימייזר, ונתונים">
                הגדרות
              </HelpTip>
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {/* Column headers */}
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 sm:gap-4 pb-2 mb-1 border-b border-border/40">
              <span className="text-[10px] font-bold text-end uppercase tracking-wider text-muted-foreground truncate">
                {nameA}
              </span>
              <span className="min-w-[60px] sm:min-w-[100px]" />
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground truncate">
                {nameB}
              </span>
            </div>
            <div className="divide-y divide-border/30">
              <ConfigRow
                icon={Layers}
                label="מודול"
                a={a.module_name ?? "—"}
                b={b.module_name ?? "—"}
              />
              <ConfigRow
                icon={Cpu}
                label="אופטימייזר"
                a={a.optimizer_name ?? "—"}
                b={b.optimizer_name ?? "—"}
              />
              <ConfigRow
                icon={Sparkles}
                label="מודל"
                a={a.model_name ?? "—"}
                b={b.model_name ?? "—"}
              />
              <ConfigRow
                icon={Database}
                label="שורות בדאטאסט"
                a={String(a.dataset_rows ?? "—")}
                b={String(b.dataset_rows ?? "—")}
              />
              <ConfigRow
                icon={Clock}
                label="זמן ריצה"
                a={fmtElapsed(a.result?.runtime_seconds)}
                b={fmtElapsed(b.result?.runtime_seconds)}
              />
            </div>
          </CardContent>
        </Card>
      </FadeIn>

      {/* Prompts comparison — side by side */}
      <FadeIn delay={0.35}>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2 text-muted-foreground font-semibold">
              <Sparkles className="size-3.5" />
              <HelpTip text="הפרומפט שנבנה אוטומטית ע״י האופטימייזר — כולל הנחיות ודוגמאות שנבחרו">
                פרומפט מאופטם
              </HelpTip>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              <PromptBlock prompt={aPrompt} label={nameA} />
              <PromptBlock prompt={bPrompt} label={nameB} />
            </div>
          </CardContent>
        </Card>
      </FadeIn>
    </motion.div>
  );
}
