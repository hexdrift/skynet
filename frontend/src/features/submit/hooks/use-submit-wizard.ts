"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { toast } from "react-toastify";

import {
  submitRun,
  submitGridSearch,
  validateCode,
  getOptimizationPayload,
  getJob,
  profileDataset,
} from "@/shared/lib/api";
import type {
  ModelConfig,
  ColumnMapping,
  SplitFractions,
  ValidateCodeResponse,
  ModelCatalogResponse,
  DatasetProfile,
  SplitPlan,
} from "@/shared/types/api";
import { parseDatasetFile, type ParsedDataset } from "@/features/submit/lib/parse-dataset";
import type { ValidationResult as EditorValidationResult } from "@/shared/ui/code-editor";
import { getModelCatalog, cachedCatalog } from "@/shared/lib/model-catalog";
import { registerTutorialHook } from "@/features/tutorial/lib/bridge";
import { msg } from "@/shared/lib/messages";
import { useWizardStateOptional } from "@/features/agent-panel/hooks/use-wizard-state";

import { STEPS, emptyModelConfig, defaultSplit, RECENT_KEY, MAX_RECENT } from "../constants";
import { buildSignatureTemplate } from "../lib/build-signature";
import { buildMetricTemplate } from "../lib/build-metric";
import { buildOptimizerKwargs } from "../lib/build-kwargs";
import { useCodeAgent } from "./use-code-agent";

export function useSubmitWizard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: session } = useSession();

  const [step, setStep] = useState(0);
  const [direction, setDirection] = useState(0);
  const [summaryTab, setSummaryTab] = useState(0);
  const [summaryCodeTab, setSummaryCodeTab] = useState<string>("signature");

  const [jobType, setOptimizationType] = useState<"run" | "grid_search">("run");

  // Username — always from the logged-in session
  const username = session?.user?.name ?? "";
  const [jobName, setJobName] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [moduleName, setModuleName] = useState("predict");
  const [optimizerName, setOptimizerName] = useState("gepa");

  const [signatureCode, setSignatureCode] = useState(() => buildSignatureTemplate({}));
  const [metricCode, setMetricCode] = useState(() => buildMetricTemplate({}));

  const [parsedDataset, setParsedDataset] = useState<ParsedDataset | null>(null);
  const [datasetFileName, setDatasetFileName] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [columnRoles, setColumnRoles] = useState<Record<string, "input" | "output" | "ignore">>({});
  const [signatureManuallyEdited, setSignatureManuallyEdited] = useState(false);
  const [metricManuallyEdited, setMetricManuallyEdited] = useState(false);
  const [codeAssistMode, setCodeAssistMode] = useState<"auto" | "manual">("auto");

  // Global provider settings (shared across all models)
  const [globalBaseUrl, setGlobalBaseUrl] = useState("");
  const [globalApiKey, setGlobalApiKey] = useState("");

  // Run model configs — primary + secondary (shared across optimizers)
  const [modelConfig, setModelConfig] = useState<ModelConfig>(emptyModelConfig());
  const [secondModelConfig, setSecondModelConfig] = useState<ModelConfig | null>(null);

  const [editingModel, setEditingModel] = useState<{
    config: ModelConfig;
    onSave: (c: ModelConfig) => void;
    label: string;
    onSelectAllAvailable?: () => void;
  } | null>(null);

  // Recent model configs — persisted in localStorage
  const [recentConfigs, setRecentConfigs] = useState<ModelConfig[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    } catch {
      return [];
    }
  });
  const saveToRecent = useCallback((config: ModelConfig) => {
    if (!config.name) return;
    setRecentConfigs((prev) => {
      const deduped = prev.filter((c) => c.name !== config.name);
      const next = [config, ...deduped].slice(0, MAX_RECENT);
      localStorage.setItem(RECENT_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  // Model catalog — prefetched on module load, instant here
  const [catalog, setCatalog] = useState<ModelCatalogResponse | null>(cachedCatalog);
  useEffect(() => {
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

  // Check if ANY provider has an env key configured on the backend
  const anyProviderHasEnvKey = catalog?.providers.some((p) => p.has_env_key) ?? false;

  const [generationModels, setGenerationModels] = useState<ModelConfig[]>([emptyModelConfig()]);
  const [reflectionModels, setReflectionModels] = useState<ModelConfig[]>([emptyModelConfig()]);
  const [useAllGenerationModels, setUseAllGenerationModels] = useState(false);
  const [useAllReflectionModels, setUseAllReflectionModels] = useState(false);

  const [split, setSplit] = useState<SplitFractions>(defaultSplit);

  // Dataset profile + recommended split plan (non-blocking; the user can always
  // override or ignore). A ref mirrors the manual-edit flag so the auto-profile
  // effect can read it without stale-closure re-runs.
  const [datasetProfile, setDatasetProfile] = useState<DatasetProfile | null>(null);
  const [splitPlan, setSplitPlan] = useState<SplitPlan | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [splitMode, setSplitModeState] = useState<"auto" | "manual">("auto");
  const splitModeRef = useRef<"auto" | "manual">("auto");
  const [seed, setSeed] = useState<number | undefined>(undefined);
  const [stratify, setStratify] = useState(false);
  const [stratifyColumn, setStratifyColumn] = useState<string | null>(null);

  // Code validation — each block is validated independently
  const [signatureValidation, setSignatureValidation] = useState<ValidateCodeResponse | null>(null);
  const [metricValidation, setMetricValidation] = useState<ValidateCodeResponse | null>(null);

  // Advanced — structured optimizer/compile kwargs
  const [autoLevel, setAutoLevel] = useState<string>("light");
  const [reflectionMinibatchSize, setReflectionMinibatchSize] = useState<string>("3");
  const [maxFullEvals, setMaxFullEvals] = useState<string>("6");
  const [useMerge, setUseMerge] = useState(true);
  const [shuffle, setShuffle] = useState(true);

  const [submitting, setSubmitting] = useState(false);
  const [submitPhase, setSubmitPhase] = useState<"idle" | "sending" | "splash" | "done">("idle");

  /* ── Clone pre-fill ── */
  const [cloneLoading, setCloneLoading] = useState(false);
  const cloneRan = useRef(false);

  // Register setters with the typed tutorial bridge so the tutorial system
  // can drive the wizard from plain-JS steps (see lib/tutorial-bridge.ts).
  useEffect(() => {
    const unregister = [
      registerTutorialHook("setWizardStep", setStep),
      registerTutorialHook("setParsedDataset", setParsedDataset),
      registerTutorialHook("setColumnRoles", setColumnRoles),
      registerTutorialHook("setDatasetFileName", setDatasetFileName),
      registerTutorialHook("setSignatureCode", setSignatureCode),
      registerTutorialHook("setMetricCode", setMetricCode),
      registerTutorialHook("setOptimizerName", setOptimizerName),
    ];
    return () => unregister.forEach((fn) => fn());
  }, []);

  /* ── Shared wizard-state bridge ──────────────────────────────────────────
   * The generalist agent writes wizard fields into WizardStateContext. We
   * mirror those agent writes into the local wizard state, and push local
   * edits back so the agent's phased-exposure gate sees them. Echo is
   * avoided by only pushing when the value actually differs from shared.
   */
  const wizardCtx = useWizardStateOptional();
  const { agentPulseTick, agentPulseKeys, sharedState } = {
    agentPulseTick: wizardCtx?.agentPulseTick ?? 0,
    agentPulseKeys: wizardCtx?.agentPulseKeys ?? [],
    sharedState: wizardCtx?.state,
  };

  // Incoming: apply agent patches to local state whenever the pulse bumps.
  useEffect(() => {
    if (!sharedState || agentPulseKeys.length === 0) return;
    for (const key of agentPulseKeys) {
      if (key === "job_name" && typeof sharedState.job_name === "string") {
        setJobName(sharedState.job_name);
      } else if (key === "job_description" && typeof sharedState.job_description === "string") {
        setJobDescription(sharedState.job_description);
      } else if (
        key === "job_type" &&
        (sharedState.job_type === "run" || sharedState.job_type === "grid_search")
      ) {
        setOptimizationType(sharedState.job_type);
      } else if (key === "optimizer_name" && typeof sharedState.optimizer_name === "string") {
        setOptimizerName(sharedState.optimizer_name);
      } else if (key === "module_name" && typeof sharedState.module_name === "string") {
        setModuleName(sharedState.module_name);
      } else if (key === "signature_code" && typeof sharedState.signature_code === "string") {
        setSignatureCode(sharedState.signature_code);
        setSignatureManuallyEdited(true);
        setSignatureValidation(null);
      } else if (key === "metric_code" && typeof sharedState.metric_code === "string") {
        setMetricCode(sharedState.metric_code);
        setMetricManuallyEdited(true);
        setMetricValidation(null);
      } else if (key === "column_roles" && sharedState.column_roles) {
        setColumnRoles((prev) => {
          const next = { ...prev };
          for (const [col, role] of Object.entries(sharedState.column_roles ?? {})) {
            if (role === "input" || role === "output" || role === "ignore") {
              next[col] = role;
            }
          }
          return next;
        });
      } else if (key === "model_config" && sharedState.model_config) {
        setModelConfig({ ...emptyModelConfig(), ...(sharedState.model_config as Partial<ModelConfig>) });
      } else if (key === "reflection_model_config" && sharedState.reflection_model_config) {
        setSecondModelConfig({
          ...emptyModelConfig(),
          ...(sharedState.reflection_model_config as Partial<ModelConfig>),
        });
      } else if (key === "generation_models" && Array.isArray(sharedState.generation_models)) {
        setGenerationModels(
          sharedState.generation_models.map((m) => ({
            ...emptyModelConfig(),
            ...(m as Partial<ModelConfig>),
          })),
        );
      } else if (key === "reflection_models" && Array.isArray(sharedState.reflection_models)) {
        setReflectionModels(
          sharedState.reflection_models.map((m) => ({
            ...emptyModelConfig(),
            ...(m as Partial<ModelConfig>),
          })),
        );
      } else if (
        key === "use_all_generation_models" &&
        typeof sharedState.use_all_generation_models === "boolean"
      ) {
        setUseAllGenerationModels(sharedState.use_all_generation_models);
      } else if (
        key === "use_all_reflection_models" &&
        typeof sharedState.use_all_reflection_models === "boolean"
      ) {
        setUseAllReflectionModels(sharedState.use_all_reflection_models);
      } else if (key === "split_fractions" && sharedState.split_fractions) {
        setSplit(sharedState.split_fractions);
      } else if (
        key === "split_mode" &&
        (sharedState.split_mode === "auto" || sharedState.split_mode === "manual")
      ) {
        splitModeRef.current = sharedState.split_mode;
        setSplitModeState(sharedState.split_mode);
      } else if (key === "seed" && typeof sharedState.seed === "number") {
        setSeed(sharedState.seed);
      } else if (key === "shuffle" && typeof sharedState.shuffle === "boolean") {
        setShuffle(sharedState.shuffle);
      } else if (key === "stratify" && typeof sharedState.stratify === "boolean") {
        setStratify(sharedState.stratify);
      } else if (key === "stratify_column" && typeof sharedState.stratify_column === "string") {
        setStratifyColumn(sharedState.stratify_column);
      } else if (key === "optimizer_kwargs" && sharedState.optimizer_kwargs) {
        const kw = sharedState.optimizer_kwargs as Record<string, unknown>;
        if (typeof kw.auto === "string") setAutoLevel(kw.auto);
        if (typeof kw.reflection_minibatch_size === "number") {
          setReflectionMinibatchSize(String(kw.reflection_minibatch_size));
        }
        if (typeof kw.max_full_evals === "number") {
          setMaxFullEvals(String(kw.max_full_evals));
        }
        if (typeof kw.use_merge === "boolean") setUseMerge(kw.use_merge);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentPulseTick]);

  // Outgoing: push relevant local state back into the shared context so the
  // agent's tool-gate (dataset_ready, columns_configured, model_configured)
  // reflects what the user actually has. Guarded by value equality to avoid
  // echo after incoming patches.
  useEffect(() => {
    if (!wizardCtx) return;
    const datasetReady = !!parsedDataset && parsedDataset.rowCount > 0;
    if (wizardCtx.state.dataset_ready !== datasetReady) {
      wizardCtx.setField("dataset_ready", datasetReady, "user");
    }
    const columns = parsedDataset?.columns ?? [];
    const shared = wizardCtx.state.dataset_columns;
    const changed = !shared || shared.length !== columns.length ||
      columns.some((c, i) => shared[i] !== c);
    if (changed && columns.length > 0) {
      wizardCtx.setField("dataset_columns", columns, "user");
    }
  }, [parsedDataset, wizardCtx]);

  useEffect(() => {
    if (!wizardCtx) return;
    if (wizardCtx.state.job_name !== jobName) {
      wizardCtx.setField("job_name", jobName, "user");
    }
  }, [jobName, wizardCtx]);

  useEffect(() => {
    if (!wizardCtx) return;
    if (wizardCtx.state.signature_code !== signatureCode) {
      wizardCtx.setField("signature_code", signatureCode, "user");
    }
  }, [signatureCode, wizardCtx]);

  useEffect(() => {
    if (!wizardCtx) return;
    if (wizardCtx.state.metric_code !== metricCode) {
      wizardCtx.setField("metric_code", metricCode, "user");
    }
  }, [metricCode, wizardCtx]);

  useEffect(() => {
    if (!wizardCtx) return;
    const inputs = Object.values(columnRoles).filter((r) => r === "input").length;
    const outputs = Object.values(columnRoles).filter((r) => r === "output").length;
    const configured = inputs > 0 && outputs > 0;
    if (wizardCtx.state.columns_configured !== configured) {
      wizardCtx.setField("columns_configured", configured, "user");
    }
    const shared = wizardCtx.state.column_roles ?? {};
    const sameShape =
      Object.keys(shared).length === Object.keys(columnRoles).length &&
      Object.entries(columnRoles).every(([c, r]) => shared[c] === r);
    if (!sameShape && Object.keys(columnRoles).length > 0) {
      wizardCtx.setField("column_roles", columnRoles, "user");
    }
  }, [columnRoles, wizardCtx]);

  useEffect(() => {
    if (!wizardCtx) return;
    const configured = !!modelConfig.name.trim();
    if (wizardCtx.state.model_configured !== configured) {
      wizardCtx.setField("model_configured", configured, "user");
    }
    wizardCtx.setField(
      "model_config",
      modelConfig as unknown as Record<string, unknown>,
      "user",
    );
  }, [modelConfig, wizardCtx]);

  // Outgoing: scalar wizard fields the agent can read back for decisions.
  useEffect(() => {
    if (!wizardCtx) return;
    const s = wizardCtx.state;
    if (s.job_description !== jobDescription) {
      wizardCtx.setField("job_description", jobDescription, "user");
    }
    if (s.job_type !== jobType) {
      wizardCtx.setField("job_type", jobType, "user");
    }
    if (s.optimizer_name !== optimizerName) {
      wizardCtx.setField("optimizer_name", optimizerName, "user");
    }
    if (s.module_name !== moduleName) {
      wizardCtx.setField("module_name", moduleName, "user");
    }
    if (s.use_all_generation_models !== useAllGenerationModels) {
      wizardCtx.setField("use_all_generation_models", useAllGenerationModels, "user");
    }
    if (s.use_all_reflection_models !== useAllReflectionModels) {
      wizardCtx.setField("use_all_reflection_models", useAllReflectionModels, "user");
    }
    if (s.split_mode !== splitMode) {
      wizardCtx.setField("split_mode", splitMode, "user");
    }
    if (s.seed !== seed) {
      wizardCtx.setField("seed", seed, "user");
    }
    if (s.shuffle !== shuffle) {
      wizardCtx.setField("shuffle", shuffle, "user");
    }
    if (s.stratify !== stratify) {
      wizardCtx.setField("stratify", stratify, "user");
    }
    const nextStratifyCol = stratifyColumn ?? undefined;
    if (s.stratify_column !== nextStratifyCol) {
      wizardCtx.setField("stratify_column", nextStratifyCol, "user");
    }
  }, [
    jobDescription,
    jobType,
    optimizerName,
    moduleName,
    useAllGenerationModels,
    useAllReflectionModels,
    splitMode,
    seed,
    shuffle,
    stratify,
    stratifyColumn,
    wizardCtx,
  ]);

  // Outgoing: split fractions (compared component-wise to avoid object echo).
  useEffect(() => {
    if (!wizardCtx) return;
    const shared = wizardCtx.state.split_fractions;
    if (
      !shared ||
      shared.train !== split.train ||
      shared.val !== split.val ||
      shared.test !== split.test
    ) {
      wizardCtx.setField("split_fractions", split, "user");
    }
  }, [split, wizardCtx]);

  // Outgoing: object/array fields — setField's internal ref-dedupe keeps these cheap.
  useEffect(() => {
    if (!wizardCtx) return;
    wizardCtx.setField(
      "reflection_model_config",
      (secondModelConfig ?? undefined) as Record<string, unknown> | undefined,
      "user",
    );
  }, [secondModelConfig, wizardCtx]);

  useEffect(() => {
    if (!wizardCtx) return;
    wizardCtx.setField(
      "generation_models",
      generationModels as unknown as Record<string, unknown>[],
      "user",
    );
  }, [generationModels, wizardCtx]);

  useEffect(() => {
    if (!wizardCtx) return;
    wizardCtx.setField(
      "reflection_models",
      reflectionModels as unknown as Record<string, unknown>[],
      "user",
    );
  }, [reflectionModels, wizardCtx]);

  // Outgoing: optimizer_kwargs — rebuild from the quartet and compare entries.
  useEffect(() => {
    if (!wizardCtx) return;
    const kw = buildOptimizerKwargs({
      autoLevel,
      maxFullEvals,
      reflectionMinibatchSize,
      useMerge,
    });
    const shared = wizardCtx.state.optimizer_kwargs ?? {};
    const kwEntries = Object.entries(kw);
    const same =
      Object.keys(shared).length === kwEntries.length &&
      kwEntries.every(([k, v]) => shared[k] === v);
    if (!same) {
      wizardCtx.setField("optimizer_kwargs", kw, "user");
    }
  }, [autoLevel, maxFullEvals, reflectionMinibatchSize, useMerge, wizardCtx]);

  // Agent-driven dataset staging: ``stage_sample_dataset`` returns a
  // ``dataset`` array alongside a ``wizard_state`` patch.
  // use-generalist-agent re-broadcasts the result on
  // ``wizard:dataset-staged``; we consume it here to populate the live
  // wizard dataset.
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (!detail) return;
      const rows = detail.dataset;
      const ws = detail.wizard_state;
      if (!Array.isArray(rows) || rows.length === 0) return;
      const columns =
        Array.isArray(ws?.dataset_columns) && ws.dataset_columns.length > 0
          ? (ws.dataset_columns as string[])
          : Object.keys(rows[0] ?? {});
      setParsedDataset({
        columns,
        rows: rows as Record<string, unknown>[],
        rowCount: rows.length,
      });
      const explicitFilename =
        typeof detail.dataset_filename === "string" && detail.dataset_filename
          ? detail.dataset_filename
          : null;
      const jobBasedFilename =
        typeof ws?.job_name === "string" && ws.job_name ? `${ws.job_name}.json` : null;
      setDatasetFileName(explicitFilename ?? jobBasedFilename ?? "sample.json");
      splitModeRef.current = "auto";
      setSplitModeState("auto");
      setDatasetProfile(null);
      setSplitPlan(null);
      setStratify(false);
      setStratifyColumn(null);
      setSignatureValidation(null);
      setMetricValidation(null);
    };
    window.addEventListener("wizard:dataset-staged", handler);
    return () => window.removeEventListener("wizard:dataset-staged", handler);
  }, []);

  // Auto-update signature template when column roles change
  useEffect(() => {
    if (signatureManuallyEdited) return;
    const hasRoles = Object.values(columnRoles).some((r) => r === "input" || r === "output");
    if (!hasRoles) return;
    setSignatureCode(buildSignatureTemplate(columnRoles));
  }, [columnRoles, signatureManuallyEdited]);

  // Auto-update metric template when output roles change. The agent
  // overwrites this in auto mode; the manual-edit flag protects a user's
  // edits from being clobbered when they toggle between columns afterwards.
  useEffect(() => {
    if (metricManuallyEdited) return;
    const hasOutputs = Object.values(columnRoles).some((r) => r === "output");
    if (!hasOutputs) return;
    setMetricCode(buildMetricTemplate(columnRoles));
  }, [columnRoles, metricManuallyEdited]);

  /* ── Clone pre-fill effect ── */
  useEffect(() => {
    const cloneId = searchParams.get("clone");
    if (!cloneId || cloneRan.current) return;
    cloneRan.current = true;
    setCloneLoading(true);
    // Fetch both payload and job display name in parallel
    Promise.all([getOptimizationPayload(cloneId), getJob(cloneId).catch(() => null)])
      .then(([{ optimization_type, payload }, jobData]) => {
              setOptimizationType(optimization_type === "grid_search" ? "grid_search" : "run");

        // Basic fields — prefer the current display name over the payload name
        const displayName = jobData?.name || payload.name;
        if (displayName) setJobName(String(displayName));
        if (payload.description) setJobDescription(String(payload.description));
        if (payload.module_name) setModuleName(String(payload.module_name));
        if (payload.optimizer_name) setOptimizerName(String(payload.optimizer_name));
        if (payload.signature_code) {
          setSignatureCode(String(payload.signature_code));
          setSignatureManuallyEdited(true);
        }
        if (payload.metric_code) {
          setMetricCode(String(payload.metric_code));
          setMetricManuallyEdited(true);
        }

              if (Array.isArray(payload.dataset) && payload.dataset.length > 0) {
          const rows = payload.dataset as Record<string, unknown>[];
          const columns = Object.keys(rows[0] ?? {});
          setParsedDataset({ columns, rows, rowCount: rows.length });
          setDatasetFileName(
            String(
              (payload as Record<string, unknown>).dataset_filename || displayName || cloneId || "",
            ),
          );
        }

              const cm = payload.column_mapping as
          | { inputs?: Record<string, string>; outputs?: Record<string, string> }
          | undefined;
        if (cm) {
          const roles: Record<string, "input" | "output" | "ignore"> = {};
          if (cm.inputs)
            Object.keys(cm.inputs).forEach((k) => {
              roles[k] = "input";
            });
          if (cm.outputs)
            Object.keys(cm.outputs).forEach((k) => {
              roles[k] = "output";
            });
          setColumnRoles(roles);
        }

              const sf = payload.split_fractions as
          | { train?: number; val?: number; test?: number }
          | undefined;
        if (sf) {
          setSplit({ train: sf.train ?? 0.7, val: sf.val ?? 0.15, test: sf.test ?? 0.15 });
          // Cloned splits are intentional — pin the wizard to manual so the
          // auto-profile effect doesn't clobber them when the dataset reloads.
          splitModeRef.current = "manual";
          setSplitModeState("manual");
        }

        if (payload.shuffle != null) setShuffle(Boolean(payload.shuffle));
        if (payload.stratify != null) setStratify(Boolean(payload.stratify));
        if (payload.stratify_column != null)
          setStratifyColumn(String(payload.stratify_column));
        if (payload.seed != null) setSeed(Number(payload.seed));

        const mc = payload.model_config as ModelConfig | undefined;
        if (mc) setModelConfig({ ...emptyModelConfig(), ...mc });

        const smc = (payload.reflection_model_config ??
          payload.task_model_config) as ModelConfig | undefined;
        if (smc?.name) setSecondModelConfig({ ...emptyModelConfig(), ...smc });

        const gm = payload.generation_models as ModelConfig[] | undefined;
        if (gm?.length) setGenerationModels(gm.map((m) => ({ ...emptyModelConfig(), ...m })));

        const rm = payload.reflection_models as ModelConfig[] | undefined;
        if (rm?.length) setReflectionModels(rm.map((m) => ({ ...emptyModelConfig(), ...m })));

        if (payload.use_all_available_generation_models) setUseAllGenerationModels(true);
        if (payload.use_all_available_reflection_models) setUseAllReflectionModels(true);

        const optKw = payload.optimizer_kwargs as Record<string, unknown> | undefined;
        if (optKw) {
          if (optKw.auto) setAutoLevel(String(optKw.auto));
          if (optKw.reflection_minibatch_size != null)
            setReflectionMinibatchSize(String(optKw.reflection_minibatch_size));
          if (optKw.max_full_evals != null) setMaxFullEvals(String(optKw.max_full_evals));
          if (optKw.use_merge != null) setUseMerge(Boolean(optKw.use_merge));
        }

        toast.success(msg("submit.clone.success"));
      })
      .catch(() => {
        toast.error(msg("submit.clone.failed"));
      })
      .finally(() => setCloneLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── Navigation ── */
  const goNext = () => {
    if (step < STEPS.length - 1) {
      setDirection(1);
      setStep((s) => s + 1);
    }
  };
  const goPrev = () => {
    if (step > 0) {
      setDirection(-1);
      setStep((s) => s - 1);
    }
  };
  const goTo = (idx: number) => {
    setDirection(idx > step ? 1 : -1);
    setStep(idx);
  };

  /* ── Build column mapping ── */
  const buildColumnMapping = (): ColumnMapping => {
    const inputs: Record<string, string> = {};
    const outputs: Record<string, string> = {};
    Object.entries(columnRoles).forEach(([col, role]) => {
      if (role === "input") inputs[col] = col;
      else if (role === "output") outputs[col] = col;
    });
    return { inputs, outputs };
  };

  /* ── Auto-profile: fetch a recommended split whenever the dataset or
   * column mapping changes. Debounced so rapid role edits don't spam the
   * endpoint. Auto-applies the plan to split/shuffle/seed only when the
   * user hasn't taken manual control of the split yet — the "החל המלצה"
   * button in ParamsStep re-applies it on demand. Failures are swallowed;
   * the existing manual controls remain usable. */
  useEffect(() => {
    if (!parsedDataset || parsedDataset.rowCount === 0) return;
    const mapping: ColumnMapping = { inputs: {}, outputs: {} };
    Object.entries(columnRoles).forEach(([col, role]) => {
      if (role === "input") mapping.inputs[col] = col;
      else if (role === "output") mapping.outputs[col] = col;
    });
    if (Object.keys(mapping.inputs).length === 0) return;
    let cancelled = false;
    const handle = setTimeout(() => {
      setProfileLoading(true);
      profileDataset({
        dataset: parsedDataset.rows as Record<string, unknown>[],
        column_mapping: mapping,
      })
        .then((response) => {
          if (cancelled) return;
          setDatasetProfile(response.profile);
          setSplitPlan(response.plan);
          if (splitModeRef.current === "auto") {
            setSplit(response.plan.fractions);
            setShuffle(response.plan.shuffle);
            setSeed(response.plan.seed);
            setStratify(response.plan.stratify);
            setStratifyColumn(response.plan.stratify_column);
          }
        })
        .catch(() => {
          /* non-blocking: manual controls still work */
        })
        .finally(() => {
          if (!cancelled) setProfileLoading(false);
        });
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [parsedDataset, columnRoles]);

  const setSplitMode = useCallback(
    (mode: "auto" | "manual") => {
      splitModeRef.current = mode;
      setSplitModeState(mode);
      if (mode === "auto" && splitPlan) {
        setSplit(splitPlan.fractions);
        setShuffle(splitPlan.shuffle);
        setSeed(splitPlan.seed);
        setStratify(splitPlan.stratify);
        setStratifyColumn(splitPlan.stratify_column);
      }
    },
    [splitPlan],
  );

  /* ── Step validation (optionally shows toast errors) ── */
  const validateStep = (s: number, showToast = false): boolean => {
    switch (s) {
      case 0:
        if (!username.trim()) {
          if (showToast) toast.error(msg("submit.validation.username_required"));
          return false;
        }
        if (!jobName.trim()) {
          if (showToast) toast.error(msg("submit.validation.name_required"));
          return false;
        }
        return true;
      case 1: {
        if (!parsedDataset || parsedDataset.rowCount === 0) {
          if (showToast) toast.error(msg("submit.validation.dataset_required"));
          return false;
        }
        const m = buildColumnMapping();
        if (Object.keys(m.inputs).length === 0) {
          if (showToast) toast.error(msg("submit.validation.input_column_required"));
          return false;
        }
        if (Object.keys(m.outputs).length === 0) {
          if (showToast) toast.error(msg("submit.validation.output_column_required"));
          return false;
        }
        return true;
      }
      case 2:
        return true;
      case 3:
        if (!signatureCode.trim()) {
          if (showToast) toast.error(msg("submit.validation.signature_required"));
          return false;
        }
        if (!metricCode.trim()) {
          if (showToast) toast.error(msg("submit.validation.metric_required"));
          return false;
        }
        if (signatureValidation && signatureValidation.errors.length > 0) {
          return false;
        }
        if (metricValidation && metricValidation.errors.length > 0) {
          return false;
        }
        return true;
      case 4:
        if (jobType === "run") {
          if (!modelConfig.name.trim()) {
            if (showToast) toast.error(msg("submit.validation.model_required"));
            return false;
          }
          // Require api_key if provider has no env default AND no global key
          const hasApiKey = !!globalApiKey || !!modelConfig.extra?.api_key;
          if (!anyProviderHasEnvKey && !hasApiKey) {
            if (showToast) toast.error(msg("submit.validation.api_key_required"));
            return false;
          }
          const secondModel = secondModelConfig;
          if (!secondModel?.name?.trim()) {
            if (showToast) toast.error(msg("submit.validation.reflection_model_required"));
            return false;
          }
        }
        if (jobType === "grid_search") {
          if (!useAllGenerationModels && generationModels.every((m) => !m.name.trim())) {
            if (showToast) toast.error(msg("submit.validation.generation_model_required"));
            return false;
          }
          if (!useAllReflectionModels && reflectionModels.every((m) => !m.name.trim())) {
            if (showToast) toast.error(msg("submit.validation.reflection_models_required"));
            return false;
          }
          if (
            (useAllGenerationModels || useAllReflectionModels) &&
            (catalog?.models.length ?? 0) === 0
          ) {
            if (showToast) toast.error(msg("submit.validation.no_models_available"));
            return false;
          }
        }
        return true;
      default:
        return true;
    }
  };

  /* ── Highest reachable step (all prior steps must be valid) ── */
  const maxReachableStep = (() => {
    for (let i = 0; i < STEPS.length; i++) {
      if (!validateStep(i)) return i;
    }
    return STEPS.length - 1;
  })();

  /* ── Code validation ── */
  const validateBlock = async (
    kind: "signature" | "metric",
    overrideCode?: string,
  ): Promise<ValidateCodeResponse | EditorValidationResult> => {
    const code = overrideCode ?? (kind === "signature" ? signatureCode : metricCode);
    if (!code.trim()) {
      return { valid: false, errors: [`Missing ${kind} code`], warnings: [] };
    }
    if (!parsedDataset || parsedDataset.rowCount === 0) {
      return { valid: false, errors: ["Upload a dataset before validating code"], warnings: [] };
    }
    const mapping = buildColumnMapping();
    const sampleRow = parsedDataset.rows[0] as Record<string, unknown>;
    return validateCode({
      signature_code: kind === "signature" ? code : undefined,
      metric_code: kind === "metric" ? code : undefined,
      column_mapping: mapping,
      sample_row: sampleRow,
      optimizer_name: optimizerName,
    });
  };

  const runSignatureValidation = async (
    overrideCode?: string,
  ): Promise<EditorValidationResult | null> => {
    try {
      const result = await validateBlock("signature", overrideCode);
      setSignatureValidation(result as ValidateCodeResponse);
      return result;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Signature validation failed";
      return { valid: false, errors: [msg], warnings: [] };
    }
  };

  const runMetricValidation = async (
    overrideCode?: string,
  ): Promise<EditorValidationResult | null> => {
    try {
      const result = await validateBlock("metric", overrideCode);
      setMetricValidation(result as ValidateCodeResponse);
      return result;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Metric validation failed";
      return { valid: false, errors: [msg], warnings: [] };
    }
  };

  const handleValidateCode = async (): Promise<boolean> => {
    if (!parsedDataset || parsedDataset.rowCount === 0) {
      toast.error(msg("submit.validation.dataset_before_code"));
      return false;
    }
    try {
      const [sigRes, metRes] = await Promise.all([
        signatureCode.trim() ? runSignatureValidation() : Promise.resolve(null),
        metricCode.trim() ? runMetricValidation() : Promise.resolve(null),
      ]);
      const sigOk = !sigRes || sigRes.errors.length === 0;
      const metOk = !metRes || metRes.errors.length === 0;
      if (sigOk && metOk) return true;
      toast.error(msg("submit.validation.code_has_errors"));
      return false;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("submit.code_validation_failed"));
      return false;
    }
  };

  const handleNext = async () => {
    // Auto-trigger code validation when leaving the code step (step 3)
    if (step === 3 && signatureCode.trim() && metricCode.trim() && parsedDataset) {
      // Run validation — triggers the inline error UI in the CodeEditors
      const passed = await handleValidateCode();
      if (!passed) return;
    }
    if (validateStep(step, true)) goNext();
  };

  const handleTabClick = (idx: number) => {
    if (idx <= step) {
      goTo(idx);
      return;
    } // going back is always allowed
    if (idx <= maxReachableStep) {
      goTo(idx);
      return;
    } // all prior steps valid
    // try to validate current step and show error
    validateStep(step, true);
  };

  /* ── File upload handler ── */
  const handleFileUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const parsed = await parseDatasetFile(file);
      setParsedDataset(parsed);
      setDatasetFileName(file.name);
      const roles: Record<string, "input" | "output" | "ignore"> = {};
      parsed.columns.forEach((col) => {
        roles[col] = "input";
      });
      setColumnRoles(roles);
      // A fresh dataset deserves a fresh recommendation — reset to auto mode
      // so the auto-profile effect can apply the new plan.
      splitModeRef.current = "auto";
      setSplitModeState("auto");
      setDatasetProfile(null);
      setSplitPlan(null);
      setStratify(false);
      setStratifyColumn(null);
      // A new dataset invalidates any cloned or user-authored code — clear
      // the manual-edit flags so the template effects and the code agent
      // can repopulate for the new schema.
      setSignatureManuallyEdited(false);
      setMetricManuallyEdited(false);
      setSignatureValidation(null);
      setMetricValidation(null);
      toast.success(`נטען ${parsed.rowCount} שורות מ-${file.name}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("submit.dataset.file_error"));
    }
  }, []);

  /* ── Split fraction handler ── */
  const updateSplit = (field: keyof SplitFractions, value: string) => {
    if (splitModeRef.current === "auto") return;
    const num = parseFloat(value);
    if (isNaN(num) || num < 0 || num > 1) return;
    setSplit((prev) => ({ ...prev, [field]: num }));
  };
  const splitSum = +(split.train + split.val + split.test).toFixed(4);

  /* ── Submit ── */
  const handleSubmit = async () => {
    if (!username.trim()) {
      toast.error(msg("submit.validation.username_required"));
      goTo(0);
      return;
    }
    if (!parsedDataset || parsedDataset.rowCount === 0) {
      toast.error(msg("submit.validation.dataset_required_short"));
      goTo(1);
      return;
    }
    if (!signatureCode.trim()) {
      toast.error(msg("submit.validation.signature_required"));
      goTo(3);
      return;
    }
    if (!metricCode.trim()) {
      toast.error(msg("submit.validation.metric_required"));
      goTo(3);
      return;
    }

    const columnMapping = buildColumnMapping();
    if (Object.keys(columnMapping.inputs).length === 0) {
      toast.error(msg("submit.validation.input_column_required"));
      goTo(1);
      return;
    }
    if (Object.keys(columnMapping.outputs).length === 0) {
      toast.error(msg("submit.validation.output_column_required"));
      goTo(1);
      return;
    }

    setSubmitting(true);
    setSubmitPhase("sending");
    try {
      const optKw = buildOptimizerKwargs({
        autoLevel,
        maxFullEvals,
        reflectionMinibatchSize,
        useMerge,
      });
      const base = {
        name: jobName.trim() || undefined,
        description: jobDescription.trim() || undefined,
        username: username.trim(),
        module_name: moduleName,
        signature_code: signatureCode,
        metric_code: metricCode,
        optimizer_name: optimizerName,
        dataset: parsedDataset.rows as Record<string, unknown>[],
        dataset_filename: datasetFileName || undefined,
        column_mapping: columnMapping,
        split_fractions: split,
        shuffle,
        stratify,
        ...(stratify && stratifyColumn ? { stratify_column: stratifyColumn } : {}),
        ...(seed != null && { seed }),
        ...(Object.keys(optKw).length > 0 && { optimizer_kwargs: optKw }),
      };

      // Inject global API key + base URL into any model config that doesn't override
      const applyGlobals = (mc: ModelConfig): ModelConfig => {
        const out = { ...mc };
        if (globalBaseUrl && !out.base_url) out.base_url = globalBaseUrl;
        if (globalApiKey && !out.extra?.api_key)
          out.extra = { ...out.extra, api_key: globalApiKey };
        return out;
      };

      let result;
      if (jobType === "run") {
        if (!modelConfig.name.trim()) {
          toast.error(msg("submit.validation.model_required"));
          goTo(4);
          setSubmitting(false);
          setSubmitPhase("idle");
          return;
        }
        const secondApplied = secondModelConfig?.name?.trim()
          ? applyGlobals(secondModelConfig)
          : undefined;
        const runPayload = {
          ...base,
          model_config: applyGlobals(modelConfig),
          ...(secondApplied ? { reflection_model_config: secondApplied } : {}),
        } as Parameters<typeof submitRun>[0];
        result = await submitRun(runPayload);
      } else {
        const validGen = generationModels.filter((m) => m.name.trim()).map(applyGlobals);
        const validRef = reflectionModels.filter((m) => m.name.trim()).map(applyGlobals);
        if (!useAllGenerationModels && validGen.length === 0) {
          toast.error(msg("submit.validation.generation_model_required"));
          goTo(4);
          setSubmitting(false);
          setSubmitPhase("idle");
          return;
        }
        if (!useAllReflectionModels && validRef.length === 0) {
          toast.error(msg("submit.validation.reflection_models_required"));
          goTo(4);
          setSubmitting(false);
          setSubmitPhase("idle");
          return;
        }
        if (
          (useAllGenerationModels || useAllReflectionModels) &&
          (catalog?.models.length ?? 0) === 0
        ) {
          toast.error(msg("submit.validation.no_models_available"));
          goTo(4);
          setSubmitting(false);
          setSubmitPhase("idle");
          return;
        }
        result = await submitGridSearch({
          ...base,
          generation_models: useAllGenerationModels ? [] : validGen,
          reflection_models: useAllReflectionModels ? [] : validRef,
          ...(useAllGenerationModels && { use_all_available_generation_models: true }),
          ...(useAllReflectionModels && { use_all_available_reflection_models: true }),
        });
      }

      // Show splash transition, then navigate
      const jobUrl = `/optimizations/${result.optimization_id}`;
      setSubmitPhase("splash");
      // Collapse sidebar before navigating so the job page opens with full width
      window.dispatchEvent(new Event("sidebar:collapse"));
      setTimeout(() => {
        setSubmitPhase("done");
        router.push(jobUrl);
      }, 1500);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("submit.submit_failed"));
      setSubmitPhase("idle");
      setSubmitting(false);
    }
  };

  const clearRecentConfigs = () => {
    setRecentConfigs([]);
    localStorage.removeItem(RECENT_KEY);
  };

  // Hoisted to wizard scope so the seed pass fires as soon as the user
  // has a dataset + I/O roles — by the time they reach the code step,
  // the Signature + metric are already filled (or streaming in).
  const agent = useCodeAgent({
    codeAssistMode,
    setCodeAssistMode,
    columnRoles,
    parsedDataset,
    moduleName,
    signatureCode,
    metricCode,
    setSignatureCode,
    setMetricCode,
    signatureManuallyEdited,
    metricManuallyEdited,
    setSignatureManuallyEdited,
    setMetricManuallyEdited,
    setSignatureValidation,
    setMetricValidation,
    signatureValidation,
    metricValidation,
    runSignatureValidation,
    runMetricValidation,
  });

  return {
    step,
    setStep,
    direction,
    setDirection,
    summaryTab,
    setSummaryTab,
    summaryCodeTab,
    setSummaryCodeTab,
    goNext,
    goPrev,
    goTo,
    maxReachableStep,
    validateStep,
    handleNext,
    handleTabClick,
    jobType,
    setOptimizationType,
    username,
    jobName,
    setJobName,
    jobDescription,
    setJobDescription,
    moduleName,
    setModuleName,
    optimizerName,
    setOptimizerName,
    signatureCode,
    setSignatureCode,
    setSignatureManuallyEdited,
    metricCode,
    setMetricCode,
    setMetricManuallyEdited,
    codeAssistMode,
    setCodeAssistMode,
    signatureValidation,
    setSignatureValidation,
    metricValidation,
    setMetricValidation,
    runSignatureValidation,
    runMetricValidation,
      parsedDataset,
    setParsedDataset,
    datasetFileName,
    setDatasetFileName,
    fileInputRef,
    handleFileUpload,
      columnRoles,
    setColumnRoles,
    globalBaseUrl,
    setGlobalBaseUrl,
    globalApiKey,
    setGlobalApiKey,
    anyProviderHasEnvKey,
    modelConfig,
    setModelConfig,
    secondModelConfig,
    setSecondModelConfig,
    editingModel,
    setEditingModel,
    recentConfigs,
    saveToRecent,
    clearRecentConfigs,
    catalog,
    generationModels,
    setGenerationModels,
    reflectionModels,
    setReflectionModels,
    useAllGenerationModels,
    setUseAllGenerationModels,
    useAllReflectionModels,
    setUseAllReflectionModels,
    split,
    updateSplit,
    splitSum,
    datasetProfile,
    splitPlan,
    profileLoading,
    splitMode,
    setSplitMode,
    seed,
    shuffle,
    setShuffle,
    autoLevel,
    setAutoLevel,
    reflectionMinibatchSize,
    setReflectionMinibatchSize,
    maxFullEvals,
    setMaxFullEvals,
    useMerge,
    setUseMerge,
    submitting,
    submitPhase,
    handleSubmit,
    cloneLoading,
    agent,
  };
}

export type SubmitWizardContext = ReturnType<typeof useSubmitWizard>;
