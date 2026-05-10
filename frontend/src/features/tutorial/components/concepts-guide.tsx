"use client";

import * as React from "react";
import {
  X,
  Copy,
  Check,
  BookOpen,
  Sparkles,
  Cog,
  Boxes,
  ListTree,
  Lightbulb,
  Compass,
  ArrowLeft,
} from "lucide-react";
import { msg, formatMsg } from "@/shared/lib/messages";

interface ConceptsGuideProps {
  open: boolean;
  onClose: () => void;
}

interface SectionMeta {
  id: string;
  num: string;
  title: string;
  Icon: React.ComponentType<{ className?: string }>;
}

const SECTIONS: readonly SectionMeta[] = [
  {
    id: "background",
    num: "1",
    title: msg("auto.features.tutorial.components.concepts.guide.literal.1"),
    Icon: BookOpen,
  },
  {
    id: "gepa",
    num: "2",
    title: msg("auto.features.tutorial.components.concepts.guide.literal.2"),
    Icon: Sparkles,
  },
  {
    id: "parameters",
    num: "3",
    title: msg("auto.features.tutorial.components.concepts.guide.literal.3"),
    Icon: Cog,
  },
  {
    id: "task-definition",
    num: "4",
    title: msg("auto.features.tutorial.components.concepts.guide.literal.4"),
    Icon: Boxes,
  },
  {
    id: "workflow",
    num: "5",
    title: msg("auto.features.tutorial.components.concepts.guide.literal.5"),
    Icon: ListTree,
  },
  {
    id: "tips",
    num: "6",
    title: msg("auto.features.tutorial.components.concepts.guide.literal.6"),
    Icon: Lightbulb,
  },
  {
    id: "glossary",
    num: "7",
    title: msg("auto.features.tutorial.components.concepts.guide.literal.7"),
    Icon: Compass,
  },
] as const;

export function ConceptsGuide({ open, onClose }: ConceptsGuideProps) {
  const dialogRef = React.useRef<HTMLDivElement | null>(null);
  const scrollRef = React.useRef<HTMLDivElement | null>(null);
  const closeBtnRef = React.useRef<HTMLButtonElement | null>(null);
  const [activeId, setActiveId] = React.useState<string>(SECTIONS[0]!.id);
  const titleId = React.useId();

  React.useEffect(() => {
    if (!open) return;
    closeBtnRef.current?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const root = dialogRef.current;
      if (!root) return;
      const focusables = root.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusables.length === 0) return;
      const first = focusables[0]!;
      const last = focusables[focusables.length - 1]!;
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  React.useEffect(() => {
    if (!open) return;
    const root = scrollRef.current;
    if (!root) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .map((e) => ({ id: e.target.id.replace(/^guide-/, ""), top: e.boundingClientRect.top }));
        if (visible.length === 0) return;
        visible.sort((a, b) => a.top - b.top);
        setActiveId(visible[0]!.id);
      },
      { root, rootMargin: "-15% 0px -70% 0px", threshold: [0, 1] },
    );

    SECTIONS.forEach((s) => {
      const el = document.getElementById(`guide-${s.id}`);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [open]);

  const jumpTo = React.useCallback((id: string) => {
    const el = document.getElementById(`guide-${id}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center p-2 sm:p-6 animate-[fadeIn_180ms_ease-out]"
      dir="rtl"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <div
        className="absolute inset-0 bg-[#1C1612]/55 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        ref={dialogRef}
        className="relative w-full max-w-5xl h-[min(88vh,920px)] rounded-2xl border border-[#E5DDD4] bg-[#FAF8F5] shadow-[0_24px_64px_rgba(28,22,18,0.22)] overflow-hidden flex flex-col"
      >
        <GuideHeader
          titleId={titleId}
          onClose={onClose}
          closeBtnRef={closeBtnRef}
        />

        <div className="grid grid-cols-1 md:grid-cols-[240px_minmax(0,1fr)] flex-1 min-h-0">
          <GuideSidebar activeId={activeId} onJump={jumpTo} />
          <div
            ref={scrollRef}
            className="overflow-y-auto px-5 sm:px-8 py-6 scroll-smooth"
          >
            <SectionBackground />
            <SectionGepa />
            <SectionParameters />
            <SectionTaskDefinition />
            <SectionWorkflow />
            <SectionTips />
            <SectionGlossary />
          </div>
        </div>
      </div>
    </div>
  );
}

function GuideHeader({
  titleId,
  onClose,
  closeBtnRef,
}: {
  titleId: string;
  onClose: () => void;
  closeBtnRef: React.RefObject<HTMLButtonElement | null>;
}) {
  return (
    <header className="flex items-start gap-3 px-5 sm:px-7 py-4 border-b border-[#E5DDD4] bg-gradient-to-b from-[#FAF8F5] to-[#F5F1EC]">
      <div className="size-10 rounded-xl bg-[#3D2E22] flex items-center justify-center flex-shrink-0 shadow-[0_2px_6px_rgba(61,46,34,0.25)]">
        <Lightbulb className="size-5 text-[#FAF8F5]" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#7C6350]">
          {msg("auto.features.tutorial.components.concepts.guide.literal.8")}
        </p>
        <h2
          id={titleId}
          className="text-lg sm:text-xl font-bold text-[#3D2E22] leading-tight"
          style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
        >
          {msg("auto.features.tutorial.components.concepts.guide.literal.9")}
        </h2>
      </div>
      <button
        ref={closeBtnRef}
        type="button"
        onClick={onClose}
        className="p-1.5 rounded-lg hover:bg-[#E5DDD4]/60 text-[#8C7A6B] hover:text-[#3D2E22] transition-colors cursor-pointer flex-shrink-0"
        aria-label={msg("auto.features.tutorial.components.concepts.guide.literal.10")}
      >
        <X className="size-4" />
      </button>
    </header>
  );
}

function GuideSidebar({ activeId, onJump }: { activeId: string; onJump: (id: string) => void }) {
  return (
    <aside className="border-l border-[#E5DDD4] bg-[#F5F1EC]/40 px-3 py-4 hidden md:block overflow-y-auto">
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[#8C7A6B] px-2 mb-2">
        {msg("auto.features.tutorial.components.concepts.guide.literal.11")}
      </p>
      <ol className="space-y-0.5">
        {SECTIONS.map((s) => {
          const isActive = activeId === s.id;
          return (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => onJump(s.id)}
                className={[
                  "w-full text-right flex items-start gap-2 px-2 py-1.5 rounded-md text-[13px] transition-colors cursor-pointer",
                  isActive
                    ? "bg-[#EDE7DD] text-[#3D2E22] font-semibold"
                    : "text-[#5C4D40] hover:bg-[#EDE7DD]/60 hover:text-[#3D2E22]",
                ].join(" ")}
              >
                <span
                  className={[
                    "inline-flex items-center justify-center size-5 rounded-full text-[10px] font-bold flex-shrink-0 mt-0.5",
                    isActive ? "bg-[#3D2E22] text-[#FAF8F5]" : "bg-[#E5DDD4] text-[#7C6350]",
                  ].join(" ")}
                >
                  {s.num}
                </span>
                <span className="leading-snug">{s.title}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}

function GuideSection({
  id,
  num,
  title,
  kicker,
  children,
}: {
  id: string;
  num: string;
  title: string;
  kicker?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={`guide-${id}`} className="scroll-mt-4 mb-12 first:mt-0">
      <div className="flex items-baseline gap-2 mb-1">
        <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7C6350]">
          {formatMsg("auto.features.tutorial.components.concepts.guide.template.1", { p1: num })}
        </span>
        {kicker && <span className="text-[11px] text-[#A69585]">· {kicker}</span>}
      </div>
      <h3
        className="text-xl sm:text-2xl font-bold text-[#3D2E22] mb-3 leading-tight"
        style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
      >
        {title}
      </h3>
      <div className="prose-content text-[#3D2E22] text-[14.5px] leading-relaxed space-y-3">
        {children}
      </div>
    </section>
  );
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return (
    <h4
      className="text-[15px] font-bold text-[#3D2E22] mt-5 mb-1"
      style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
    >
      {children}
    </h4>
  );
}

function InlineCode({ children }: { children: React.ReactNode }) {
  return (
    <code
      className="px-1.5 py-0.5 rounded bg-[#F0EBE4] text-[#3D2E22] text-[0.88em] tabular-nums"
      style={{
        fontFamily:
          '"JetBrains Mono Variable", ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
      }}
    >
      {children}
    </code>
  );
}

function CodeBlock({ code, lang }: { code: string; lang?: string }) {
  const [copied, setCopied] = React.useState(false);
  const onCopy = () => {
    void navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    });
  };
  const copiedLabel = msg("auto.features.tutorial.components.concepts.guide.literal.12");
  const copyLabel = msg("auto.features.tutorial.components.concepts.guide.literal.13");
  return (
    <div className="relative my-3 rounded-lg overflow-hidden border border-[#2A211B] shadow-[0_1px_3px_rgba(28,22,18,0.08)]" dir="ltr">
      {lang && (
        <div className="absolute top-2 right-2 text-[10px] uppercase tracking-wider text-[#A69585] font-semibold pointer-events-none">
          {lang}
        </div>
      )}
      <button
        type="button"
        onClick={onCopy}
        className="absolute top-1.5 left-1.5 inline-flex items-center gap-1 px-1.5 py-1 rounded text-[10px] font-medium bg-[#2A211B] text-[#A69585] hover:text-[#F0EAE0] hover:bg-[#3D2E22] transition-colors cursor-pointer z-10"
        aria-label={copied ? copiedLabel : copyLabel}
      >
        {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
        {copied ? copiedLabel : copyLabel}
      </button>
      <pre
        className="px-4 py-3 pt-7 text-[12.5px] leading-relaxed text-[#F0EAE0] bg-[#1C1612] overflow-x-auto"
        style={{
          fontFamily:
            '"JetBrains Mono Variable", ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
          fontVariantLigatures: "none",
        }}
      >
        <code>{code}</code>
      </pre>
    </div>
  );
}

function ParamTable({
  rows,
}: {
  rows: Array<{ name: string; desc: React.ReactNode }>;
}) {
  return (
    <div className="my-3 overflow-hidden rounded-lg border border-[#E5DDD4] bg-white shadow-[0_1px_2px_rgba(28,22,18,0.05)]">
      <table className="w-full text-[13.5px]">
        <thead>
          <tr className="bg-[#F0EBE4] text-[#3D2E22]">
            <th
              className="text-right font-semibold px-3 py-2 w-[34%]"
              style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
            >
              {msg("auto.features.tutorial.components.concepts.guide.literal.14")}
            </th>
            <th
              className="text-right font-semibold px-3 py-2"
              style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
            >
              {msg("auto.features.tutorial.components.concepts.guide.literal.15")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.name} className={i % 2 === 0 ? "bg-white" : "bg-[#FAF8F5]"}>
              <td className="px-3 py-2 align-top border-t border-[#E5DDD4]" dir="ltr">
                <InlineCode>{r.name}</InlineCode>
              </td>
              <td className="px-3 py-2 align-top text-[#3D2E22] border-t border-[#E5DDD4]">
                {r.desc}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SectionBackground() {
  return (
    <GuideSection
      id="background"
      num="1"
      title={msg("auto.features.tutorial.components.concepts.guide.literal.1")}
      kicker={msg("auto.features.tutorial.components.concepts.guide.literal.16")}
    >
      <p>
        {msg("auto.features.tutorial.components.concepts.guide.literal.297")}
        <InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.271")}
        </InlineCode>
        {msg("auto.features.tutorial.components.concepts.guide.literal.298")}
        <InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.272")}
        </InlineCode>
        {msg("auto.features.tutorial.components.concepts.guide.literal.299")}
      </p>

      <SubHeading>{msg("auto.features.tutorial.components.concepts.guide.literal.17")}</SubHeading>
      <p>{msg("auto.features.tutorial.components.concepts.guide.literal.18")}</p>
      <p>{msg("auto.features.tutorial.components.concepts.guide.literal.19")}</p>

      <SubHeading>{msg("auto.features.tutorial.components.concepts.guide.literal.20")}</SubHeading>
      <p>{msg("auto.features.tutorial.components.concepts.guide.literal.21")}</p>
      <ul className="list-disc pr-5 space-y-1.5">
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.22")}
          </strong>{" "}
          {msg("auto.features.tutorial.components.concepts.guide.literal.23")}
        </li>
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.24")}
          </strong>{" "}
          {msg("auto.features.tutorial.components.concepts.guide.literal.25")}
        </li>
      </ul>

      <SubHeading>{msg("auto.features.tutorial.components.concepts.guide.literal.26")}</SubHeading>
      <p>{msg("auto.features.tutorial.components.concepts.guide.literal.27")}</p>
      <ul className="list-disc pr-5 space-y-1">
        <li>
          <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.28")}</strong>{" "}
          {msg("auto.features.tutorial.components.concepts.guide.literal.29")}
        </li>
        <li>
          <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.30")}</strong>{" "}
          {msg("auto.features.tutorial.components.concepts.guide.literal.31")}
        </li>
        <li>
          <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.32")}</strong>{" "}
          {msg("auto.features.tutorial.components.concepts.guide.literal.33")}
        </li>
        <li>
          <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.34")}</strong>{" "}
          {msg("auto.features.tutorial.components.concepts.guide.literal.35")}
        </li>
      </ul>
      <p>
        <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.36")}</strong>{" "}
        {msg("auto.features.tutorial.components.concepts.guide.literal.37")}
        <InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.273")}
        </InlineCode>
        {msg("auto.features.tutorial.components.concepts.guide.literal.38")}
      </p>

      <SubHeading>{msg("auto.features.tutorial.components.concepts.guide.literal.39")}</SubHeading>
      <p>
        <InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.271")}
        </InlineCode>
        {msg("auto.features.tutorial.components.concepts.guide.literal.40")}
        <em>{msg("auto.features.tutorial.components.concepts.guide.literal.41")}</em>
        {msg("auto.features.tutorial.components.concepts.guide.literal.42")}
      </p>
      <ol className="list-decimal pr-5 space-y-1">
        <li>
          <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.43")}</strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.44")}
        </li>
        <li>
          <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.45")}</strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.46")}
        </li>
        <li>
          <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.47")}</strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.48")}
        </li>
      </ol>
      <p>{msg("auto.features.tutorial.components.concepts.guide.literal.49")}</p>

      <SubHeading>{msg("auto.features.tutorial.components.concepts.guide.literal.50")}</SubHeading>
      <p>{msg("auto.features.tutorial.components.concepts.guide.literal.51")}</p>
      <ol className="list-decimal pr-5 space-y-1">
        <li>{msg("auto.features.tutorial.components.concepts.guide.literal.52")}</li>
        <li>{msg("auto.features.tutorial.components.concepts.guide.literal.53")}</li>
        <li>{msg("auto.features.tutorial.components.concepts.guide.literal.54")}</li>
        <li>{msg("auto.features.tutorial.components.concepts.guide.literal.55")}</li>
        <li>{msg("auto.features.tutorial.components.concepts.guide.literal.56")}</li>
      </ol>
    </GuideSection>
  );
}

function GepaLoopDiagram() {
  const stages = [
    { i: 1, name: "Initialization", he: msg("auto.features.tutorial.components.concepts.guide.literal.57") },
    { i: 2, name: "Evaluation", he: msg("auto.features.tutorial.components.concepts.guide.literal.58") },
    { i: 3, name: "Reflection", he: msg("auto.features.tutorial.components.concepts.guide.literal.59") },
    { i: 4, name: "Evolution", he: msg("auto.features.tutorial.components.concepts.guide.literal.60") },
    { i: 5, name: "Selection", he: msg("auto.features.tutorial.components.concepts.guide.literal.61") },
  ];
  return (
    <figure className="my-4 rounded-lg border border-[#E5DDD4] bg-white p-4 shadow-[0_1px_2px_rgba(28,22,18,0.05)]" dir="ltr">
      <svg viewBox="0 0 700 130" xmlns="http://www.w3.org/2000/svg" className="w-full h-auto">
        <defs>
          <marker id="gepa-arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto">
            <path d="M0,0 L9,4.5 L0,9 z" fill="#5C4D40" />
          </marker>
          <marker id="gepa-loop" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto">
            <path d="M0,0 L9,4.5 L0,9 z" fill="#9A6A10" />
          </marker>
        </defs>
        {stages.map((s, idx) => {
          const cx = 75 + idx * 138;
          return (
            <g key={s.i}>
              <rect
                x={cx - 60}
                y={28}
                width={120}
                height={48}
                rx={10}
                fill={idx === 2 ? "#3D2E22" : "#EDE7DD"}
                stroke="#3D2E22"
                strokeWidth={1.4}
              />
              <text
                x={cx}
                y={50}
                textAnchor="middle"
                fontFamily="Inter Variable, system-ui, sans-serif"
                fontSize={13}
                fontWeight={700}
                fill={idx === 2 ? "#FAF8F5" : "#3D2E22"}
              >
                {s.i}. {s.name}
              </text>
              <text
                x={cx}
                y={67}
                textAnchor="middle"
                fontFamily="Heebo Variable, system-ui, sans-serif"
                fontSize={11}
                fill={idx === 2 ? "#E5DDD4" : "#5C4D40"}
              >
                {s.he}
              </text>
              {idx < stages.length - 1 && (
                <line
                  x1={cx + 60}
                  y1={52}
                  x2={cx + 78}
                  y2={52}
                  stroke="#5C4D40"
                  strokeWidth={1.4}
                  markerEnd="url(#gepa-arrow)"
                />
              )}
            </g>
          );
        })}
        <path
          d="M 615 78 Q 615 110 350 110 Q 75 110 75 78"
          stroke="#9A6A10"
          strokeWidth={1.2}
          fill="none"
          strokeDasharray="4 4"
          markerEnd="url(#gepa-loop)"
        />
        <text
          x={350}
          y={125}
          textAnchor="middle"
          fontFamily="Heebo Variable, system-ui, sans-serif"
          fontSize={11}
          fill="#9A6A10"
          fontStyle="italic"
        >
          {msg("auto.features.tutorial.components.concepts.guide.literal.62")}
        </text>
      </svg>
    </figure>
  );
}

function SectionGepa() {
  return (
    <GuideSection
      id="gepa"
      num="2"
      title={msg("auto.features.tutorial.components.concepts.guide.literal.2")}
      kicker={msg("auto.features.tutorial.components.concepts.guide.literal.63")}
    >
      <SubHeading>{msg("auto.features.tutorial.components.concepts.guide.literal.64")}</SubHeading>
      <p>
        {msg("auto.features.tutorial.components.concepts.guide.literal.65")}
        <em>{msg("auto.features.tutorial.components.concepts.guide.literal.66")}</em>
        {msg("auto.features.tutorial.components.concepts.guide.literal.67")}
        <InlineCode>{msg("auto.features.tutorial.components.concepts.guide.literal.68")}</InlineCode>
        {msg("auto.features.tutorial.components.concepts.guide.literal.69")}
      </p>

      <SubHeading>{msg("auto.features.tutorial.components.concepts.guide.literal.70")}</SubHeading>
      <GepaLoopDiagram />
      <ol className="list-decimal pr-5 space-y-1.5">
        <li>
          <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.71")}</strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.72")}
        </li>
        <li>
          <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.73")}</strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.74")}
        </li>
        <li>
          <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.75")}</strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.76")}
          <InlineCode>
            {msg("auto.features.tutorial.components.concepts.guide.literal.274")}
          </InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.77")}
        </li>
        <li>
          <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.78")}</strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.79")}
          <InlineCode>
            {msg("auto.features.tutorial.components.concepts.guide.literal.275")}
          </InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.80")}
        </li>
        <li>
          <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.81")}</strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.82")}
          <em>{msg("auto.features.tutorial.components.concepts.guide.literal.83")}</em>
          {msg("auto.features.tutorial.components.concepts.guide.literal.84")}
        </li>
      </ol>
      <p className="text-[#5C4D40]">
        {msg("auto.features.tutorial.components.concepts.guide.literal.85")}
      </p>

      <SubHeading>{msg("auto.features.tutorial.components.concepts.guide.literal.86")}</SubHeading>
      <div className="my-3 overflow-hidden rounded-lg border border-[#E5DDD4] bg-white shadow-[0_1px_2px_rgba(28,22,18,0.05)]">
        <table className="w-full text-[13.5px]">
          <thead>
            <tr className="bg-[#F0EBE4] text-[#3D2E22]">
              <th
                className="text-right font-semibold px-3 py-2 w-1/2"
                style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
              >
                {msg("auto.features.tutorial.components.concepts.guide.literal.87")}
              </th>
              <th
                className="text-right font-semibold px-3 py-2 w-1/2 border-r border-[#E5DDD4]"
                style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
              >
                {msg("auto.features.tutorial.components.concepts.guide.literal.88")}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr className="bg-white">
              <td className="px-3 py-2 align-top text-[#3D2E22] border-t border-[#E5DDD4]">
                {msg("auto.features.tutorial.components.concepts.guide.literal.89")}
                <br />
                <span className="text-[12px] text-[#5C4D40]">
                  {msg("auto.features.tutorial.components.concepts.guide.literal.90")}
                </span>
                <br />
                {msg("auto.features.tutorial.components.concepts.guide.literal.91")}
                <br />
                <span className="text-[12px] text-[#5C4D40]">
                  {msg("auto.features.tutorial.components.concepts.guide.literal.92")}
                </span>
              </td>
              <td className="px-3 py-2 align-top text-[#3D2E22] border-t border-[#E5DDD4] border-r">
                {msg("auto.features.tutorial.components.concepts.guide.literal.89")}
                <br />
                {msg("auto.features.tutorial.components.concepts.guide.literal.91")}
                <br />
                {msg("auto.features.tutorial.components.concepts.guide.literal.93")}
              </td>
            </tr>
            <tr className="bg-[#FAF8F5]">
              <td className="px-3 py-2 align-top text-[#3D2E22] border-t border-[#E5DDD4]">
                <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.94")}</strong>
                {msg("auto.features.tutorial.components.concepts.guide.literal.95")}
                <br />→{" "}
                <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.96")}</strong>
                {msg("auto.features.tutorial.components.concepts.guide.literal.97")}
              </td>
              <td className="px-3 py-2 align-top text-[#3D2E22] border-t border-[#E5DDD4] border-r">
                <strong>{msg("auto.features.tutorial.components.concepts.guide.literal.98")}</strong>
                {msg("auto.features.tutorial.components.concepts.guide.literal.99")}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </GuideSection>
  );
}

function SectionParameters() {
  return (
    <GuideSection
      id="parameters"
      num="3"
      title={msg("auto.features.tutorial.components.concepts.guide.literal.3")}
      kicker={msg("auto.features.tutorial.components.concepts.guide.literal.100")}
    >
      <SubHeading>
        {msg("auto.features.tutorial.components.concepts.guide.literal.101")}
      </SubHeading>
      <p>{msg("auto.features.tutorial.components.concepts.guide.literal.102")}</p>
      <ParamTable
        rows={[
          {
            name: "auto",
            desc: (
              <>
                {msg("auto.features.tutorial.components.concepts.guide.literal.103")}
                <InlineCode>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.104")}
                </InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.105")}
                <InlineCode>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.106")}
                </InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.107")}
                <InlineCode>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.108")}
                </InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.109")}
                <strong>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.110")}
                </strong>
                {msg("auto.features.tutorial.components.concepts.guide.literal.38")}
              </>
            ),
          },
          {
            name: "max_full_evals",
            desc: (
              <>
                {msg("auto.features.tutorial.components.concepts.guide.literal.111")}
                <InlineCode>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.276")}
                </InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.112")}
              </>
            ),
          },
        ]}
      />

      <SubHeading>
        {msg("auto.features.tutorial.components.concepts.guide.literal.113")}
      </SubHeading>
      <ParamTable
        rows={[
          {
            name: "use_merge",
            desc: (
              <>
                {msg("auto.features.tutorial.components.concepts.guide.literal.114")}
                <InlineCode>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.277")}
                </InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.38")}
              </>
            ),
          },
          {
            name: "max_merge_invocations",
            desc: (
              <>
                {msg("auto.features.tutorial.components.concepts.guide.literal.115")}
                <InlineCode>5</InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.38")}
              </>
            ),
          },
        ]}
      />

      <SubHeading>
        {msg("auto.features.tutorial.components.concepts.guide.literal.116")}
      </SubHeading>
      <ParamTable
        rows={[
          {
            name: "num_threads",
            desc: (
              <>
                {msg("auto.features.tutorial.components.concepts.guide.literal.117")}
                <InlineCode>32</InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.126")}
              </>
            ),
          },
          {
            name: "failure_score",
            desc: (
              <>
                {msg("auto.features.tutorial.components.concepts.guide.literal.118")}
                <InlineCode>0.0</InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.38")}
              </>
            ),
          },
          {
            name: "perfect_score",
            desc: (
              <>
                {msg("auto.features.tutorial.components.concepts.guide.literal.119")}
                <InlineCode>1.0</InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.120")}
              </>
            ),
          },
          {
            name: "track_stats",
            desc: <>{msg("auto.features.tutorial.components.concepts.guide.literal.121")}</>,
          },
        ]}
      />

      <SubHeading>
        {msg("auto.features.tutorial.components.concepts.guide.literal.122")}
      </SubHeading>
      <p>
        <strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.123")}
        </strong>
        {msg("auto.features.tutorial.components.concepts.guide.literal.124")}
        <InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.278")}
        </InlineCode>
        {", "}
        <InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.279")}
        </InlineCode>
        {msg("auto.features.tutorial.components.concepts.guide.literal.125")}
        <InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.280")}
        </InlineCode>
        {msg("auto.features.tutorial.components.concepts.guide.literal.126")}
      </p>
      <ul className="list-disc pr-5 space-y-1">
        <li>
          <strong>
            <InlineCode>
              {msg("auto.features.tutorial.components.concepts.guide.literal.274")}
            </InlineCode>
            {":"}
          </strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.127")}
        </li>
      </ul>
    </GuideSection>
  );
}

function SectionTaskDefinition() {
  return (
    <GuideSection
      id="task-definition"
      num="4"
      title={msg("auto.features.tutorial.components.concepts.guide.literal.4")}
      kicker={msg("auto.features.tutorial.components.concepts.guide.literal.128")}
    >
      <SubHeading>
        {msg("auto.features.tutorial.components.concepts.guide.literal.129")}
      </SubHeading>
      <p>{msg("auto.features.tutorial.components.concepts.guide.literal.130")}</p>
      <ul className="list-disc pr-5 space-y-1">
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.131")}
          </strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.132")}
        </li>
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.133")}
          </strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.134")}
        </li>
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.135")}
          </strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.136")}
        </li>
      </ul>
      <CodeBlock
        lang="python"
        code={`import dspy

class AnswerQuestion(dspy.Signature):
    """Given a math word problem, return the numeric answer."""

    question: str = dspy.InputField(desc="A short word problem in Hebrew or English.")
    answer: str = dspy.OutputField(desc="The final numeric answer only.")
`}
      />

      <SubHeading>
        {msg("auto.features.tutorial.components.concepts.guide.literal.137")}
      </SubHeading>
      <p>
        {msg("auto.features.tutorial.components.concepts.guide.literal.138")}
        <InlineCode>200+</InlineCode>
        {msg("auto.features.tutorial.components.concepts.guide.literal.38")}
      </p>
      <p>
        <strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.139")}
        </strong>
        {msg("auto.features.tutorial.components.concepts.guide.literal.140")}
      </p>
      <div className="my-3 overflow-hidden rounded-lg border border-[#E5DDD4] bg-white shadow-[0_1px_2px_rgba(28,22,18,0.05)]">
        <table className="w-full text-[13.5px]">
          <thead>
            <tr className="bg-[#F0EBE4] text-[#3D2E22]">
              <th
                className="text-right font-semibold px-3 py-2 w-[24%]"
                style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
              >
                {msg("auto.features.tutorial.components.concepts.guide.literal.141")}
              </th>
              <th
                className="text-right font-semibold px-3 py-2"
                style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
              >
                {msg("auto.features.tutorial.components.concepts.guide.literal.142")}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr className="bg-white">
              <td className="px-3 py-2 align-top border-t border-[#E5DDD4]" dir="ltr">
                <InlineCode>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.281")}
                </InlineCode>{" "}
                {msg("auto.features.tutorial.components.concepts.guide.literal.143")}
              </td>
              <td className="px-3 py-2 align-top text-[#3D2E22] border-t border-[#E5DDD4]">
                {msg("auto.features.tutorial.components.concepts.guide.literal.144")}
              </td>
            </tr>
            <tr className="bg-[#FAF8F5]">
              <td className="px-3 py-2 align-top border-t border-[#E5DDD4]" dir="ltr">
                <InlineCode>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.282")}
                </InlineCode>{" "}
                {msg("auto.features.tutorial.components.concepts.guide.literal.145")}
              </td>
              <td className="px-3 py-2 align-top text-[#3D2E22] border-t border-[#E5DDD4]">
                {msg("auto.features.tutorial.components.concepts.guide.literal.146")}
              </td>
            </tr>
            <tr className="bg-white">
              <td className="px-3 py-2 align-top border-t border-[#E5DDD4]" dir="ltr">
                <InlineCode>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.283")}
                </InlineCode>{" "}
                {msg("auto.features.tutorial.components.concepts.guide.literal.147")}
              </td>
              <td className="px-3 py-2 align-top text-[#3D2E22] border-t border-[#E5DDD4]">
                {msg("auto.features.tutorial.components.concepts.guide.literal.148")}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <SubHeading>
        {msg("auto.features.tutorial.components.concepts.guide.literal.149")}
      </SubHeading>
      <p>
        <strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.150")}
        </strong>
        {msg("auto.features.tutorial.components.concepts.guide.literal.151")}
        <InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.284")}
        </InlineCode>
        {msg("auto.features.tutorial.components.concepts.guide.literal.152")}
        <InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.285")}
        </InlineCode>
        {msg("auto.features.tutorial.components.concepts.guide.literal.153")}
        <InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.286")}
        </InlineCode>
        {msg("auto.features.tutorial.components.concepts.guide.literal.38")}
      </p>
      <CodeBlock
        lang="python"
        code={msg("auto.features.tutorial.components.concepts.guide.literal.300")}
      />
      <p>{msg("auto.features.tutorial.components.concepts.guide.literal.154")}</p>
      <ul className="list-disc pr-5 space-y-1">
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.155")}
          </strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.156")}
          <InlineCode>1.0</InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.157")}
        </li>
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.158")}
          </strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.156")}
          <InlineCode>0.5</InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.159")}
        </li>
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.160")}
          </strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.156")}
          <InlineCode>0.0</InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.161")}
        </li>
      </ul>
    </GuideSection>
  );
}

function WorkflowFlow() {
  const steps = [
    msg("auto.features.tutorial.components.concepts.guide.literal.162"),
    msg("auto.features.tutorial.components.concepts.guide.literal.163"),
    msg("auto.features.tutorial.components.concepts.guide.literal.164"),
    msg("auto.features.tutorial.components.concepts.guide.literal.165"),
    msg("auto.features.tutorial.components.concepts.guide.literal.166"),
    msg("auto.features.tutorial.components.concepts.guide.literal.167"),
    msg("auto.features.tutorial.components.concepts.guide.literal.168"),
    msg("auto.features.tutorial.components.concepts.guide.literal.169"),
  ];
  return (
    <figure className="my-4 rounded-lg border border-[#E5DDD4] bg-white p-4 shadow-[0_1px_2px_rgba(28,22,18,0.05)]">
      <ol className="space-y-2" dir="rtl">
        {steps.map((label, idx) => (
          <li key={label} className="flex items-center gap-3">
            <span
              className={[
                "inline-flex items-center justify-center size-7 rounded-full text-[12px] font-bold flex-shrink-0",
                idx === steps.length - 1
                  ? "bg-[#3D2E22] text-[#FAF8F5]"
                  : "bg-[#EDE7DD] text-[#3D2E22] border border-[#3D2E22]",
              ].join(" ")}
              style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
            >
              {idx + 1}
            </span>
            <span
              className={[
                "flex-1 px-3 py-1.5 rounded-md border text-[13.5px]",
                idx === steps.length - 1
                  ? "bg-[#3D2E22] text-[#FAF8F5] border-[#3D2E22]"
                  : "bg-[#FAF8F5] text-[#3D2E22] border-[#E5DDD4]",
              ].join(" ")}
            >
              {label}
            </span>
            {idx < steps.length - 1 && (
              <ArrowLeft className="size-4 text-[#A69585] flex-shrink-0 rotate-90" aria-hidden />
            )}
          </li>
        ))}
      </ol>
    </figure>
  );
}

function SectionWorkflow() {
  const endpoints: Array<[string, string]> = [
    ["POST /run", msg("auto.features.tutorial.components.concepts.guide.literal.197")],
    ["POST /grid-search", msg("auto.features.tutorial.components.concepts.guide.literal.198")],
    ["GET /optimizations", msg("auto.features.tutorial.components.concepts.guide.literal.199")],
    [
      "GET /optimizations/{id}",
      msg("auto.features.tutorial.components.concepts.guide.literal.200"),
    ],
    [
      "GET /optimizations/{id}/summary",
      msg("auto.features.tutorial.components.concepts.guide.literal.201"),
    ],
    [
      "GET /optimizations/{id}/logs",
      msg("auto.features.tutorial.components.concepts.guide.literal.202"),
    ],
    [
      "GET /optimizations/{id}/stream",
      msg("auto.features.tutorial.components.concepts.guide.literal.203"),
    ],
    [
      "GET /optimizations/{id}/artifact",
      msg("auto.features.tutorial.components.concepts.guide.literal.204"),
    ],
    [
      "GET /optimizations/{id}/grid-result",
      msg("auto.features.tutorial.components.concepts.guide.literal.205"),
    ],
    [
      "POST /optimizations/{id}/cancel",
      msg("auto.features.tutorial.components.concepts.guide.literal.206"),
    ],
    [
      "POST /optimizations/{id}/clone",
      msg("auto.features.tutorial.components.concepts.guide.literal.207"),
    ],
    [
      "POST /optimizations/{id}/retry",
      msg("auto.features.tutorial.components.concepts.guide.literal.208"),
    ],
    [
      "GET /serve/{id}/info",
      msg("auto.features.tutorial.components.concepts.guide.literal.209"),
    ],
    ["POST /serve/{id}", msg("auto.features.tutorial.components.concepts.guide.literal.210")],
    ["GET /health", msg("auto.features.tutorial.components.concepts.guide.literal.211")],
    ["GET /queue", msg("auto.features.tutorial.components.concepts.guide.literal.212")],
  ];
  return (
    <GuideSection
      id="workflow"
      num="5"
      title={msg("auto.features.tutorial.components.concepts.guide.literal.5")}
      kicker={msg("auto.features.tutorial.components.concepts.guide.literal.170")}
    >
      <SubHeading>
        {msg("auto.features.tutorial.components.concepts.guide.literal.171")}
      </SubHeading>
      <WorkflowFlow />

      <SubHeading>
        {msg("auto.features.tutorial.components.concepts.guide.literal.172")}
      </SubHeading>
      <p>{msg("auto.features.tutorial.components.concepts.guide.literal.173")}</p>
      <ParamTable
        rows={[
          {
            name: "module_name",
            desc: (
              <>
                {msg("auto.features.tutorial.components.concepts.guide.literal.174")}
                <InlineCode>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.175")}
                </InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.176")}
                <InlineCode>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.287")}
                </InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.177")}
              </>
            ),
          },
          {
            name: "optimizer_name",
            desc: (
              <>
                {msg("auto.features.tutorial.components.concepts.guide.literal.178")}
                <InlineCode>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.179")}
                </InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.126")}
              </>
            ),
          },
          {
            name: "signature_code",
            desc: <>{msg("auto.features.tutorial.components.concepts.guide.literal.180")}</>,
          },
          {
            name: "metric_code",
            desc: <>{msg("auto.features.tutorial.components.concepts.guide.literal.181")}</>,
          },
          {
            name: "dataset",
            desc: <>{msg("auto.features.tutorial.components.concepts.guide.literal.182")}</>,
          },
          {
            name: "column_mapping",
            desc: (
              <>
                {msg("auto.features.tutorial.components.concepts.guide.literal.183")}
                <InlineCode>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.288")}
                </InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.184")}
                <InlineCode>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.289")}
                </InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.126")}
              </>
            ),
          },
          {
            name: "model_config",
            desc: <>{msg("auto.features.tutorial.components.concepts.guide.literal.185")}</>,
          },
          {
            name: "reflection_lm",
            desc: (
              <>
                {msg("auto.features.tutorial.components.concepts.guide.literal.186")}
                <strong>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.187")}
                </strong>
                {msg("auto.features.tutorial.components.concepts.guide.literal.126")}
              </>
            ),
          },
          {
            name: "optimizer_kwargs",
            desc: (
              <>
                {msg("auto.features.tutorial.components.concepts.guide.literal.188")}
                <InlineCode>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.189")}
                </InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.126")}
              </>
            ),
          },
          {
            name: "split_fractions",
            desc: (
              <>
                {msg("auto.features.tutorial.components.concepts.guide.literal.190")}
                <InlineCode>
                  {msg("auto.features.tutorial.components.concepts.guide.literal.191")}
                </InlineCode>
                {msg("auto.features.tutorial.components.concepts.guide.literal.126")}
              </>
            ),
          },
          {
            name: "shuffle",
            desc: <>{msg("auto.features.tutorial.components.concepts.guide.literal.192")}</>,
          },
          {
            name: "seed",
            desc: <>{msg("auto.features.tutorial.components.concepts.guide.literal.193")}</>,
          },
        ]}
      />

      <SubHeading>
        {msg("auto.features.tutorial.components.concepts.guide.literal.194")}
      </SubHeading>
      <p>{msg("auto.features.tutorial.components.concepts.guide.literal.195")}</p>
      <div className="my-3 overflow-hidden rounded-lg border border-[#E5DDD4] bg-white shadow-[0_1px_2px_rgba(28,22,18,0.05)]">
        <table className="w-full text-[13.5px]">
          <thead>
            <tr className="bg-[#F0EBE4] text-[#3D2E22]">
              <th
                className="text-right font-semibold px-3 py-2 w-[40%]"
                style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
              >
                {msg("auto.features.tutorial.components.concepts.guide.literal.196")}
              </th>
              <th
                className="text-right font-semibold px-3 py-2"
                style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
              >
                {msg("auto.features.tutorial.components.concepts.guide.literal.142")}
              </th>
            </tr>
          </thead>
          <tbody>
            {endpoints.map(([endpoint, purpose], i) => (
              <tr key={endpoint} className={i % 2 === 0 ? "bg-white" : "bg-[#FAF8F5]"}>
                <td className="px-3 py-2 align-top border-t border-[#E5DDD4]" dir="ltr">
                  <InlineCode>{endpoint}</InlineCode>
                </td>
                <td className="px-3 py-2 align-top text-[#3D2E22] border-t border-[#E5DDD4]">
                  {purpose}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <SubHeading>
        {msg("auto.features.tutorial.components.concepts.guide.literal.213")}
      </SubHeading>
      <p>{msg("auto.features.tutorial.components.concepts.guide.literal.214")}</p>
      <ul className="list-disc pr-5 space-y-1">
        <li>
          <InlineCode>
            {msg("auto.features.tutorial.components.concepts.guide.literal.290")}
          </InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.215")}
        </li>
        <li>
          <InlineCode>
            {msg("auto.features.tutorial.components.concepts.guide.literal.291")}
          </InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.216")}
        </li>
        <li>
          <InlineCode>
            {msg("auto.features.tutorial.components.concepts.guide.literal.292")}
          </InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.217")}
        </li>
        <li>
          <InlineCode>
            {msg("auto.features.tutorial.components.concepts.guide.literal.293")}
          </InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.218")}
        </li>
        <li>
          <InlineCode>
            {msg("auto.features.tutorial.components.concepts.guide.literal.294")}
          </InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.219")}
        </li>
      </ul>
    </GuideSection>
  );
}

function SectionTips() {
  const problems: Array<[string, React.ReactNode]> = [
    [
      msg("auto.features.tutorial.components.concepts.guide.literal.241"),
      msg("auto.features.tutorial.components.concepts.guide.literal.242"),
    ],
    [
      msg("auto.features.tutorial.components.concepts.guide.literal.243"),
      msg("auto.features.tutorial.components.concepts.guide.literal.244"),
    ],
    [
      msg("auto.features.tutorial.components.concepts.guide.literal.245"),
      <>
        {msg("auto.features.tutorial.components.concepts.guide.literal.246")}
        <InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.295")}
        </InlineCode>
        {msg("auto.features.tutorial.components.concepts.guide.literal.247")}
        <InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.296")}
        </InlineCode>
        {msg("auto.features.tutorial.components.concepts.guide.literal.38")}
      </>,
    ],
    [
      msg("auto.features.tutorial.components.concepts.guide.literal.248"),
      msg("auto.features.tutorial.components.concepts.guide.literal.249"),
    ],
    [
      msg("auto.features.tutorial.components.concepts.guide.literal.250"),
      msg("auto.features.tutorial.components.concepts.guide.literal.251"),
    ],
  ];
  return (
    <GuideSection
      id="tips"
      num="6"
      title={msg("auto.features.tutorial.components.concepts.guide.literal.6")}
      kicker={msg("auto.features.tutorial.components.concepts.guide.literal.220")}
    >
      <SubHeading>
        {msg("auto.features.tutorial.components.concepts.guide.literal.221")}
      </SubHeading>
      <ul className="list-disc pr-5 space-y-1">
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.222")}
          </strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.223")}
        </li>
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.224")}
          </strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.225")}
        </li>
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.226")}
          </strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.227")}
        </li>
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.228")}
          </strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.229")}
        </li>
      </ul>

      <SubHeading>
        {msg("auto.features.tutorial.components.concepts.guide.literal.230")}
      </SubHeading>
      <ul className="list-disc pr-5 space-y-1">
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.231")}
          </strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.232")}
        </li>
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.233")}
          </strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.234")}
        </li>
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.235")}
          </strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.236")}
        </li>
        <li>
          <strong>
            {msg("auto.features.tutorial.components.concepts.guide.literal.32")}
          </strong>
          {msg("auto.features.tutorial.components.concepts.guide.literal.237")}
          <InlineCode>
            {msg("auto.features.tutorial.components.concepts.guide.literal.274")}
          </InlineCode>
          {msg("auto.features.tutorial.components.concepts.guide.literal.38")}
        </li>
      </ul>

      <SubHeading>
        {msg("auto.features.tutorial.components.concepts.guide.literal.238")}
      </SubHeading>
      <div className="my-3 overflow-hidden rounded-lg border border-[#E5DDD4] bg-white shadow-[0_1px_2px_rgba(28,22,18,0.05)]">
        <table className="w-full text-[13.5px]">
          <thead>
            <tr className="bg-[#F0EBE4] text-[#3D2E22]">
              <th
                className="text-right font-semibold px-3 py-2 w-[36%]"
                style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
              >
                {msg("auto.features.tutorial.components.concepts.guide.literal.239")}
              </th>
              <th
                className="text-right font-semibold px-3 py-2"
                style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
              >
                {msg("auto.features.tutorial.components.concepts.guide.literal.240")}
              </th>
            </tr>
          </thead>
          <tbody>
            {problems.map(([problem, solution], i) => (
              <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-[#FAF8F5]"}>
                <td className="px-3 py-2 align-top text-[#3D2E22] border-t border-[#E5DDD4] font-medium">
                  {problem}
                </td>
                <td className="px-3 py-2 align-top text-[#3D2E22] border-t border-[#E5DDD4]">
                  {solution}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </GuideSection>
  );
}

function SectionGlossary() {
  const rows: Array<[string, string]> = [
    ["LLM", msg("auto.features.tutorial.components.concepts.guide.literal.255")],
    ["Prompt", msg("auto.features.tutorial.components.concepts.guide.literal.256")],
    ["DSPy", msg("auto.features.tutorial.components.concepts.guide.literal.257")],
    ["Optimizer", msg("auto.features.tutorial.components.concepts.guide.literal.258")],
    ["GEPA", msg("auto.features.tutorial.components.concepts.guide.literal.259")],
    ["Reflection", msg("auto.features.tutorial.components.concepts.guide.literal.260")],
    ["Signature", msg("auto.features.tutorial.components.concepts.guide.literal.261")],
    ["Metric", msg("auto.features.tutorial.components.concepts.guide.literal.262")],
    ["Dataset", msg("auto.features.tutorial.components.concepts.guide.literal.263")],
    ["Train / Val / Test", msg("auto.features.tutorial.components.concepts.guide.literal.264")],
    ["Optimization", msg("auto.features.tutorial.components.concepts.guide.literal.265")],
    ["Artifact", msg("auto.features.tutorial.components.concepts.guide.literal.266")],
    ["Rollout", msg("auto.features.tutorial.components.concepts.guide.literal.267")],
    ["Trace", msg("auto.features.tutorial.components.concepts.guide.literal.268")],
    ["ChainOfThought", msg("auto.features.tutorial.components.concepts.guide.literal.269")],
    ["reflection_lm", msg("auto.features.tutorial.components.concepts.guide.literal.270")],
  ];
  return (
    <GuideSection
      id="glossary"
      num="7"
      title={msg("auto.features.tutorial.components.concepts.guide.literal.7")}
      kicker={msg("auto.features.tutorial.components.concepts.guide.literal.252")}
    >
      <div className="my-3 overflow-hidden rounded-lg border border-[#E5DDD4] bg-white shadow-[0_1px_2px_rgba(28,22,18,0.05)]">
        <table className="w-full text-[13.5px]">
          <thead>
            <tr className="bg-[#F0EBE4] text-[#3D2E22]">
              <th
                className="text-right font-semibold px-3 py-2 w-[34%]"
                style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
              >
                {msg("auto.features.tutorial.components.concepts.guide.literal.253")}
              </th>
              <th
                className="text-right font-semibold px-3 py-2"
                style={{ fontFamily: '"Inter Variable", "Heebo Variable", system-ui, sans-serif' }}
              >
                {msg("auto.features.tutorial.components.concepts.guide.literal.254")}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([term, explanation], i) => (
              <tr key={term} className={i % 2 === 0 ? "bg-white" : "bg-[#FAF8F5]"}>
                <td className="px-3 py-2 align-top text-[#3D2E22] border-t border-[#E5DDD4]" dir="ltr">
                  <InlineCode>{term}</InlineCode>
                </td>
                <td className="px-3 py-2 align-top text-[#3D2E22] border-t border-[#E5DDD4]">
                  {explanation}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </GuideSection>
  );
}
