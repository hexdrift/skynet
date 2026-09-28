"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  Books,
  Brain,
  Columns,
  Cpu,
  Cube,
  Database,
  DiceFive,
  FileText,
  Gauge,
  Gear,
  GearSix,
  GitMerge,
  Globe,
  HardDrives,
  Key,
  Lock,
  Plug,
  Repeat,
  Ruler,
  ShieldCheck,
  Shuffle,
  Sparkle,
  Stack,
  Table,
  Tag,
  Target,
  TreeStructure,
  Wrench,
} from "@/shared/ui/icons";
import { FadeIn } from "@/shared/ui/motion";
import { HelpTip } from "@/shared/ui/help-tip";
import { RolePill, type ColumnRoleTone } from "@/shared/ui/role-pill";
import type {
  ColumnMapping,
  ModelConfig,
  OptimizationPayloadResponse,
  OptimizationStatusResponse,
  PairResult,
} from "@/shared/types/api";
import { tip } from "@/shared/lib/tooltips";
import { formatMsg, msg } from "@/shared/lib/messages";
import { perLocale } from "@/shared/lib/per-locale";
import { formatBytes, moduleLabel } from "@/shared/lib/formatters";
import { TERMS } from "@/shared/lib/terms";
import { InfoCard } from "./ui-primitives";
import {
  ConfigCarousel,
  ModelCard,
  SlideHeroCard,
  SlideMiniCard,
  SlideNote,
  SplitBar,
} from "./ConfigCarousel";

const CONFIG_SLIDES = perLocale(() => [
  {
    id: "general",
    label: msg("optimization.config.slide_general"),
    icon: <Tag className="size-5" />,
    tip: tip("config.section.general"),
  },
  {
    id: "optimization",
    label: `${msg("auto.features.optimizations.components.configtab.5")}${TERMS.optimization}`,
    icon: <Gear className="size-5" />,
    tip: tip("config.section.summary"),
  },
  {
    id: "models",
    label: msg("auto.features.optimizations.components.configtab.6"),
    icon: <Cpu className="size-5" />,
    tip: tip("config.section.models"),
  },
  {
    id: "data",
    label: msg("auto.features.optimizations.components.configtab.8"),
    icon: <Database className="size-5" />,
    tip: tip("config.section.data"),
  },
]);

const OPT_PARAM_LABELS: Record<string, string> = perLocale(() => ({
  auto: msg("auto.features.optimizations.components.configtab.literal.1"),
  max_bootstrapped_demos: msg("auto.features.optimizations.components.configtab.literal.2"),
  max_labeled_demos: msg("auto.features.optimizations.components.configtab.literal.3"),
  minibatch: msg("auto.features.optimizations.components.configtab.literal.4"),
  minibatch_size: msg("auto.features.optimizations.components.configtab.literal.5"),
  reflection_minibatch_size: msg("auto.features.optimizations.components.configtab.literal.6"),
  max_full_evals: msg("auto.features.optimizations.components.configtab.literal.7"),
  max_metric_calls: msg("submit.metric_calls"),
  use_merge: msg("auto.features.optimizations.components.configtab.literal.8"),
  pxn_parents: msg("submit.pxn.parents"),
  pxn_proposals: msg("submit.pxn.proposals"),
  metric: TERMS.metric,
}));
const OPT_PARAM_TIPS: Record<string, string> = perLocale(() => ({
  auto: msg("auto.features.optimizations.components.configtab.literal.9"),
  max_bootstrapped_demos: msg("auto.features.optimizations.components.configtab.literal.10"),
  max_labeled_demos: formatMsg("auto.features.optimizations.components.configtab.template.1", {
    p1: TERMS.dataset,
    p2: TERMS.model,
  }),
  minibatch: formatMsg("auto.features.optimizations.components.configtab.template.2", {
    p1: TERMS.dataset,
  }),
  minibatch_size: msg("auto.features.optimizations.components.configtab.literal.11"),
  reflection_minibatch_size: formatMsg(
    "auto.features.optimizations.components.configtab.template.3",
    { p1: TERMS.model },
  ),
  max_full_evals: msg("auto.features.optimizations.components.configtab.literal.12"),
  max_metric_calls: msg("tooltip.submit.metric_calls"),
  use_merge: msg("auto.features.optimizations.components.configtab.literal.13"),
  pxn_parents: msg("tooltip.submit.pxn_parents"),
  pxn_proposals: msg("tooltip.submit.pxn_proposals"),
}));

// Raw kwarg identifiers read the same in every locale; the tooltip carries
// the translated explanation of which call the value was handed to.
function humanizeKey(key: string): string {
  const spaced = key.replace(/_/g, " ").trim();
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : key;
}

function labelWithTip(key: string, fallbackTip: string): ReactNode {
  const label = OPT_PARAM_LABELS[key] || humanizeKey(key);
  const tipText = OPT_PARAM_TIPS[key] ?? fallbackTip;
  return <HelpTip text={tipText}>{label}</HelpTip>;
}

const PARAM_ICONS: Record<string, ReactNode> = {
  auto: <Gauge className="size-3.5" />,
  max_bootstrapped_demos: <Sparkle className="size-3.5" />,
  max_labeled_demos: <Tag className="size-3.5" />,
  minibatch: <Stack className="size-3.5" />,
  minibatch_size: <Ruler className="size-3.5" />,
  reflection_minibatch_size: <Brain className="size-3.5" />,
  max_full_evals: <Repeat className="size-3.5" />,
  // Shares Gauge with `auto`: both are the run's (mutually exclusive) budget knob.
  max_metric_calls: <Gauge className="size-3.5" />,
  use_merge: <GitMerge className="size-3.5" />,
  pxn_parents: <TreeStructure className="size-3.5" />,
  pxn_proposals: <Sparkle className="size-3.5" />,
};

function paramIcon(key: string): ReactNode {
  return PARAM_ICONS[key] ?? <GearSix className="size-3.5" />;
}

// The GEPA budget level arrives as the raw "light" / "medium" / "heavy"
// string; translate it to the same Hebrew the submit summary shows so the
// value reads consistently across surfaces.
const AUTO_LEVEL_LABELS: Record<string, string> = perLocale(() => ({
  light: msg("auto.features.optimizations.components.configtab.literal.18"),
  medium: msg("auto.features.optimizations.components.configtab.literal.19"),
  heavy: msg("auto.features.optimizations.components.configtab.literal.20"),
}));

function yesNo(v: boolean): string {
  return v
    ? msg("auto.features.optimizations.components.configtab.literal.14")
    : msg("auto.features.optimizations.components.configtab.literal.15");
}

function formatParamValue(k: string, v: unknown): string {
  if (typeof v === "boolean") return yesNo(v);
  if (v == null) return "—";
  if (k === "auto" && typeof v === "string" && AUTO_LEVEL_LABELS[v]) return AUTO_LEVEL_LABELS[v];
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

// The pair only carries the model name + reasoning effort; the richer
// ModelConfig (temperature, max_tokens, extra) lives on job.generation_models
// / job.reflection_models. Match by name first, narrowing on reasoning
// effort when multiple configs share the name. Fall back to a synthesized
// config so the ModelCard still renders when the grid lists are missing
// (older payloads, partial responses).
function pickPairModelConfig(
  configs: ModelConfig[] | undefined,
  name: string,
  reasoningEffort: string | null | undefined,
): Record<string, unknown> {
  const candidates = (configs ?? []).filter((c) => c.name === name);
  const matched =
    candidates.find(
      (c) =>
        ((c.extra?.reasoning_effort as string | undefined) ?? null) === (reasoningEffort ?? null),
    ) ?? candidates[0];
  if (matched) return matched as unknown as Record<string, unknown>;
  return reasoningEffort ? { name, extra: { reasoning_effort: reasoningEffort } } : { name };
}

type ConfigRow = { label: ReactNode; value: string; icon: ReactNode };

function MiniGrid({ rows }: { rows: ConfigRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div
      className="grid gap-3"
      style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(11rem, 100%), 1fr))" }}
    >
      {rows.map((row, index) => (
        <SlideMiniCard key={index} label={row.label} value={row.value} icon={row.icon} />
      ))}
    </div>
  );
}

/** Every dataset column with the role the run gave it, in the file's own order. */
function ColumnRoles({ mapping, order }: { mapping: ColumnMapping; order: string[] | null }) {
  const inputs = mapping.inputs ?? {};
  const outputs = mapping.outputs ?? {};
  const columns = order ?? [...Object.keys(inputs), ...Object.keys(outputs)];
  if (columns.length === 0) return null;
  const roleLabels = {
    input: msg("auto.features.submit.components.steps.summarystep.literal.6"),
    output: msg("auto.features.submit.components.steps.summarystep.literal.7"),
    ignore: msg("auto.features.submit.components.steps.summarystep.literal.8"),
  };
  return (
    <div className="rounded-xl border border-border/45 bg-background/65 p-4">
      <div className="mb-3 flex items-center gap-2 text-[0.6875rem] font-semibold uppercase tracking-widest text-muted-foreground">
        <Columns className="size-3.5" aria-hidden="true" />
        <HelpTip text={tip("submit.column_roles")}>
          {msg("auto.features.submit.components.steps.summarystep.11")}
        </HelpTip>
      </div>
      <ul className="flex flex-wrap gap-2">
        {columns.map((column) => {
          const role: ColumnRoleTone =
            column in inputs ? "input" : column in outputs ? "output" : "ignore";
          const field =
            role === "input" ? inputs[column] : role === "output" ? outputs[column] : null;
          const renamed = field && field !== column ? field : null;
          return (
            <li
              key={column}
              className="inline-flex max-w-full items-center gap-2 rounded-full border border-border/45 bg-background/80 py-1 pe-1 ps-3 text-xs"
            >
              <span className="truncate font-mono font-medium text-foreground" dir="ltr">
                {renamed ? `${column} · ${renamed}` : column}
              </span>
              <RolePill role={role}>{roleLabels[role]}</RolePill>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * Every setting the run was submitted with, grouped into general / optimization
 * / models / data slides. Reads the stored payload first and falls back to the
 * summarised job fields, so older runs whose payload lacks a field still show
 * what the job record knows. Nothing here is gated on a display mode: the tab
 * is the record of what actually ran.
 */
export function ConfigTab({
  job,
  payload,
  activePair,
}: {
  job: OptimizationStatusResponse;
  payload: OptimizationPayloadResponse | null;
  activePair?: PairResult;
}) {
  const p = (payload?.payload ?? {}) as Record<string, unknown>;
  const isGrid = job.optimization_type === "grid_search";

  const name = nonEmptyString(p.name) ?? nonEmptyString(job.name) ?? "—";
  const description = nonEmptyString(p.description) ?? nonEmptyString(job.description);
  const isPrivate = typeof p.is_private === "boolean" ? p.is_private : null;
  const tokenSource =
    p.token_source === "byok" || p.token_source === "managed" ? p.token_source : null;
  const targetScore = typeof p.target_score === "number" ? p.target_score : null;

  const generalRows: ConfigRow[] = [];
  if (isPrivate != null) {
    generalRows.push({
      label: <HelpTip text={tip("submit.privacy")}>{msg("submit.basics.privacy.label")}</HelpTip>,
      value: isPrivate ? msg("submit.basics.privacy.private") : msg("submit.basics.privacy.public"),
      icon: isPrivate ? <Lock /> : <Globe />,
    });
  }
  if (tokenSource) {
    generalRows.push({
      label: (
        <HelpTip text={tip("config.token_source")}>
          {msg("optimization.config.token_source")}
        </HelpTip>
      ),
      value: tokenSource === "byok" ? msg("model_source.byok") : msg("model_source.managed"),
      icon: tokenSource === "byok" ? <Key /> : <ShieldCheck />,
    });
  }
  if (targetScore != null) {
    generalRows.push({
      label: (
        <HelpTip text={tip("submit.target_score")}>
          {msg("auto.features.submit.components.steps.summarystep.25")}
        </HelpTip>
      ),
      value: `${targetScore}%`,
      icon: <Target />,
    });
  }

  const splitFractions = (p.split_fractions ??
    job.split_fractions ?? { train: 0.7, val: 0.15, test: 0.15 }) as {
    train: number;
    val: number;
    test: number;
  };
  const shuffleVal =
    p.shuffle != null ? Boolean(p.shuffle) : job.shuffle != null ? job.shuffle : true;
  const seedVal = (p.seed ?? job.seed) as number | null | undefined;
  const optKw = asRecord(p.optimizer_kwargs) ?? job.optimizer_kwargs ?? {};
  const modKw = asRecord(p.module_kwargs) ?? job.module_kwargs ?? {};
  const compKw = asRecord(p.compile_kwargs) ?? job.compile_kwargs ?? {};
  const modelCfg = asRecord(p.model_config) ?? job.model_settings ?? null;
  const reflCfg = asRecord(p.reflection_model_config);
  const taskCfg = asRecord(p.task_model_config);
  const workflow = asRecord(p.workflow);
  const workflowNodes = Array.isArray(workflow?.nodes) ? workflow.nodes.length : null;
  const workflowEdges = Array.isArray(workflow?.edges) ? workflow.edges.length : null;

  // Tool sources ride on react runs and on workflows whose steps call tools;
  // show them whenever the payload carries one rather than keying on the module.
  const toolSource = asRecord(p.tool_source);
  const toolRows: ConfigRow[] = [];
  if (toolSource && typeof toolSource.kind === "string") {
    const kind = toolSource.kind;
    toolRows.push({
      label: (
        <HelpTip text={tip("react.tool_source")}>{msg("submit.react.tool_source_label")}</HelpTip>
      ),
      value:
        kind === "live_mcp"
          ? msg("optimization.config.tool_source.live_mcp")
          : kind === "dataset_snapshot"
            ? msg("optimization.config.tool_source.dataset_snapshot")
            : kind,
      icon: <Wrench />,
    });
    const mcpUrl = nonEmptyString(toolSource.mcp_url);
    if (mcpUrl) {
      toolRows.push({
        label: <HelpTip text={tip("react.mcp_url")}>{msg("submit.react.mcp_url_label")}</HelpTip>,
        value: mcpUrl,
        icon: <Plug />,
      });
    }
    const filter = Array.isArray(toolSource.tool_filter) ? toolSource.tool_filter : null;
    toolRows.push({
      label: <HelpTip text={tip("config.tool_access")}>{msg("submit.react.tools_access")}</HelpTip>,
      value: filter
        ? formatMsg("submit.react.tools_count", { p1: filter.length })
        : msg("submit.react.tools_all"),
      icon: <Wrench />,
    });
  }

  const gridRows: ConfigRow[] = [];
  if (isGrid) {
    if (job.total_pairs != null) {
      gridRows.push({
        label: (
          <HelpTip text={tip("config.model_pairs")}>
            {msg("optimization.config.model_pairs")}
          </HelpTip>
        ),
        value: String(job.total_pairs),
        icon: <Cpu />,
      });
    }
    if (typeof p.use_all_available_generation_models === "boolean") {
      gridRows.push({
        label: (
          <HelpTip text={tip("config.all_generation_models")}>
            {msg("optimization.config.all_generation_models")}
          </HelpTip>
        ),
        value: yesNo(p.use_all_available_generation_models),
        icon: <Cpu />,
      });
    }
    if (typeof p.use_all_available_reflection_models === "boolean") {
      gridRows.push({
        label: (
          <HelpTip text={tip("config.all_reflection_models")}>
            {msg("optimization.config.all_reflection_models")}
          </HelpTip>
        ),
        value: yesNo(p.use_all_available_reflection_models),
        icon: <Brain />,
      });
    }
  }

  const optimizationRows: ConfigRow[] = [
    ...(workflowNodes != null && workflowEdges != null
      ? [
          {
            label: (
              <HelpTip text={tip("config.workflow")}>{msg("optimization.config.workflow")}</HelpTip>
            ),
            value: formatMsg("optimization.config.workflow_graph", {
              nodes: workflowNodes,
              edges: workflowEdges,
            }),
            icon: <TreeStructure />,
          },
        ]
      : []),
    ...toolRows,
    ...gridRows,
    // `metric` is the scoring callable itself; the code tab shows its source.
    ...Object.entries(optKw)
      .filter(([k]) => k !== "metric")
      .map(([k, v]) => ({
        label: labelWithTip(k, tip("config.optimizer_kwarg")),
        value: formatParamValue(k, v),
        icon: paramIcon(k),
      })),
    ...Object.entries(modKw).map(([k, v]) => ({
      label: <HelpTip text={tip("config.module_kwarg")}>{humanizeKey(k)}</HelpTip>,
      value: formatParamValue(k, v),
      icon: <Cube />,
    })),
    ...Object.entries(compKw).map(([k, v]) => ({
      label: <HelpTip text={tip("config.compile_kwarg")}>{humanizeKey(k)}</HelpTip>,
      value: formatParamValue(k, v),
      icon: <Stack />,
    })),
  ];

  const datasetFilename = nonEmptyString(p.dataset_filename);
  const inlineRows = Array.isArray(p.dataset) ? p.dataset.length : null;
  const datasetRows = job.dataset_rows ?? inlineRows;
  const columnMapping =
    (asRecord(p.column_mapping) as ColumnMapping | null) ?? job.column_mapping ?? null;
  const columnOrder = Array.isArray(p.column_order)
    ? p.column_order.filter((c): c is string => typeof c === "string")
    : null;

  const dataRows: ConfigRow[] = [];
  if (datasetFilename) {
    dataRows.push({
      label: (
        <HelpTip text={tip("submit.dataset_file")}>
          {msg("auto.features.submit.components.steps.summarystep.7")}
        </HelpTip>
      ),
      value: datasetFilename,
      icon: <FileText />,
    });
  }
  if (datasetRows != null) {
    dataRows.push({
      label: <HelpTip text={tip("submit.dataset_size")}>{msg("optimization.config.rows")}</HelpTip>,
      value: String(datasetRows),
      icon: <Table />,
    });
  }
  if (job.stored_bytes) {
    dataRows.push({
      label: (
        <HelpTip text={tip("submit.dataset_size")}>
          {msg("auto.features.submit.components.steps.summarystep.8")}
        </HelpTip>
      ),
      value: formatBytes(job.stored_bytes),
      icon: <HardDrives />,
    });
  }

  const taskModelLabel = msg("optimization.config.task_model");

  return (
    <>
      <FadeIn>
        <p className="mb-4 max-w-3xl text-sm text-muted-foreground">
          {msg("auto.features.optimizations.components.configtab.2")}
          {TERMS.optimization}
          {msg("auto.features.optimizations.components.configtab.3")}
          {TERMS.model}, {TERMS.optimizer}
          {msg("auto.features.optimizations.components.configtab.4")}
        </p>
      </FadeIn>
      <ConfigCarousel
        slides={CONFIG_SLIDES}
        renderSlide={(activeSlide) => (
          <>
            {activeSlide === 0 && (
              <div className="flex min-h-[24rem] flex-col gap-5">
                <div className="grid items-stretch gap-3 md:grid-cols-2">
                  <SlideHeroCard
                    index={0}
                    label={
                      <HelpTip text={tip("submit.name")}>
                        {msg("auto.features.submit.components.steps.summarystep.3")}
                        {TERMS.optimization}
                      </HelpTip>
                    }
                    value={name}
                    icon={<Tag />}
                  />
                  <SlideHeroCard
                    index={1}
                    label={
                      <HelpTip text={tip("submit.optimization_type")}>
                        {msg("auto.features.submit.components.steps.summarystep.4")}
                        {TERMS.optimization}
                      </HelpTip>
                    }
                    value={
                      isGrid
                        ? msg("auto.features.submit.components.steps.summarystep.literal.5")
                        : msg("auto.features.submit.components.steps.summarystep.literal.4")
                    }
                    icon={<Stack />}
                  />
                </div>
                <MiniGrid rows={generalRows} />
                {description && (
                  <SlideNote
                    label={
                      <HelpTip text={tip("config.description")}>
                        {msg("optimization.config.description")}
                      </HelpTip>
                    }
                    text={description}
                  />
                )}
              </div>
            )}

            {activeSlide === 1 && (
              <div className="flex min-h-[24rem] flex-col gap-5">
                <div className="grid items-stretch gap-3 md:grid-cols-2">
                  <SlideHeroCard
                    index={0}
                    label={
                      <HelpTip text={tip("module.choice")}>
                        {msg("auto.features.optimizations.components.configtab.1")}
                      </HelpTip>
                    }
                    value={moduleLabel(job.module_name)}
                    icon={<Cube />}
                  />
                  <SlideHeroCard
                    index={1}
                    label={<HelpTip text={tip("optimizer.choice")}>{TERMS.optimizer}</HelpTip>}
                    value={job.optimizer_name ?? "—"}
                    icon={<Target />}
                  />
                </div>
                <MiniGrid rows={optimizationRows} />
              </div>
            )}

            {activeSlide === 2 && (
              <div className="min-h-[24rem]">
                {!isGrid ? (
                  <div
                    className="grid gap-4"
                    style={{
                      gridTemplateColumns: "repeat(auto-fit, minmax(min(17rem, 100%), 1fr))",
                    }}
                  >
                    {modelCfg && <ModelCard label={msg("model.generation.label")} cfg={modelCfg} />}
                    {reflCfg && <ModelCard label={TERMS.reflectionModel} cfg={reflCfg} />}
                    {taskCfg && (
                      <ModelCard
                        label={taskModelLabel}
                        labelTip={tip("config.task_model")}
                        cfg={taskCfg}
                      />
                    )}
                    {!modelCfg && !reflCfg && !taskCfg && job.model_name && (
                      <>
                        <ModelCard
                          label={msg("model.generation.label")}
                          cfg={{ name: job.model_name, ...(job.model_settings || {}) }}
                        />
                        {job.reflection_model_name && (
                          <ModelCard
                            label={TERMS.reflectionModel}
                            cfg={{ name: job.reflection_model_name }}
                          />
                        )}
                        {job.task_model_name && (
                          <ModelCard
                            label={taskModelLabel}
                            labelTip={tip("config.task_model")}
                            cfg={{ name: job.task_model_name }}
                          />
                        )}
                      </>
                    )}
                  </div>
                ) : activePair ? (
                  <div
                    className="grid gap-4"
                    style={{
                      gridTemplateColumns: "repeat(auto-fit, minmax(min(17rem, 100%), 1fr))",
                    }}
                  >
                    <ModelCard
                      label={msg("model.generation.label")}
                      cfg={pickPairModelConfig(
                        job.generation_models,
                        activePair.generation_model,
                        activePair.generation_reasoning_effort,
                      )}
                    />
                    <ModelCard
                      label={TERMS.reflectionModel}
                      cfg={pickPairModelConfig(
                        job.reflection_models,
                        activePair.reflection_model,
                        activePair.reflection_reasoning_effort,
                      )}
                    />
                  </div>
                ) : job.generation_models && job.reflection_models ? (
                  <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
                    <div className="space-y-3">
                      <p className="flex items-center gap-2 text-[0.6875rem] font-semibold uppercase tracking-widest text-muted-foreground">
                        <span className="grid size-7 place-items-center rounded-lg bg-[#3D2E22] text-[#FAF8F5]">
                          <Cpu className="size-3.5" aria-hidden="true" />
                        </span>
                        <HelpTip text={tip("grid.generation_models")}>
                          {msg("model.generation.label_plural")}
                        </HelpTip>
                      </p>
                      {job.generation_models.map((m, i) => (
                        <ModelCard
                          key={i}
                          label={`${msg("model.generation.label_short")} ${i + 1}`}
                          cfg={m as unknown as Record<string, unknown>}
                        />
                      ))}
                    </div>
                    <div className="space-y-3">
                      <p className="flex items-center gap-2 text-[0.6875rem] font-semibold uppercase tracking-widest text-muted-foreground">
                        <span className="grid size-7 place-items-center rounded-lg bg-[#C8A882] text-[#3D2E22]">
                          <Brain className="size-3.5" aria-hidden="true" />
                        </span>
                        <HelpTip text={tip("grid.reflection_models")}>
                          {msg("auto.features.optimizations.components.configtab.7")}
                        </HelpTip>
                      </p>
                      {job.reflection_models.map((m, i) => (
                        <ModelCard
                          key={i}
                          label={formatMsg(
                            "auto.features.optimizations.components.configtab.template.4",
                            { p1: i + 1 },
                          )}
                          cfg={m as unknown as Record<string, unknown>}
                        />
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="py-12 text-center text-sm text-muted-foreground">—</p>
                )}
              </div>
            )}

            {activeSlide === 3 && (
              <div className="flex min-h-[24rem] flex-col gap-5">
                {job.source_dataset_id && (
                  <Link
                    href={`/datasets?open=${job.source_dataset_id}`}
                    className="group/srclink flex min-h-28 items-center gap-4 rounded-2xl border border-border/60 bg-[#F8F4EE] p-5 transition-[background-color,border-color,transform] hover:border-[#C8A882]/70 hover:bg-[#F4EEE6] active:scale-[0.995] sm:p-6"
                  >
                    <span className="grid size-14 shrink-0 place-items-center rounded-2xl bg-[#3D2E22] text-[#FAF8F5] shadow-sm">
                      <Books className="size-6" aria-hidden="true" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[0.6875rem] font-semibold uppercase tracking-widest text-muted-foreground">
                        {msg("optimizations.source_dataset.label")}
                      </span>
                      <span
                        className="mt-1 block truncate font-mono text-base font-semibold text-foreground sm:text-lg"
                        dir="ltr"
                      >
                        {job.source_dataset_id}
                      </span>
                    </span>
                    <span className="hidden shrink-0 text-xs font-semibold text-[#7C6350] sm:block">
                      {msg("optimizations.source_dataset.view")}
                    </span>
                    <ArrowUpRight className="size-4 shrink-0 text-muted-foreground/60 transition-colors group-hover/srclink:text-foreground" />
                  </Link>
                )}
                <MiniGrid rows={dataRows} />
                {columnMapping && <ColumnRoles mapping={columnMapping} order={columnOrder} />}
                <div className="flex flex-1 flex-col gap-3">
                  <div className="flex items-center gap-2.5">
                    <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-accent text-muted-foreground [&_svg]:size-4">
                      <Database className="size-4" aria-hidden="true" />
                    </span>
                    <p className="text-[0.6875rem] font-semibold uppercase tracking-widest text-muted-foreground">
                      <HelpTip text={tip("data.split_explanation")}>
                        {msg("auto.features.optimizations.components.configtab.9")}
                        {TERMS.dataset}
                      </HelpTip>
                    </p>
                  </div>
                  <SplitBar fractions={splitFractions} />
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <InfoCard
                    label={
                      <HelpTip text={tip("data.shuffle_explanation")}>
                        {msg("auto.features.optimizations.components.configtab.13")}
                      </HelpTip>
                    }
                    value={
                      shuffleVal
                        ? msg("auto.features.optimizations.components.configtab.literal.16")
                        : msg("auto.features.optimizations.components.configtab.literal.17")
                    }
                    icon={<Shuffle className="size-3.5" />}
                  />
                  <InfoCard
                    label={
                      <HelpTip text={tip("data.seed")}>
                        {msg("auto.features.optimizations.components.configtab.14")}
                      </HelpTip>
                    }
                    value={seedVal ?? null}
                    icon={<DiceFive className="size-3.5" />}
                  />
                </div>
              </div>
            )}
          </>
        )}
      />
    </>
  );
}
