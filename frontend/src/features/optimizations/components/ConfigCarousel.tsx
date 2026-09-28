"use client";

import { useCallback, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion, type Variants } from "framer-motion";
import {
  ArrowsOut,
  CaretLeft,
  CaretRight,
  Key,
  Plug,
  TextT,
  Thermometer,
  ShieldCheck,
} from "@/shared/ui/icons";
import { Button } from "@/shared/ui/primitives/button";
import { Dialog, DialogContent } from "@/shared/ui/primitives/dialog";
import { DialogTitleRow } from "@/shared/ui/dialog-title-row";
import { TooltipButton } from "@/shared/ui/tooltip-button";
import { useUserPrefs } from "@/features/settings";
import { HelpTip } from "@/shared/ui/help-tip";
import { msg } from "@/shared/lib/messages";
import { perLocale } from "@/shared/lib/per-locale";
import { tip } from "@/shared/lib/tooltips";
import { TERMS } from "@/shared/lib/terms";
import { cn } from "@/shared/lib/utils";
import { getActiveDir } from "@/shared/lib/runtime-locale";
import { arrowPageStep } from "@/shared/lib/arrow-paging";
import { ProviderLogo } from "@/shared/ui/provider-logo";
import { ReasoningPill } from "./ui-primitives";

export type ConfigSlide = {
  id: string;
  label: string;
  icon: ReactNode;
  tip?: string;
};

const SLIDE_VARIANTS: Variants = {
  enter: (direction: 1 | -1) => ({ opacity: 0, x: direction * 36 }),
  center: { opacity: 1, x: 0 },
  exit: (direction: 1 | -1) => ({ opacity: 0, x: direction * -28 }),
};

const SLIDE_TRANSITION = {
  duration: 0.24,
  ease: [0.2, 0.8, 0.2, 1] as const,
};

// Card values are single-line facts; notes are prose. Anything past these
// limits is clipped with an ellipsis and gets a maximize button that opens
// the full text in a dialog.
const VALUE_CHAR_LIMIT = 40;
const NOTE_CHAR_LIMIT = 280;

function clipText(text: string, limit: number): string {
  return text.length > limit ? `${text.slice(0, limit).trimEnd()}…` : text;
}

/** Maximize button that opens the untruncated text in a dialog. */
function ExpandTextButton({
  label,
  text,
  mono = false,
}: {
  label: ReactNode;
  text: string;
  mono?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const expandLabel = msg("optimization.config.expand");
  return (
    <>
      <TooltipButton tooltip={expandLabel}>
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          onClick={() => setOpen(true)}
          aria-label={expandLabel}
          className="text-muted-foreground hover:text-foreground"
        >
          <ArrowsOut className="size-3.5" aria-hidden="true" />
        </Button>
      </TooltipButton>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="w-[min(40rem,92vw)] max-w-[min(40rem,92vw)] sm:max-w-[min(40rem,92vw)]">
          <DialogTitleRow title={label} />
          <div className="max-h-[70vh] overflow-y-auto rounded-xl border border-border/45 bg-[#F8F4EE] p-4">
            <p
              className={cn("whitespace-pre-wrap break-words text-sm", mono && "font-mono")}
              dir={mono ? "ltr" : "auto"}
            >
              {text}
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

/** Numbered feature card for a slide's leading facts. */
export function SlideHeroCard({
  index,
  label,
  value,
  icon,
}: {
  index: number;
  label: ReactNode;
  value: string;
  icon: ReactNode;
}) {
  return (
    <article className="flex min-h-40 min-w-0 flex-col justify-between gap-6 rounded-2xl border border-border/60 bg-[#F8F4EE] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.72)] sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-[#3D2E22] text-[#FAF8F5] [&_svg]:size-5">
          {icon}
        </span>
        <span className="font-mono text-[0.625rem] tabular-nums text-[#8C7A6B]/70" dir="ltr">
          0{index + 1}
        </span>
      </div>
      <div className="min-w-0">
        <div className="text-[0.6875rem] font-semibold uppercase tracking-[0.1em] text-[#8C7A6B]">
          {label}
        </div>
        <div className="mt-1 flex min-w-0 items-center gap-2">
          <div
            className="min-w-0 truncate font-mono text-xl font-semibold tracking-tight text-foreground sm:text-2xl"
            dir="ltr"
            title={value}
          >
            {clipText(value, VALUE_CHAR_LIMIT)}
          </div>
          {value.length > VALUE_CHAR_LIMIT && <ExpandTextButton label={label} text={value} mono />}
        </div>
      </div>
    </article>
  );
}

/** Compact card for a slide's secondary facts. */
export function SlideMiniCard({
  label,
  value,
  icon,
}: {
  label: ReactNode;
  value: string;
  icon: ReactNode;
}) {
  return (
    <article className="flex min-h-28 min-w-0 flex-col justify-between gap-4 rounded-xl border border-border/45 bg-background/65 p-4">
      <span className="grid size-9 place-items-center rounded-xl bg-[#EDE7DD] text-[#8C7A6B] [&_svg]:size-4">
        {icon}
      </span>
      <div className="min-w-0">
        <div className="truncate text-[0.6875rem] font-medium text-muted-foreground">{label}</div>
        <div className="mt-0.5 flex min-w-0 items-center gap-2">
          <div
            className="min-w-0 truncate font-mono text-base font-semibold text-foreground"
            dir="ltr"
            title={value}
          >
            {clipText(value, VALUE_CHAR_LIMIT)}
          </div>
          {value.length > VALUE_CHAR_LIMIT && <ExpandTextButton label={label} text={value} mono />}
        </div>
      </div>
    </article>
  );
}

/** Free-text block for prose the wizard captured, such as the run description. */
export function SlideNote({ label, text }: { label: ReactNode; text: string }) {
  const long = text.length > NOTE_CHAR_LIMIT;
  return (
    <div className="rounded-xl border border-border/45 bg-background/65 p-4">
      <div className="mb-1 flex items-center justify-between gap-2">
        <div className="min-w-0 text-[0.6875rem] font-semibold uppercase tracking-widest text-muted-foreground">
          {label}
        </div>
        {long && <ExpandTextButton label={label} text={text} />}
      </div>
      <p className="whitespace-pre-wrap text-sm" dir="auto">
        {clipText(text, NOTE_CHAR_LIMIT)}
      </p>
    </div>
  );
}

/** Proportional train / val / test bar for a slide's split summary. */
export function SplitBar({
  fractions,
}: {
  fractions: { train: number; val: number; test: number };
}) {
  return (
    <div className="flex min-h-28 flex-1 overflow-hidden rounded-2xl border border-border/50 bg-muted/30 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
      <div
        className="flex min-w-0 flex-col items-center justify-center gap-3 bg-[#3D2E22] p-2 text-[#FAF8F5] transition-[width] sm:items-stretch sm:justify-between sm:p-5"
        style={{ width: `${fractions.train * 100}%` }}
      >
        <span className="hidden truncate text-[0.625rem] font-semibold uppercase tracking-[0.08em] opacity-70 sm:block">
          {msg("auto.features.optimizations.components.configtab.10")}
        </span>
        <span className="font-mono text-sm font-semibold tabular-nums sm:text-2xl" dir="ltr">
          {Math.round(fractions.train * 100)}%
        </span>
      </div>
      <div
        className="flex min-w-0 flex-col items-center justify-center gap-3 bg-[#C8A882] p-2 text-[#3D2E22] transition-[width] sm:items-stretch sm:justify-between sm:p-5"
        style={{ width: `${fractions.val * 100}%` }}
      >
        <span className="hidden truncate text-[0.625rem] font-semibold uppercase tracking-[0.08em] opacity-70 sm:block">
          {msg("auto.features.optimizations.components.configtab.11")}
        </span>
        <span className="font-mono text-sm font-semibold tabular-nums sm:text-2xl" dir="ltr">
          {Math.round(fractions.val * 100)}%
        </span>
      </div>
      <div
        className="flex min-w-0 flex-col items-center justify-center gap-3 bg-[#8C7A6B] p-2 text-[#FAF8F5] transition-[width] sm:items-stretch sm:justify-between sm:p-5"
        style={{ width: `${fractions.test * 100}%` }}
      >
        <span className="hidden truncate text-[0.625rem] font-semibold uppercase tracking-[0.08em] opacity-70 sm:block">
          {msg("auto.features.optimizations.components.configtab.12")}
        </span>
        <span className="font-mono text-sm font-semibold tabular-nums sm:text-2xl" dir="ltr">
          {Math.round(fractions.test * 100)}%
        </span>
      </div>
    </div>
  );
}

/**
 * Shell for the config tab: header with a step rail, an animated slide body
 * with swipe and keyboard navigation, and a footer with previous/next controls.
 */
export function ConfigCarousel({
  slides,
  renderSlide,
}: {
  slides: ConfigSlide[];
  renderSlide: (index: number) => ReactNode;
}) {
  const { prefs } = useUserPrefs();
  const prefersReducedMotion = useReducedMotion() || prefs.liteMode;
  const isRtl = getActiveDir() === "rtl";
  const [activeSlide, setActiveSlide] = useState(0);
  const [slideDirection, setSlideDirection] = useState<1 | -1>(isRtl ? -1 : 1);
  const touchStart = useRef<{ x: number; y: number } | null>(null);

  const goToSlide = useCallback(
    (next: number) => {
      const clamped = Math.max(0, Math.min(slides.length - 1, next));
      if (clamped === activeSlide) return;
      const forward = clamped > activeSlide;
      setSlideDirection(forward === isRtl ? -1 : 1);
      setActiveSlide(clamped);
    },
    [activeSlide, isRtl, slides.length],
  );

  const previousSlide = slides[activeSlide - 1];
  const currentSlide = slides[activeSlide] ?? slides[0]!;
  const nextSlide = slides[activeSlide + 1];
  const PreviousIcon = isRtl ? CaretRight : CaretLeft;
  const NextIcon = isRtl ? CaretLeft : CaretRight;

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.3 }}
      className="w-full overflow-hidden rounded-2xl border border-border bg-card/80 shadow-lg backdrop-blur-xl"
      data-tutorial="config-summary"
      role="region"
      aria-label={currentSlide.label}
      tabIndex={0}
      onKeyDown={(event) => {
        // Arrows page from anywhere in the shell — the step rail and footer
        // buttons keep focus after a click — not only from the region itself.
        const step = arrowPageStep(event, isRtl);
        if (step === 0) return;
        event.preventDefault();
        goToSlide(activeSlide + step);
      }}
    >
      <div className="flex items-center justify-between gap-5 border-b border-border/60 bg-secondary/35 px-5 py-4 sm:px-6 sm:py-5 lg:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-[#EDE7DD] text-[#3D2E22] shadow-[inset_0_1px_0_rgba(255,255,255,0.65)]">
            {currentSlide.icon}
          </span>
          <div className="min-w-0">
            <span
              className="font-mono text-[0.625rem] tabular-nums text-muted-foreground"
              dir="ltr"
            >
              {activeSlide + 1} / {slides.length}
            </span>
            <h3 className="truncate text-lg font-bold tracking-tight text-foreground sm:text-xl">
              {currentSlide.tip ? (
                <HelpTip text={currentSlide.tip}>{currentSlide.label}</HelpTip>
              ) : (
                currentSlide.label
              )}
            </h3>
          </div>
        </div>
        <div
          className="hidden min-w-0 flex-1 items-center justify-end gap-2 sm:flex"
          aria-label={currentSlide.label}
        >
          {slides.map((slide, index) => (
            <button
              key={slide.id}
              type="button"
              onClick={() => goToSlide(index)}
              aria-label={slide.label}
              aria-current={activeSlide === index ? "step" : undefined}
              className={cn(
                "flex min-w-0 cursor-pointer items-center gap-2 rounded-xl border px-2.5 py-2 text-start transition-[background-color,border-color,color,transform] duration-150",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882] focus-visible:ring-offset-2 active:scale-[0.98]",
                activeSlide === index
                  ? "border-[#C8A882]/70 bg-background text-foreground shadow-sm"
                  : "border-transparent text-muted-foreground hover:border-border/60 hover:bg-background/55 hover:text-foreground",
              )}
            >
              <span
                className={cn(
                  "grid size-8 shrink-0 place-items-center rounded-lg transition-colors [&_svg]:size-4",
                  activeSlide === index
                    ? "bg-[#3D2E22] text-[#FAF8F5]"
                    : "bg-[#EDE7DD] text-[#8C7A6B]",
                )}
              >
                {slide.icon}
              </span>
              <span className="hidden truncate text-xs font-semibold lg:block">{slide.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div
        className="relative overflow-hidden p-4 sm:p-6 lg:p-8"
        onTouchStart={(event) => {
          const touch = event.touches[0];
          touchStart.current = touch ? { x: touch.clientX, y: touch.clientY } : null;
        }}
        onTouchEnd={(event) => {
          const start = touchStart.current;
          const touch = event.changedTouches[0];
          touchStart.current = null;
          if (!start || !touch) return;
          const deltaX = touch.clientX - start.x;
          const deltaY = touch.clientY - start.y;
          if (Math.abs(deltaX) < 52 || Math.abs(deltaX) < Math.abs(deltaY) * 1.2) return;
          const forward = isRtl ? deltaX > 0 : deltaX < 0;
          goToSlide(activeSlide + (forward ? 1 : -1));
        }}
      >
        <AnimatePresence mode="wait" custom={slideDirection} initial={false}>
          <motion.div
            key={activeSlide}
            custom={slideDirection}
            variants={SLIDE_VARIANTS}
            initial="enter"
            animate="center"
            exit="exit"
            transition={prefersReducedMotion ? { duration: 0 } : SLIDE_TRANSITION}
            className="min-h-[24rem] w-full"
          >
            {renderSlide(activeSlide)}
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-border/60 bg-secondary/25 px-4 py-3 sm:px-6">
        <button
          type="button"
          onClick={() => goToSlide(activeSlide - 1)}
          disabled={!previousSlide}
          aria-label={msg("auto.features.agent.panel.components.toolscarousel.literal.14")}
          className="inline-flex min-h-[44px] min-w-[44px] cursor-pointer items-center gap-2 rounded-xl px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-background/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882] disabled:cursor-not-allowed disabled:opacity-30"
        >
          <PreviousIcon className="size-4" aria-hidden="true" />
          <span className="hidden sm:inline">{previousSlide?.label}</span>
        </button>

        <div className="flex items-center justify-center gap-1 sm:hidden">
          {slides.map((slide, index) => (
            <button
              key={slide.id}
              type="button"
              onClick={() => goToSlide(index)}
              aria-label={slide.label}
              aria-current={activeSlide === index ? "step" : undefined}
              className="flex size-[44px] cursor-pointer items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882]"
            >
              <span
                className={cn(
                  "h-1.5 rounded-full transition-[width,background-color] duration-200",
                  activeSlide === index ? "w-5 bg-[#3D2E22]" : "w-1.5 bg-[#3D2E22]/20",
                )}
              />
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => goToSlide(activeSlide + 1)}
          disabled={!nextSlide}
          aria-label={msg("auto.features.agent.panel.components.toolscarousel.literal.15")}
          className="inline-flex min-h-[44px] min-w-[44px] cursor-pointer items-center gap-2 rounded-xl px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-background/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C8A882] disabled:cursor-not-allowed disabled:opacity-30"
        >
          <span className="hidden sm:inline">{nextSlide?.label}</span>
          <NextIcon className="size-4" aria-hidden="true" />
        </button>
      </div>
    </motion.section>
  );
}

// Tooltip copy keyed by the two named model-role labels. Grid cards use
// indexed short labels (no match here) since their columns are already tipped.
const MODEL_CARD_TIPS: Record<string, string> = perLocale(() => ({
  [msg("model.generation.label")]: tip("model.generation"),
  [TERMS.reflectionModel]: tip("model.reflection"),
}));

type ModelParameterKey = "temperature" | "max_tokens";

function resolveModelParameter(
  cfg: Record<string, unknown>,
  key: ModelParameterKey,
): number | null {
  const rawExtra = cfg.extra;
  const extra =
    rawExtra && typeof rawExtra === "object" && !Array.isArray(rawExtra)
      ? (rawExtra as Record<string, unknown>)
      : undefined;
  const rawValue = cfg[key] ?? extra?.[key];
  const value =
    typeof rawValue === "number"
      ? rawValue
      : typeof rawValue === "string" && rawValue.trim()
        ? Number(rawValue)
        : Number.NaN;

  return Number.isFinite(value) ? value : null;
}

/** Resolve a routed model id to the provider mark used by the config card. */
function modelProviderSlug(id: string): string {
  return id.split("/")[0] ?? id;
}

/** Graphical model-config card for the Models carousel slide. */
export function ModelCard({
  label,
  labelTip,
  cfg,
}: {
  label: string;
  labelTip?: string;
  cfg: Record<string, unknown>;
}) {
  const cardTip = labelTip ?? MODEL_CARD_TIPS[label];
  const name = String(cfg.name || "—");
  const shortName = name.includes("/") ? name.split("/").pop()! : name;
  const temp = resolveModelParameter(cfg, "temperature");
  const maxTok = resolveModelParameter(cfg, "max_tokens");
  const extra = (cfg.extra ?? {}) as Record<string, unknown>;
  const reasoning = extra.reasoning_effort as string | undefined;
  const temperatureLabel = msg("auto.features.submit.components.modelconfigmodal.5");
  const maxTokensLabel = msg("auto.features.submit.components.modelconfigmodal.7");
  // Credential and endpoint facts sit on the config itself, not under `extra`:
  // they say whose key the calls ran on and where they went.
  const tokenSource =
    cfg.token_source === "byok" || cfg.token_source === "managed" ? cfg.token_source : null;
  const byokProvider =
    typeof cfg.byok_provider === "string" && cfg.byok_provider ? cfg.byok_provider : null;
  const baseUrl =
    typeof cfg.base_url === "string" && cfg.base_url.trim() ? cfg.base_url.trim() : null;
  const tokenSourceLabel = msg("optimization.config.token_source");
  const tokenSourceValue =
    tokenSource === "byok"
      ? byokProvider
        ? `${msg("model_source.byok")} · ${byokProvider}`
        : msg("model_source.byok")
      : tokenSource === "managed"
        ? msg("model_source.managed")
        : null;
  const endpointLabel = msg("optimization.config.model_endpoint");
  const hasChips = temp != null || maxTok != null || reasoning || tokenSourceValue || baseUrl;
  return (
    <article className="flex min-h-36 min-w-0 flex-col justify-between gap-5 rounded-2xl border border-border/60 bg-[#F8F4EE] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.72)]">
      <div className="flex min-w-0 items-start gap-3.5">
        <span className="grid size-12 shrink-0 place-items-center rounded-2xl border border-border/45 bg-background shadow-sm">
          <ProviderLogo slug={modelProviderSlug(name)} size={30} />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <span className="text-[0.625rem] font-semibold uppercase tracking-[0.1em] text-[#8C7A6B]">
            {cardTip ? <HelpTip text={cardTip}>{label}</HelpTip> : label}
          </span>
          <span
            className="truncate font-mono text-base font-semibold tracking-tight text-foreground sm:text-lg"
            dir="ltr"
            title={name}
          >
            {shortName}
          </span>
        </div>
      </div>
      {hasChips && (
        <div
          className="flex flex-wrap items-center gap-2 text-[0.6875rem] text-muted-foreground"
          dir="ltr"
        >
          {temp != null && (
            <span
              className="inline-flex items-center gap-1.5 rounded-full border border-border/45 bg-background/75 px-2.5 py-1"
              aria-label={`${temperatureLabel}: ${temp}`}
              title={temperatureLabel}
            >
              <Thermometer className="size-3" aria-hidden="true" />
              {temp}
            </span>
          )}
          {maxTok != null && (
            <span
              className="inline-flex items-center gap-1.5 rounded-full border border-border/45 bg-background/75 px-2.5 py-1"
              aria-label={`${maxTokensLabel}: ${maxTok}`}
              title={maxTokensLabel}
            >
              <TextT className="size-3" aria-hidden="true" />
              {maxTok}
            </span>
          )}
          {reasoning && <ReasoningPill value={reasoning} />}
          {tokenSourceValue && (
            <span
              className="inline-flex items-center gap-1.5 rounded-full border border-border/45 bg-background/75 px-2.5 py-1"
              aria-label={`${tokenSourceLabel}: ${tokenSourceValue}`}
              title={tokenSourceLabel}
              dir="auto"
            >
              {tokenSource === "byok" ? (
                <Key className="size-3" aria-hidden="true" />
              ) : (
                <ShieldCheck className="size-3" aria-hidden="true" />
              )}
              {tokenSourceValue}
            </span>
          )}
          {baseUrl && (
            <span
              className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-border/45 bg-background/75 px-2.5 py-1"
              aria-label={`${endpointLabel}: ${baseUrl}`}
              title={`${endpointLabel}: ${baseUrl}`}
            >
              <Plug className="size-3 shrink-0" aria-hidden="true" />
              <span className="truncate">{baseUrl}</span>
            </span>
          )}
        </div>
      )}
    </article>
  );
}
