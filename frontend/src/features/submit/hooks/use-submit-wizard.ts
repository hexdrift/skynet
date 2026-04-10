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
} from "@/lib/api";
import type {
  ModelConfig,
  ColumnMapping,
  SplitFractions,
  ValidateCodeResponse,
  ModelCatalogResponse,
} from "@/lib/types";
import { parseDatasetFile, type ParsedDataset } from "@/lib/parse-dataset";
import type { ValidationResult as EditorValidationResult } from "@/components/code-editor";
import { getModelCatalog, cachedCatalog } from "@/lib/model-catalog";
import { registerTutorialHook } from "@/lib/tutorial-bridge";
import { msg } from "@/features/shared/messages";

import {
  STEPS,
  emptyModelConfig,
  defaultSplit,
  RECENT_KEY,
  MAX_RECENT,
} from "../constants";
import { buildSignatureTemplate } from "../lib/build-signature";
import { buildOptimizerKwargs, buildCompileKwargs } from "../lib/build-kwargs";
import {
  METRIC_TEMPLATE_MIPRO,
  METRIC_TEMPLATE_GEPA,
  isMetricTemplate,
} from "../lib/metric-templates";

export function useSubmitWizard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: session } = useSession();

  // Wizard state
  const [step, setStep] = useState(0);
  const [direction, setDirection] = useState(0);
  const [summaryTab, setSummaryTab] = useState(0);
  const [summaryCodeTab, setSummaryCodeTab] = useState<string>("signature");

  // Job type
  const [jobType, setOptimizationType] = useState<"run" | "grid_search">("run");

  // Username — always from the logged-in session
  const username = session?.user?.name ?? "";
  const [jobName, setJobName] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [moduleName, setModuleName] = useState("predict");
  const [optimizerName, setOptimizerName] = useState("miprov2");

  const [signatureCode, setSignatureCode] = useState(() => buildSignatureTemplate({}));
  const [metricCode, setMetricCode] = useState(METRIC_TEMPLATE_MIPRO);
  const metricIsTemplate = isMetricTemplate(metricCode);

  // Dataset
  const [parsedDataset, setParsedDataset] = useState<ParsedDataset | null>(null);
  const [datasetFileName, setDatasetFileName] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Column mapping
  const [columnRoles, setColumnRoles] = useState<Record<string, "input" | "output" | "ignore">>({});
  const [signatureManuallyEdited, setSignatureManuallyEdited] = useState(false);

  // Global provider settings (shared across all models)
  const [globalBaseUrl, setGlobalBaseUrl] = useState("");
  const [globalApiKey, setGlobalApiKey] = useState("");

  // Run model configs — primary + secondary (shared across optimizers)
  const [modelConfig, setModelConfig] = useState<ModelConfig>(emptyModelConfig());
  const [secondModelConfig, setSecondModelConfig] = useState<ModelConfig | null>(null);

  // Model config modal state
  const [editingModel, setEditingModel] = useState<{
    config: ModelConfig;
    onSave: (c: ModelConfig) => void;
    label: string;
  } | null>(null);

  // Recent model configs — persisted in localStorage
  const [recentConfigs, setRecentConfigs] = useState<ModelConfig[]>(() => {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch { return []; }
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
    getModelCatalog().then((c) => { if (!cancelled) setCatalog(c); }).catch(() => {});
    return () => { cancelled = true; };
  }, [catalog]);

  // Check if ANY provider has an env key configured on the backend
  const anyProviderHasEnvKey = catalog?.providers.some((p) => p.has_env_key) ?? false;

  // Grid search model lists
  const [generationModels, setGenerationModels] = useState<ModelConfig[]>([emptyModelConfig()]);
  const [reflectionModels, setReflectionModels] = useState<ModelConfig[]>([emptyModelConfig()]);

  // Split fractions
  const [split, setSplit] = useState<SplitFractions>(defaultSplit);

  // Code validation — each block is validated independently
  const [signatureValidation, setSignatureValidation] = useState<ValidateCodeResponse | null>(null);
  const [metricValidation, setMetricValidation] = useState<ValidateCodeResponse | null>(null);

  // Advanced — structured optimizer/compile kwargs
  const [autoLevel, setAutoLevel] = useState<string>("light");
  const [maxBootstrappedDemos, setMaxBootstrappedDemos] = useState<string>("4");
  const [maxLabeledDemos, setMaxLabeledDemos] = useState<string>("4");
  const [numTrials, setNumTrials] = useState<string>("10");
  const [minibatch, setMinibatch] = useState(true);
  const [minibatchSize, setMinibatchSize] = useState<string>("35");
  // GEPA-specific
  const [reflectionMinibatchSize, setReflectionMinibatchSize] = useState<string>("3");
  const [maxFullEvals, setMaxFullEvals] = useState<string>("6");
  const [useMerge, setUseMerge] = useState(true);
  const [shuffle, setShuffle] = useState(true);

  // Submission state
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

  // Swap metric template when optimizer changes (only if user hasn't edited it)
  useEffect(() => {
    if (metricIsTemplate) {
      setMetricCode(optimizerName === "gepa" ? METRIC_TEMPLATE_GEPA : METRIC_TEMPLATE_MIPRO);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optimizerName]);

  // Auto-update signature template when column roles change
  useEffect(() => {
    if (signatureManuallyEdited) return;
    const hasRoles = Object.values(columnRoles).some((r) => r === "input" || r === "output");
    if (!hasRoles) return;
    setSignatureCode(buildSignatureTemplate(columnRoles));
  }, [columnRoles, signatureManuallyEdited]);

  /* ── Clone pre-fill effect ── */
  useEffect(() => {
    const cloneId = searchParams.get("clone");
    if (!cloneId || cloneRan.current) return;
    cloneRan.current = true;
    setCloneLoading(true);
    // Fetch both payload and job display name in parallel
    Promise.all([getOptimizationPayload(cloneId), getJob(cloneId).catch(() => null)])
      .then(([{ optimization_type, payload }, jobData]) => {
        // Job type
        setOptimizationType(optimization_type === "grid_search" ? "grid_search" : "run");

        // Basic fields — prefer the current display name over the payload name
        const displayName = jobData?.name || payload.name;
        if (displayName) setJobName(String(displayName));
        if (payload.description) setJobDescription(String(payload.description));
        if (payload.module_name) setModuleName(String(payload.module_name));
        if (payload.optimizer_name) setOptimizerName(String(payload.optimizer_name));
        if (payload.signature_code) { setSignatureCode(String(payload.signature_code)); setSignatureManuallyEdited(true); }
        if (payload.metric_code) setMetricCode(String(payload.metric_code));

        // Dataset
        if (Array.isArray(payload.dataset) && payload.dataset.length > 0) {
          const rows = payload.dataset as Record<string, unknown>[];
          const columns = Object.keys(rows[0] ?? {});
          setParsedDataset({ columns, rows, rowCount: rows.length });
          setDatasetFileName(String((payload as Record<string, unknown>).dataset_filename || displayName || cloneId || ""));
        }

        // Column mapping
        const cm = payload.column_mapping as { inputs?: Record<string, string>; outputs?: Record<string, string> } | undefined;
        if (cm) {
          const roles: Record<string, "input" | "output" | "ignore"> = {};
          if (cm.inputs) Object.keys(cm.inputs).forEach((k) => { roles[k] = "input"; });
          if (cm.outputs) Object.keys(cm.outputs).forEach((k) => { roles[k] = "output"; });
          setColumnRoles(roles);
        }

        // Split fractions
        const sf = payload.split_fractions as { train?: number; val?: number; test?: number } | undefined;
        if (sf) setSplit({ train: sf.train ?? 0.7, val: sf.val ?? 0.15, test: sf.test ?? 0.15 });

        if (payload.shuffle != null) setShuffle(Boolean(payload.shuffle));

        // Model config (run type)
        const mc = payload.model_config as ModelConfig | undefined;
        if (mc) setModelConfig({ ...emptyModelConfig(), ...mc });

        const smc = (payload.reflection_model_config ?? payload.task_model_config ?? payload.prompt_model_config) as ModelConfig | undefined;
        if (smc?.name) setSecondModelConfig({ ...emptyModelConfig(), ...smc });

        // Grid search models
        const gm = payload.generation_models as ModelConfig[] | undefined;
        if (gm?.length) setGenerationModels(gm.map((m) => ({ ...emptyModelConfig(), ...m })));

        const rm = payload.reflection_models as ModelConfig[] | undefined;
        if (rm?.length) setReflectionModels(rm.map((m) => ({ ...emptyModelConfig(), ...m })));

        // Optimizer / compile kwargs
        const optKw = payload.optimizer_kwargs as Record<string, unknown> | undefined;
        if (optKw) {
          if (optKw.auto) setAutoLevel(String(optKw.auto));
          if (optKw.max_bootstrapped_demos != null) setMaxBootstrappedDemos(String(optKw.max_bootstrapped_demos));
          if (optKw.max_labeled_demos != null) setMaxLabeledDemos(String(optKw.max_labeled_demos));
          if (optKw.reflection_minibatch_size != null) setReflectionMinibatchSize(String(optKw.reflection_minibatch_size));
          if (optKw.max_full_evals != null) setMaxFullEvals(String(optKw.max_full_evals));
          if (optKw.use_merge != null) setUseMerge(Boolean(optKw.use_merge));
        }
        const compKw = payload.compile_kwargs as Record<string, unknown> | undefined;
        if (compKw) {
          if (compKw.num_trials != null) setNumTrials(String(compKw.num_trials));
          if (compKw.minibatch != null) setMinibatch(Boolean(compKw.minibatch));
          if (compKw.minibatch_size != null) setMinibatchSize(String(compKw.minibatch_size));
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

  /* ── Step validation (optionally shows toast errors) ── */
  const validateStep = (s: number, showToast = false): boolean => {
    switch (s) {
      case 0:
        if (!username.trim()) { if (showToast) toast.error(msg("submit.validation.username_required")); return false; }
        if (!jobName.trim()) { if (showToast) toast.error(msg("submit.validation.name_required")); return false; }
        return true;
      case 1: {
        if (!parsedDataset || parsedDataset.rowCount === 0) { if (showToast) toast.error(msg("submit.validation.dataset_required")); return false; }
        const m = buildColumnMapping();
        if (Object.keys(m.inputs).length === 0) { if (showToast) toast.error(msg("submit.validation.input_column_required")); return false; }
        if (Object.keys(m.outputs).length === 0) { if (showToast) toast.error(msg("submit.validation.output_column_required")); return false; }
        return true;
      }
      case 2:
        if (jobType === "run") {
          if (!modelConfig.name.trim()) { if (showToast) toast.error(msg("submit.validation.model_required")); return false; }
          // Require api_key if provider has no env default AND no global key
          const hasApiKey = !!globalApiKey || !!(modelConfig.extra?.api_key);
          if (!anyProviderHasEnvKey && !hasApiKey) {
            if (showToast) toast.error(msg("submit.validation.api_key_required"));
            return false;
          }
          const secondModel = secondModelConfig;
          if (!secondModel?.name?.trim()) { if (showToast) toast.error(msg("submit.validation.reflection_model_required")); return false; }
        }
        if (jobType === "grid_search") {
          if (generationModels.every((m) => !m.name.trim())) { if (showToast) toast.error(msg("submit.validation.generation_model_required")); return false; }
          if (reflectionModels.every((m) => !m.name.trim())) { if (showToast) toast.error(msg("submit.validation.reflection_models_required")); return false; }
        }
        return true;
      case 3:
        if (!signatureCode.trim()) { if (showToast) toast.error(msg("submit.validation.signature_required")); return false; }
        if (!metricCode.trim()) { if (showToast) toast.error(msg("submit.validation.metric_required")); return false; }
        // Block progress if any validation ran and found errors
        if (signatureValidation && signatureValidation.errors.length > 0) { return false; }
        if (metricValidation && metricValidation.errors.length > 0) { return false; }
        return true;
      default: return true;
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
  ): Promise<ValidateCodeResponse | EditorValidationResult> => {
    const code = kind === "signature" ? signatureCode : metricCode;
    if (!code.trim()) {
      return { valid: false, errors: [`Missing ${kind} code`], warnings: [] };
    }
    if (!parsedDataset || parsedDataset.rowCount === 0) {
      return { valid: false, errors: ["Upload a dataset before validating code"], warnings: [] };
    }
    const mapping = buildColumnMapping();
    const sampleRow = parsedDataset.rows[0] as Record<string, unknown>;
    return validateCode({
      signature_code: kind === "signature" ? signatureCode : undefined,
      metric_code: kind === "metric" ? metricCode : undefined,
      column_mapping: mapping,
      sample_row: sampleRow,
      optimizer_name: optimizerName,
    });
  };

  const runSignatureValidation = async (): Promise<EditorValidationResult | null> => {
    try {
      const result = await validateBlock("signature");
      setSignatureValidation(result as ValidateCodeResponse);
      return result;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Signature validation failed";
      return { valid: false, errors: [msg], warnings: [] };
    }
  };

  const runMetricValidation = async (): Promise<EditorValidationResult | null> => {
    try {
      const result = await validateBlock("metric");
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
    // Auto-trigger code validation when leaving the code step (now step 3)
    if (step === 3 && signatureCode.trim() && metricCode.trim() && parsedDataset) {
      // Run validation — triggers the inline error UI in the CodeEditors
      const passed = await handleValidateCode();
      if (!passed) return;
    }
    if (validateStep(step, true)) goNext();
  };

  const handleTabClick = (idx: number) => {
    if (idx <= step) { goTo(idx); return; } // going back is always allowed
    if (idx <= maxReachableStep) { goTo(idx); return; } // all prior steps valid
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
      parsed.columns.forEach((col) => { roles[col] = "input"; });
      setColumnRoles(roles);
      toast.success(`נטען ${parsed.rowCount} שורות מ-${file.name}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : msg("submit.dataset.file_error"));
    }
  }, []);

  /* ── Split fraction handler ── */
  const updateSplit = (field: keyof SplitFractions, value: string) => {
    const num = parseFloat(value);
    if (isNaN(num) || num < 0 || num > 1) return;
    setSplit((prev) => ({ ...prev, [field]: num }));
  };
  const splitSum = +(split.train + split.val + split.test).toFixed(4);

  /* ── Submit ── */
  const handleSubmit = async () => {
    if (!username.trim()) { toast.error(msg("submit.validation.username_required")); goTo(0); return; }
    if (!parsedDataset || parsedDataset.rowCount === 0) { toast.error(msg("submit.validation.dataset_required_short")); goTo(1); return; }
    if (!signatureCode.trim()) { toast.error(msg("submit.validation.signature_required")); goTo(3); return; }
    if (!metricCode.trim()) { toast.error(msg("submit.validation.metric_required")); goTo(3); return; }

    const columnMapping = buildColumnMapping();
    if (Object.keys(columnMapping.inputs).length === 0) { toast.error(msg("submit.validation.input_column_required")); goTo(1); return; }
    if (Object.keys(columnMapping.outputs).length === 0) { toast.error(msg("submit.validation.output_column_required")); goTo(1); return; }

    setSubmitting(true);
    setSubmitPhase("sending");
    try {
      const optKw = buildOptimizerKwargs({
        optimizerName,
        autoLevel,
        maxBootstrappedDemos,
        maxLabeledDemos,
        maxFullEvals,
        reflectionMinibatchSize,
        useMerge,
      });
      const compKw = buildCompileKwargs({
        optimizerName,
        autoLevel,
        numTrials,
        minibatch,
        minibatchSize,
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
        ...(Object.keys(optKw).length > 0 && { optimizer_kwargs: optKw }),
        ...(Object.keys(compKw).length > 0 && { compile_kwargs: compKw }),
      };

      // Inject global API key + base URL into any model config that doesn't override
      const applyGlobals = (mc: ModelConfig): ModelConfig => {
        const out = { ...mc };
        if (globalBaseUrl && !out.base_url) out.base_url = globalBaseUrl;
        if (globalApiKey && !out.extra?.api_key) out.extra = { ...out.extra, api_key: globalApiKey };
        return out;
      };

      let result;
      if (jobType === "run") {
        if (!modelConfig.name.trim()) { toast.error(msg("submit.validation.model_required")); goTo(2); setSubmitting(false); setSubmitPhase("idle"); return; }
        const secondApplied = secondModelConfig?.name?.trim() ? applyGlobals(secondModelConfig) : undefined;
        const runPayload = {
          ...base,
          model_config: applyGlobals(modelConfig),
          ...(optimizerName === "gepa" && secondApplied
            ? { reflection_model_config: secondApplied }
            : {}),
          ...(optimizerName === "miprov2"
            ? {
              prompt_model_config: applyGlobals(modelConfig),
              ...(secondApplied ? { task_model_config: secondApplied } : {}),
            }
            : {}),
        } as Parameters<typeof submitRun>[0];
        result = await submitRun(runPayload);
      } else {
        const validGen = generationModels.filter((m) => m.name.trim()).map(applyGlobals);
        const validRef = reflectionModels.filter((m) => m.name.trim()).map(applyGlobals);
        if (validGen.length === 0) { toast.error(msg("submit.validation.generation_model_required")); goTo(2); setSubmitting(false); setSubmitPhase("idle"); return; }
        if (validRef.length === 0) { toast.error(msg("submit.validation.reflection_models_required")); goTo(2); setSubmitting(false); setSubmitPhase("idle"); return; }
        result = await submitGridSearch({ ...base, generation_models: validGen, reflection_models: validRef });
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

  return {
    // Navigation / step state
    step, setStep, direction, setDirection,
    summaryTab, setSummaryTab,
    summaryCodeTab, setSummaryCodeTab,
    goNext, goPrev, goTo,
    maxReachableStep,
    validateStep,
    handleNext,
    handleTabClick,
    // Job type / basics
    jobType, setOptimizationType,
    username,
    jobName, setJobName,
    jobDescription, setJobDescription,
    moduleName, setModuleName,
    optimizerName, setOptimizerName,
    // Code editors
    signatureCode, setSignatureCode,
    setSignatureManuallyEdited,
    metricCode, setMetricCode,
    signatureValidation, setSignatureValidation,
    metricValidation, setMetricValidation,
    runSignatureValidation,
    runMetricValidation,
    // Dataset
    parsedDataset, setParsedDataset,
    datasetFileName, setDatasetFileName,
    fileInputRef,
    handleFileUpload,
    // Column mapping
    columnRoles, setColumnRoles,
    // Global provider
    globalBaseUrl, setGlobalBaseUrl,
    globalApiKey, setGlobalApiKey,
    anyProviderHasEnvKey,
    // Run model configs
    modelConfig, setModelConfig,
    secondModelConfig, setSecondModelConfig,
    editingModel, setEditingModel,
    recentConfigs, saveToRecent, clearRecentConfigs,
    catalog,
    // Grid search
    generationModels, setGenerationModels,
    reflectionModels, setReflectionModels,
    // Split / shuffle
    split, updateSplit, splitSum,
    shuffle, setShuffle,
    // Advanced params
    autoLevel, setAutoLevel,
    maxBootstrappedDemos, setMaxBootstrappedDemos,
    maxLabeledDemos, setMaxLabeledDemos,
    numTrials, setNumTrials,
    minibatch, setMinibatch,
    minibatchSize, setMinibatchSize,
    reflectionMinibatchSize, setReflectionMinibatchSize,
    maxFullEvals, setMaxFullEvals,
    useMerge, setUseMerge,
    // Submission
    submitting,
    submitPhase,
    handleSubmit,
    // Clone
    cloneLoading,
  };
}

export type SubmitWizardContext = ReturnType<typeof useSubmitWizard>;
