"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { createPortal } from "react-dom";
import { useRouter, useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { toast } from "react-toastify";
import { Upload, ChevronLeft, ChevronRight, ChevronDown, Loader2, XCircle, AlertTriangle, Check, Database, Cpu, User, Code, Tag, Layers, Component, Target, FileText, Columns, Shuffle, Search } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";


import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { AnimatedWordmark } from "@/components/animated-wordmark";
import dynamic from "next/dynamic";
import type { ValidationResult as EditorValidationResult } from "@/components/code-editor";

const CodeEditor = dynamic(
 () => import("@/components/code-editor").then((m) => m.CodeEditor),
 { ssr: false, loading: () => <div className="h-[200px] rounded-lg border border-border/40 bg-muted/20 animate-pulse" /> },
);
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";

import { submitRun, submitGridSearch, validateCode, getOptimizationPayload, getJob } from "@/lib/api";
import type { ModelConfig, ColumnMapping, SplitFractions, ValidateCodeResponse, ModelCatalogResponse } from "@/lib/types";
import { parseDatasetFile, type ParsedDataset } from "@/lib/parse-dataset";
import { NumberInput } from "@/components/number-input";
import { ModelConfigModal } from "@/components/model-config-modal";
import { ModelChip, AddModelButton } from "@/components/model-chip";
import { getModelCatalog, cachedCatalog } from "@/lib/model-catalog";
import { HelpTip } from "@/components/help-tip";

/* ── Constants ── */

const emptyModelConfig = (): ModelConfig => ({
 name: "",
 temperature: 0.7,
 max_tokens: 1024,
});

const defaultSplit: SplitFractions = { train: 0.7, val: 0.15, test: 0.15 };

const STEPS = [
 { id: "basics", label: "פרטים בסיסיים"},
 { id: "data", label: "דאטאסט"},
 { id: "model", label: "מודל"},
 { id: "code", label: "קוד"},
 { id: "params", label: "פרמטרים"},
 { id: "review", label: "סיכום ושליחה"},
] as const;

/* ── Slide animation variants (RTL: forward = slide from left, backward = slide from right) ── */
const slideVariants = {
 enter: (direction: number) => ({
 x: direction > 0 ? -80 : 80,
 opacity: 0,
 scale: 0.97,
 }),
 center: {
 x: 0,
 opacity: 1,
 scale: 1,
 },
 exit: (direction: number) => ({
 x: direction > 0 ? 80 : -80,
 opacity: 0,
 scale: 0.97,
 }),
};

/* ── Page ── */

export default function SubmitPage() {
 const router = useRouter();
 const searchParams = useSearchParams();
 const { data: session } = useSession();

 // Wizard state
 const [step, setStep] = useState(0);
 const [direction, setDirection] = useState(0);
 // Expose for tutorial beforeShow
 useEffect(() => {
  (window as any).__skynetSetWizardStep = setStep;
  (window as any).__skynetSetParsedDataset = setParsedDataset;
  (window as any).__skynetSetColumnRoles = setColumnRoles;
  (window as any).__skynetSetDatasetFileName = setDatasetFileName;
  (window as any).__skynetSetSignatureCode = setSignatureCode;
  (window as any).__skynetSetMetricCode = setMetricCode;
  (window as any).__skynetSetOptimizerName = setOptimizerName;
  return () => {
   delete (window as any).__skynetSetWizardStep;
   delete (window as any).__skynetSetParsedDataset;
   delete (window as any).__skynetSetColumnRoles;
   delete (window as any).__skynetSetDatasetFileName;
   delete (window as any).__skynetSetSignatureCode;
   delete (window as any).__skynetSetMetricCode;
   delete (window as any).__skynetSetOptimizerName;
  };
 }, []);
 const [summaryTab, setSummaryTab] = useState(0);
 const [summaryCodeTab, setSummaryCodeTab] = useState<string>("signature");

 // Job type
 const [jobType, setOptimizationType] = useState<"run"|"grid_search">("run");

 // Username — always from the logged-in session
 const username = session?.user?.name ?? "";
 const [jobName, setJobName] = useState("");
 const [jobDescription, setJobDescription] = useState("");
 const [moduleName, setModuleName] = useState("predict");
 const [optimizerName, setOptimizerName] = useState("miprov2");
 const buildSignatureTemplate = (roles: Record<string, "input"|"output"|"ignore">) => {
  const inputs = Object.entries(roles).filter(([, r]) => r === "input").map(([c]) => c);
  const outputs = Object.entries(roles).filter(([, r]) => r === "output").map(([c]) => c);
  const toId = (s: string) => s.replace(/[^a-zA-Z0-9_\u0590-\u05FF]/g, "_").replace(/^(\d)/, "_$1");
  const inLines = inputs.length > 0
   ? inputs.map((c) => `    ${toId(c)}: str = dspy.InputField(desc="")`).join("\n")
   : `    input_field: str = dspy.InputField(desc="")`;
  const outLines = outputs.length > 0
   ? outputs.map((c) => `    ${toId(c)}: str = dspy.OutputField(desc="")`).join("\n")
   : `    output_field: str = dspy.OutputField(desc="")`;
  return `class MySignature(dspy.Signature):\n    """Describe the task here."""\n\n    # inputs\n${inLines}\n\n    # outputs\n${outLines}\n`;
 };
 const [signatureCode, setSignatureCode] = useState(() => buildSignatureTemplate({}));
 const METRIC_TEMPLATE_MIPRO = `def metric(example: dspy.Example, prediction: dspy.Prediction, trace: bool = None) -> float:
    # Return a numeric score (float/int/bool)

    pass
`;
 const METRIC_TEMPLATE_GEPA = `def metric(gold: dspy.Example, pred: dspy.Prediction, trace: bool = None, pred_name: str = None, pred_trace: list = None) -> dspy.Prediction:
    score = 0.0
    feedback = ""

    # Calculate score and feedback

    return dspy.Prediction(score=score, feedback=feedback)
`;
 const [metricCode, setMetricCode] = useState(METRIC_TEMPLATE_MIPRO);
 const metricIsTemplate = metricCode === METRIC_TEMPLATE_MIPRO || metricCode === METRIC_TEMPLATE_GEPA;

 // Swap metric template when optimizer changes (only if user hasn't edited it)
 useEffect(() => {
 if (metricIsTemplate) {
 setMetricCode(optimizerName === "gepa" ? METRIC_TEMPLATE_GEPA : METRIC_TEMPLATE_MIPRO);
 }
 // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [optimizerName]);

 // Dataset
 const [parsedDataset, setParsedDataset] = useState<ParsedDataset | null>(null);
 const [datasetFileName, setDatasetFileName] = useState<string | null>(null);
 const fileInputRef = useRef<HTMLInputElement>(null);

 // Column mapping
 const [columnRoles, setColumnRoles] = useState<Record<string,"input"|"output"|"ignore">>({});
 const [signatureManuallyEdited, setSignatureManuallyEdited] = useState(false);

 // Auto-update signature template when column roles change
 useEffect(() => {
  if (signatureManuallyEdited) return;
  const hasRoles = Object.values(columnRoles).some((r) => r === "input" || r === "output");
  if (!hasRoles) return;
  setSignatureCode(buildSignatureTemplate(columnRoles));
 }, [columnRoles, signatureManuallyEdited]);

 // Global provider settings (shared across all models)
 const [globalBaseUrl, setGlobalBaseUrl] = useState("");
 const [globalApiKey, setGlobalApiKey] = useState("");

 // Run model configs — primary + secondary (shared across optimizers)
 const [modelConfig, setModelConfig] = useState<ModelConfig>(emptyModelConfig());
 const [secondModelConfig, setSecondModelConfig] = useState<ModelConfig | null>(null);

 // Model config modal state
 const [editingModel, setEditingModel] = useState<{ config: ModelConfig; onSave: (c: ModelConfig) => void; label: string } | null>(null);

 // Recent model configs — persisted in localStorage
 const RECENT_KEY = "skynet:recent-model-configs";
 const MAX_RECENT = 5;
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

 // Module kwargs (JSON string)

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
 const columns = Object.keys(rows[0]);
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


 toast.success("הגדרות שוכפלו בהצלחה");
 })
 .catch(() => {
 toast.error("שגיאה בטעינת הגדרות לשכפול");
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
 if (!username.trim()) { if (showToast) toast.error("נא להזין שם משתמש"); return false; }
 if (!jobName.trim()) { if (showToast) toast.error("נא להזין שם לאופטימיזציה"); return false; }
 return true;
 case 1: {
 if (!parsedDataset || parsedDataset.rowCount === 0) { if (showToast) toast.error("נא להעלות קובץ דאטאסט"); return false; }
 const m = buildColumnMapping();
 if (Object.keys(m.inputs).length === 0) { if (showToast) toast.error("נא לסמן לפחות עמודת קלט אחת"); return false; }
 if (Object.keys(m.outputs).length === 0) { if (showToast) toast.error("נא לסמן לפחות עמודת פלט אחת"); return false; }
 return true;
 }
 case 2:
 if (jobType === "run") {
 if (!modelConfig.name.trim()) { if (showToast) toast.error("נא לבחור מודל"); return false; }
 // Require api_key if provider has no env default AND no global key
 const hasApiKey = !!globalApiKey || !!(modelConfig.extra?.api_key);
 if (!anyProviderHasEnvKey && !hasApiKey) {
 if (showToast) toast.error("נא להזין מפתח API — אין ב-env ולא הוזן ידנית");
 return false;
 }
 const secondModel = secondModelConfig;
 if (!secondModel?.name?.trim()) { if (showToast) toast.error("נא לבחור מודל רפלקציה"); return false; }
 }
 if (jobType === "grid_search") {
 if (generationModels.every(m => !m.name.trim())) { if (showToast) toast.error("נא להוסיף לפחות מודל יצירה אחד"); return false; }
 if (reflectionModels.every(m => !m.name.trim())) { if (showToast) toast.error("נא להוסיף לפחות מודל רפלקציה אחד"); return false; }
 }
 return true;
 case 3:
 if (!signatureCode.trim()) { if (showToast) toast.error("נא להזין קוד חתימה"); return false; }
 if (!metricCode.trim()) { if (showToast) toast.error("נא להזין קוד Metric"); return false; }
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

 const handleNext = async () => {
 // Auto-trigger code validation when leaving the code step (now step 3)
 if (step === 3 && signatureCode.trim() && metricCode.trim() && parsedDataset) {
 // Run validation — triggers the inline error UI in the CodeEditors
 const passed = await handleValidateCode();
 if (!passed) return;
 }
 if (validateStep(step, true)) goNext();
 };

 /* ── Tab click — allow going back freely, forward only if all prior steps valid ── */
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
 const roles: Record<string,"input"|"output"|"ignore"> = {};
 parsed.columns.forEach((col) => { roles[col] ="input"; });
 setColumnRoles(roles);
 toast.success(`נטען ${parsed.rowCount} שורות מ-${file.name}`);
 } catch (err) {
 toast.error(err instanceof Error ? err.message :"שגיאה בטעינת הקובץ");
 }
 }, []);

 /* ── Code validation handler ── */
 /* ── Validate a single code block (signature or metric) ── */
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

 /* ── Explicit validators wired to each CodeEditor's run button ── */
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

 /* ── Run both validations (used by Next-button auto-trigger) ── */
 const handleValidateCode = async (): Promise<boolean> => {
 if (!parsedDataset || parsedDataset.rowCount === 0) {
 toast.error("נא להעלות דאטאסט לפני אימות הקוד");
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
 toast.error("יש שגיאות בקוד — בדוק את הפירוט למטה");
 return false;
 } catch (err) {
 toast.error(err instanceof Error ? err.message : "שגיאה באימות הקוד");
 return false;
 }
 };

 /* ── Build structured kwargs ── */
 const buildOptimizerKwargs = (): Record<string, unknown> => {
 const kw: Record<string, unknown> = {};
 if (optimizerName === "miprov2") {
 if (autoLevel) kw.auto = autoLevel;
 if (maxBootstrappedDemos) kw.max_bootstrapped_demos = parseInt(maxBootstrappedDemos, 10);
 if (maxLabeledDemos) kw.max_labeled_demos = parseInt(maxLabeledDemos, 10);
 } else if (optimizerName === "gepa") {
 // GEPA requires exactly one of: auto, max_full_evals, max_metric_calls
 if (autoLevel) {
 kw.auto = autoLevel;
 } else if (maxFullEvals) {
 kw.max_full_evals = parseInt(maxFullEvals, 10);
 }
 if (reflectionMinibatchSize) kw.reflection_minibatch_size = parseInt(reflectionMinibatchSize, 10);
 kw.use_merge = useMerge;
 }
 return Object.keys(kw).length > 0 ? kw : {};
 };

 const buildCompileKwargs = (): Record<string, unknown> => {
 const kw: Record<string, unknown> = {};
 if (optimizerName === "miprov2") {
 // When auto is set, num_trials/num_candidates are controlled by auto
 if (!autoLevel && numTrials) kw.num_trials = parseInt(numTrials, 10);
 kw.minibatch = minibatch;
 if (minibatch && minibatchSize) kw.minibatch_size = parseInt(minibatchSize, 10);
 }
 return Object.keys(kw).length > 0 ? kw : {};
 };

 /* ── Submit ── */
 const handleSubmit = async () => {
 if (!username.trim()) { toast.error("נא להזין שם משתמש"); goTo(0); return; }
 if (!parsedDataset || parsedDataset.rowCount === 0) { toast.error("נא להעלות דאטאסט"); goTo(1); return; }
 if (!signatureCode.trim()) { toast.error("נא להזין קוד חתימה"); goTo(3); return; }
 if (!metricCode.trim()) { toast.error("נא להזין קוד Metric"); goTo(3); return; }

 const columnMapping = buildColumnMapping();
 if (Object.keys(columnMapping.inputs).length === 0) { toast.error("נא לסמן לפחות עמודת קלט אחת"); goTo(1); return; }
 if (Object.keys(columnMapping.outputs).length === 0) { toast.error("נא לסמן לפחות עמודת פלט אחת"); goTo(1); return; }

 setSubmitting(true);
 setSubmitPhase("sending");
 try {
 const optKw = buildOptimizerKwargs();
 const compKw = buildCompileKwargs();
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
 if (jobType ==="run") {
 if (!modelConfig.name.trim()) { toast.error("נא לבחור מודל"); goTo(2); setSubmitting(false); setSubmitPhase("idle"); return; }
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
 if (validGen.length === 0) { toast.error("נא להוסיף לפחות מודל יצירה אחד"); goTo(2); setSubmitting(false); setSubmitPhase("idle"); return; }
 if (validRef.length === 0) { toast.error("נא להוסיף לפחות מודל רפלקציה אחד"); goTo(2); setSubmitting(false); setSubmitPhase("idle"); return; }
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
 toast.error(err instanceof Error ? err.message :"שגיאה בשליחת האופטימיזציה");
 setSubmitPhase("idle");
 setSubmitting(false);
 }
 };

 /* ── Split fraction handler ── */
 const updateSplit = (field: keyof SplitFractions, value: string) => {
 const num = parseFloat(value);
 if (isNaN(num) || num < 0 || num > 1) return;
 setSplit((prev) => ({ ...prev, [field]: num }));
 };
 const splitSum = +(split.train + split.val + split.test).toFixed(4);

 /* ════════════════════════════════════════════
 STEP CONTENT
 ════════════════════════════════════════════ */

 const stepContent = [
 /* ── Step 0: Basics ── */
 <Card key="basics" className="border-border/50 bg-card/80 backdrop-blur-xl shadow-lg" data-tutorial="wizard-step-1">
 <CardHeader>
 <CardTitle className="text-lg">פרטים בסיסיים</CardTitle>
 <CardDescription>שם וסוג אופטימיזציה</CardDescription>
 </CardHeader>
 <CardContent className="space-y-4">
 <div className="space-y-2">
 <Label>שם האופטימיזציה</Label>
 <Input placeholder="לדוגמא: ניתוח שאלות מתמטיקה" value={jobName} onChange={(e) => setJobName(e.target.value)} dir="rtl" />
 </div>
 <div className="space-y-2">
 <div className="flex items-center justify-between">
 <Label>תיאור</Label>
 <span className={cn("text-[10px] tabular-nums transition-colors", jobDescription.length > 280 ? "text-destructive font-medium" : "text-muted-foreground/50")}>{jobDescription.length}/280</span>
 </div>
 <textarea
 data-tutorial="job-description"
 value={jobDescription}
 onChange={(e) => { if (e.target.value.length <= 280) setJobDescription(e.target.value); }}
 placeholder="תיאור קצר של מטרת האופטימיזציה (אופציונלי)"
 dir="rtl"
 rows={4}
 className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:border-ring disabled:cursor-not-allowed disabled:opacity-50 resize-none"
 />
 </div>
 <Separator />
 <div className="space-y-3">
 <Label>סוג אופטימיזציה</Label>
 <div className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1">
 <div
 className="absolute top-1 bottom-1 w-[calc(50%-6px)] rounded-md bg-background shadow-sm transition-[inset-inline-start] duration-100 ease-out"
 style={{ insetInlineStart: jobType === "run" ? 4 : "calc(50% + 2px)" }}
 />
 {([["run","ריצה בודדת","אופטימיזציה עם מודל יחיד"], ["grid_search","סריקה","סריקת זוגות מודלים למציאת השילוב הטוב ביותר"]] as const).map(([val, label, desc]) => (
 <button key={val} type="button" onClick={() => setOptimizationType(val)}
 className={cn("relative z-10 flex-1 rounded-md px-4 py-2.5 cursor-pointer text-center transition-colors duration-200",
 jobType === val ?"text-foreground":"text-foreground/60 hover:text-foreground")}>
 <span className="text-sm font-medium">{label}</span>
 <span className={cn("block text-[11px] mt-0.5 transition-colors duration-200", jobType === val ?"text-muted-foreground":"text-foreground/40")}>{desc}</span>
 </button>
 ))}
 </div>
 </div>
 </CardContent>
 </Card>,

 /* ── Step 1: Dataset ── */
 <Card key="data" className=" border-border/50 bg-card/80 backdrop-blur-xl shadow-lg" data-tutorial="wizard-step-2">
 <CardHeader>
 <CardTitle className="text-lg">דאטאסט</CardTitle>
 <CardDescription>העלה קובץ נתונים והגדר את מיפוי העמודות</CardDescription>
 </CardHeader>
 <CardContent className="space-y-5">
 <label
 className={cn(
"border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all duration-300 block group",
 parsedDataset
 ? "border-primary/40 bg-primary/5"
 : "hover:border-primary/50 hover:bg-muted/30"
 )}
 >
 <Upload className="h-10 w-10 mx-auto mb-3 text-muted-foreground group-hover:text-primary/70 transition-colors duration-300"/>
 <p className="text-sm font-medium truncate max-w-full px-4" title={datasetFileName ?? undefined}>{datasetFileName ?? "לחץ להעלאת קובץ CSV או JSON"}</p>
 {parsedDataset && (
 <Badge variant="secondary" className="mt-2">{parsedDataset.rowCount} שורות · {parsedDataset.columns.length} עמודות</Badge>
 )}
 <input ref={fileInputRef} type="file" accept=".csv,.json" className="hidden" onChange={handleFileUpload} />
 </label>

 {parsedDataset && parsedDataset.columns.length > 0 && (
 <>
 <Separator />
 <div className="space-y-3" data-tutorial="column-mapping">
 <Label>מיפוי עמודות</Label>
 <p className="text-xs text-muted-foreground">סמן כל עמודה כקלט, פלט, או התעלם</p>
 <div className="space-y-2">
 {parsedDataset.columns.map((col) => (
 <div key={col} className="flex items-center justify-between gap-2">
 <span className="text-xs sm:text-sm font-mono truncate" dir="ltr">{col}</span>
 {(() => {
 const options = [["input","קלט"], ["output","פלט"], ["ignore","התעלם"]] as const;
 const activeIdx = options.findIndex(([v]) => v === columnRoles[col]);
 const pillLeft = activeIdx >= 0 ? `calc(${activeIdx} * 100% / 3 + 2px)` : "2px";
 return (
 <div className="relative inline-grid grid-cols-3 shrink-0 rounded-lg bg-muted p-0.5 gap-0.5" dir="rtl">
 <div
 className="absolute top-0.5 bottom-0.5 rounded-md bg-stone-500/15 shadow-sm transition-[inset-inline-start] duration-100 ease-out"
 style={{ width: "calc((100% - 6px) / 3)", insetInlineStart: pillLeft }}
 />
 {options.map(([val, label]) => (
 <button key={val} type="button"
 onClick={() => setColumnRoles((prev) => ({ ...prev, [col]: val }))}
 className={cn("relative z-10 rounded-md px-3 py-1 text-xs font-medium text-center transition-colors duration-100 cursor-pointer",
 columnRoles[col] === val ? "text-stone-600" : "text-muted-foreground hover:text-foreground"
 )}>
 {label}
 </button>
 ))}
 </div>
 );
 })()}
 </div>
 ))}
 </div>
 </div>
 </>
 )}
 </CardContent>
 </Card>,

 /* ── Step 2: Model & Optimizer ── */
 <Card key="model" className="border-border/50 bg-card/80 backdrop-blur-xl shadow-lg" data-tutorial="wizard-step-3">
 <CardHeader>
 <CardTitle className="text-lg">הגדרות מודל ואופטימיזציה</CardTitle>
 <CardDescription>בחר מודול, אופטימייזר ומודלי שפה</CardDescription>
 </CardHeader>
 <CardContent className="space-y-5">
 <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
 <div className="space-y-2" data-tutorial="module-selector">
 <Label><HelpTip text="אופן עיבוד הפרומפט — Predict שולח ישירות, CoT מוסיף שלב חשיבה לפני התשובה">מודול</HelpTip></Label>
 <div className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1">
 <div
 className="absolute top-1 bottom-1 w-[calc(50%-6px)] rounded-md bg-background shadow-sm transition-[inset-inline-start] duration-100 ease-out"
 style={{ insetInlineStart: moduleName === "predict" ? 4 : "calc(50% + 2px)" }}
 />
 {([["predict","Predict"], ["cot","CoT"]] as const).map(([val, label]) => (
 <button key={val} type="button" onClick={() => setModuleName(val)}
 className={cn("relative z-10 flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-200 text-center cursor-pointer",
 moduleName === val ?"text-foreground":"text-muted-foreground hover:text-foreground")}>{label}</button>
 ))}
 </div>
 </div>
 <div className="space-y-2" data-tutorial="optimizer-selector">
 <Label><HelpTip text="אלגוריתם האופטימיזציה — MIPROv2 מנסה שילובי הוראות ודוגמאות, GEPA משפר באמצעות רפלקציה על שגיאות">אופטימייזר</HelpTip></Label>
 <div className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1">
 <div
 className="absolute top-1 bottom-1 w-[calc(50%-6px)] rounded-md bg-background shadow-sm transition-[inset-inline-start] duration-100 ease-out"
 style={{ insetInlineStart: optimizerName === "miprov2" ? 4 : "calc(50% + 2px)" }}
 />
 {([["miprov2","MIPROv2"], ["gepa","GEPA"]] as const).map(([val, label]) => (
 <button key={val} type="button" onClick={() => setOptimizerName(val)}
 className={cn("relative z-10 flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-200 text-center cursor-pointer",
 optimizerName === val ?"text-foreground":"text-muted-foreground hover:text-foreground")}>{label}</button>
 ))}
 </div>
 </div>
 </div>
 <Separator />

 {/* Global provider settings */}
 <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
 <div className="space-y-2">
 <Label htmlFor="baseUrl">כתובת שרת (Base URL)</Label>
 <Input id="baseUrl" dir="ltr" value={globalBaseUrl} onChange={(e) => setGlobalBaseUrl(e.target.value)} />
 <p className="text-[10px] text-muted-foreground">ניתן להשאיר ריק — יוגדר אוטומטית לפי הספק</p>
 </div>
 <div className="space-y-2">
 <Label htmlFor="apiKey">מפתח API</Label>
 <Input id="apiKey" dir="ltr" type="password" placeholder="sk-..." value={globalApiKey} onChange={(e) => setGlobalApiKey(e.target.value)} />
 {anyProviderHasEnvKey && <p className="text-[10px] text-muted-foreground">אופציונאלי- מפתח API ילקח ממשתנה סביבה</p>}
 {globalApiKey && typeof window !== "undefined" && window.location.protocol !== "https:" && process.env.NODE_ENV === "production" && (
 <p className="text-[10px] text-amber-600 dark:text-amber-400 flex items-center gap-1">
 <AlertTriangle className="size-3 shrink-0" />
 ⚠️ חיבור לא מוצפן — מפתח ה-API יישלח ללא הצפנה. השתמשו ב-HTTPS בסביבת ייצור.
 </p>
 )}
 </div>
 </div>

 <Separator />

 {/* Model chips */}
 {jobType === "run" ? (
 <div className="space-y-3" data-tutorial="model-catalog">
 <Label className="text-sm font-semibold">מודלים</Label>
 <div className="space-y-2">
 <ModelChip
 config={modelConfig}
 roleLabel="מודל יצירה"
 required
 onClick={() => setEditingModel({ config: modelConfig, onSave: setModelConfig, label: "מודל יצירה" })}
 onRemove={modelConfig.name ? () => setModelConfig(emptyModelConfig()) : undefined}
 />
 <ModelChip
 config={secondModelConfig ?? emptyModelConfig()}
 roleLabel="מודל רפלקציה"
 required
 onClick={() => setEditingModel({ config: secondModelConfig ?? emptyModelConfig(), onSave: setSecondModelConfig, label: "מודל רפלקציה" })}
 onRemove={secondModelConfig?.name ? () => setSecondModelConfig(null) : undefined}
 />
 </div>
 </div>
 ) : (
 <div className="space-y-5">
 <div className="space-y-2">
 <Label className="text-sm font-semibold">מודלי יצירה</Label>
 <div className="flex flex-wrap gap-2">
 {generationModels.map((m, i) => (
 <ModelChip
 key={i}
 config={m}
 onClick={() => setEditingModel({
 config: m,
 onSave: (c) => { const u = [...generationModels]; u[i] = c; setGenerationModels(u); },
 label: `מודל יצירה ${i + 1}`,
 })}
 onRemove={generationModels.length > 1 ? () => setGenerationModels(generationModels.filter((_, j) => j !== i)) : undefined}
 />
 ))}
 {generationModels.every((m) => m.name.trim()) && (
 <AddModelButton label="הוסף" onClick={() => setEditingModel({
 config: generationModels.length ? { ...generationModels[generationModels.length - 1], name: "" } : emptyModelConfig(),
 onSave: (c) => setGenerationModels([...generationModels.filter((m) => m.name.trim()), c]),
 label: "מודל יצירה חדש",
 })} />
 )}
 </div>
 </div>
 <Separator />
 <div className="space-y-2">
 <Label className="text-sm font-semibold">מודלי רפלקציה</Label>
 <div className="flex flex-wrap gap-2">
 {reflectionModels.map((m, i) => (
 <ModelChip
 key={i}
 config={m}
 onClick={() => setEditingModel({
 config: m,
 onSave: (c) => { const u = [...reflectionModels]; u[i] = c; setReflectionModels(u); },
 label: `מודל רפלקציה ${i + 1}`,
 })}
 onRemove={reflectionModels.length > 1 ? () => setReflectionModels(reflectionModels.filter((_, j) => j !== i)) : undefined}
 />
 ))}
 {reflectionModels.every((m) => m.name.trim()) && (
 <AddModelButton label="הוסף" onClick={() => setEditingModel({
 config: reflectionModels.length ? { ...reflectionModels[reflectionModels.length - 1], name: "" } : emptyModelConfig(),
 onSave: (c) => setReflectionModels([...reflectionModels.filter((m) => m.name.trim()), c]),
 label: "מודל רפלקציה חדש",
 })} />
 )}
 </div>
 </div>
 </div>
 )}
 {/* Model config modal — shared across all model chips */}
 <ModelConfigModal
 open={!!editingModel}
 onOpenChange={(open) => { if (!open) setEditingModel(null); }}
 config={editingModel?.config ?? emptyModelConfig()}
 onSave={(c) => { editingModel?.onSave(c); saveToRecent(c); setEditingModel(null); }}
 roleLabel={editingModel?.label ?? "הגדרות מודל"}
 catalogModels={catalog?.models}
 recentConfigs={recentConfigs}
 onClearRecent={() => { setRecentConfigs([]); localStorage.removeItem(RECENT_KEY); }}
 />
 </CardContent>
 </Card>,

 /* ── Step 3: Code ── */
 <Card key="code" className="border-border/50 bg-card/80 backdrop-blur-xl shadow-lg" data-tutorial="wizard-step-4">
 <CardHeader>
 <CardTitle className="text-lg">קוד</CardTitle>
 <CardDescription>הגדר את חתימת המשימה ופונקציית המדידה</CardDescription>
 </CardHeader>
 <CardContent className="space-y-5">
 <div className="space-y-2" data-tutorial="signature-editor">
 <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"><HelpTip text="הגדרת שדות הקלט והפלט של המשימה — מה המודל מקבל ומה הוא צריך להחזיר">חתימה (Signature)</HelpTip></Label>
 <CodeEditor
 value={signatureCode}
 onChange={(v) => { setSignatureCode(v); setSignatureManuallyEdited(true); setSignatureValidation(null); }}
 height="180px"
 onRun={runSignatureValidation}
 validationResult={signatureValidation}
 />
 </div>
 <Separator />
 <div className="space-y-2" data-tutorial="metric-editor">
 <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"><HelpTip text="פונקציה שמודדת את איכות התשובה — מחזירה ציון מספרי לכל דוגמה">מטריקה (Metric)</HelpTip></Label>
 <CodeEditor
 value={metricCode}
 onChange={(v) => { setMetricCode(v); setMetricValidation(null); }}
 height="180px"
 onRun={runMetricValidation}
 validationResult={metricValidation}
 />
 </div>
 </CardContent>
 </Card>,

 /* ── Step 4: Parameters ── */
 <Card key="params" className=" border-border/50 bg-card/80 backdrop-blur-xl shadow-lg" data-tutorial="wizard-step-5">
 <CardHeader>
 <CardTitle className="text-lg">פרמטרים</CardTitle>
 <CardDescription>חלוקת הנתונים והגדרות האופטימייזר</CardDescription>
 </CardHeader>
 <CardContent className="space-y-5">
 {/* Split fractions */}
 <div className="space-y-3" data-tutorial="data-splits">
 <div className="flex items-center justify-between">
 <Label className="font-semibold"><HelpTip text="הנתונים מחולקים לשלוש קבוצות — אימון ללמידה, אימות לכיוונון, ובדיקה למדידת הביצועים הסופיים">חלוקת דאטאסט</HelpTip></Label>
 {splitSum !== 1 && <Badge variant="destructive" className="text-xs">סכום: {splitSum}</Badge>}
 </div>
 <div className="flex h-3 rounded-full overflow-hidden">
 <div className="bg-[#3D2E22] transition-all" style={{ width: `${split.train * 100}%` }} />
 <div className="bg-[#C8A882] transition-all" style={{ width: `${split.val * 100}%` }} />
 <div className="bg-[#8C7A6B] transition-all" style={{ width: `${split.test * 100}%` }} />
 </div>
 <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
 <div className="space-y-1">
 <Label htmlFor="split-train" className="flex items-center gap-1.5 text-xs"><span className="inline-block w-2 h-2 rounded-full bg-[#3D2E22]"/><HelpTip text="דוגמאות שהאופטימייזר לומד מהן">אימון</HelpTip></Label>
 <NumberInput id="split-train" step={0.05} min={0} max={1} value={split.train} onChange={(v) => updateSplit("train", String(v))} />
 </div>
 <div className="space-y-1">
 <Label htmlFor="split-val" className="flex items-center gap-1.5 text-xs"><span className="inline-block w-2 h-2 rounded-full bg-[#C8A882]"/><HelpTip text="דוגמאות לכיוונון פנימי במהלך האופטימיזציה">אימות</HelpTip></Label>
 <NumberInput id="split-val" step={0.05} min={0} max={1} value={split.val} onChange={(v) => updateSplit("val", String(v))} />
 </div>
 <div className="space-y-1">
 <Label htmlFor="split-test" className="flex items-center gap-1.5 text-xs"><span className="inline-block w-2 h-2 rounded-full bg-[#8C7A6B]"/><HelpTip text="דוגמאות שמורות למדידה סופית — לא נחשפות באימון">בדיקה</HelpTip></Label>
 <NumberInput id="split-test" step={0.05} min={0} max={1} value={split.test} onChange={(v) => updateSplit("test", String(v))} />
 </div>
 </div>
 </div>

 <Separator />

 {/* Advanced settings inline */}
 <div className="space-y-4">
 <Label className="font-semibold">הגדרות נוספות</Label>
 <div className="flex items-center justify-between">
 <Label htmlFor="shuffle" className="cursor-pointer text-sm"><HelpTip text="ערבוב סדר השורות בדאטאסט לפני החלוקה — מונע הטיה מסדר הנתונים">ערבוב</HelpTip></Label>
 <Switch id="shuffle" checked={shuffle} onCheckedChange={setShuffle} />
 </div>
 {/* Optimizer-specific parameters */}
 <Separator />
 <Label className="font-semibold text-xs text-muted-foreground">פרמטרי אופטימייזר</Label>

 {/* Common: auto level */}
 <div className="space-y-2" data-tutorial="auto-level">
 <Label className="text-sm"><HelpTip text="עומק החיפוש — קלה מהירה עם פחות ניסיונות, מעמיקה בודקת יותר שילובים אך לוקחת זמן רב יותר">רמת חיפוש (auto)</HelpTip></Label>
 <div className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1">
 {autoLevel && (
 <div
 className="absolute top-1 bottom-1 rounded-md bg-background shadow-sm transition-[inset-inline-start] duration-100 ease-out pointer-events-none"
 style={{ width: "calc((100% - 8px) / 3)", insetInlineStart: `calc(${(["light","medium","heavy"] as string[]).indexOf(autoLevel)} * (100% / 3) + 4px)` }}
 />
 )}
 {([["light","קלה"], ["medium","בינונית"], ["heavy","מעמיקה"]] as const).map(([val, label]) => (
 <button key={val} type="button" onClick={() => setAutoLevel(autoLevel === val ? "" : val)}
 className={cn("relative z-[1] flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors text-center cursor-pointer",
 autoLevel === val ?"text-foreground":"text-muted-foreground hover:text-foreground"
 )}>{label}</button>
 ))}
 </div>
 </div>

 {optimizerName === "miprov2"? (
 <div className="grid grid-cols-2 gap-3" data-tutorial="mipro-params">
 <div className="space-y-1.5">
 <Label className="text-xs"><HelpTip text="דוגמאות שהמערכת מייצרת אוטומטית מתוך הנתונים כדי ללמד את המודל">דוגמאות אוטומטיות</HelpTip></Label>
 <NumberInput min={0} max={20} step={1} value={maxBootstrappedDemos ? parseInt(maxBootstrappedDemos, 10) : ""} onChange={(v) => setMaxBootstrappedDemos(String(v))} />
 </div>
 <div className="space-y-1.5">
 <Label className="text-xs"><HelpTip text="דוגמאות קלט-פלט מתוך הדאטאסט שמוצגות למודל כהדגמה">דוגמאות מהנתונים</HelpTip></Label>
 <NumberInput min={0} max={20} step={1} value={maxLabeledDemos ? parseInt(maxLabeledDemos, 10) : ""} onChange={(v) => setMaxLabeledDemos(String(v))} />
 </div>
 <div className="space-y-1.5">
 <Label className={cn("text-xs", autoLevel && "text-muted-foreground/50")}><HelpTip text="כמה שילובים שונים של הוראות ודוגמאות האופטימייזר ינסה">מספר ניסיונות</HelpTip></Label>
 <NumberInput min={1} max={100} step={1} value={numTrials ? parseInt(numTrials, 10) : ""} onChange={(v) => setNumTrials(String(v))} disabled={!!autoLevel} />
 </div>
 <div className="space-y-1.5">
 <Label className="text-xs"><HelpTip text="מספר הדוגמאות שנבדקות בכל סבב הערכה — מדגם קטן מזרז, גדול מדויק יותר">גודל מדגם</HelpTip></Label>
 <NumberInput min={1} max={200} step={1} value={minibatchSize ? parseInt(minibatchSize, 10) : ""} onChange={(v) => setMinibatchSize(String(v))} />
 </div>
 <div className="col-span-2 flex items-center justify-between">
 <Label className="text-sm cursor-pointer"><HelpTip text="כשפעיל, הערכה רצה על מדגם קטן במקום הדאטאסט המלא — מאיץ את התהליך">בדיקה חלקית</HelpTip></Label>
 <Switch checked={minibatch} onCheckedChange={setMinibatch} />
 </div>
 </div>
 ) : (
 <div className="grid grid-cols-2 gap-3" data-tutorial="gepa-params">
 <div className="space-y-1.5">
 <Label className="text-xs"><HelpTip text="כמה דוגמאות המודל מנתח בכל סבב רפלקציה כדי לזהות דפוסי שגיאה">גודל מדגם לרפלקציה</HelpTip></Label>
 <NumberInput min={1} max={20} step={1} value={reflectionMinibatchSize ? parseInt(reflectionMinibatchSize, 10) : ""} onChange={(v) => setReflectionMinibatchSize(String(v))} />
 </div>
 <div className="space-y-1.5">
 <Label className={cn("text-xs", autoLevel && "text-muted-foreground/50")}><HelpTip text="מספר הפעמים שהמערכת מריצה הערכה מלאה על כל הנתונים">מקסימום סבבי הערכה</HelpTip></Label>
 <NumberInput min={1} max={50} step={1} value={maxFullEvals ? parseInt(maxFullEvals, 10) : ""} onChange={(v) => setMaxFullEvals(String(v))} disabled={!!autoLevel} />
 </div>
 <div className="col-span-2 flex items-center justify-between">
 <Label className="text-sm cursor-pointer"><HelpTip text="כשפעיל, המערכת משלבת הוראות מכמה מועמדים טובים לפרומפט אחד משופר">מיזוג מועמדים</HelpTip></Label>
 <Switch checked={useMerge} onCheckedChange={setUseMerge} />
 </div>
 </div>
 )}
 </div>

 </CardContent>
 </Card>,

 /* ── Step 5: Summary & Submit ── */
 <div key="review" className="space-y-4" data-tutorial="wizard-step-6">
 {(() => {
 const SUMMARY_TABS = [
  { id: "general", label: "כללי", icon: <User className="size-3.5" /> },
  { id: "dataset", label: "דאטאסט", icon: <Database className="size-3.5" /> },
  { id: "models", label: "מודלים", icon: <Cpu className="size-3.5" /> },
  { id: "optimizer", label: "אופטימייזר", icon: <Target className="size-3.5" /> },
  { id: "code", label: "קוד", icon: <Code className="size-3.5" /> },
 ];

 return (
 <>
 {/* Tabbed sections */}
 <motion.div
  initial={{ opacity: 0, y: 8 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.3, ease: [0.2, 0.8, 0.2, 1] }}
  className="rounded-2xl border border-border bg-card/80 backdrop-blur-xl shadow-lg overflow-hidden"
 >
  {/* Tab bar */}
  <div className="relative flex border-b border-border bg-secondary/50 p-1 gap-0.5">
   <div
    className="absolute top-1 bottom-1 rounded-lg bg-background shadow-sm transition-[inset-inline-start] duration-200 ease-out pointer-events-none"
    style={{
     width: `calc((100% - 12px) / ${SUMMARY_TABS.length})`,
     insetInlineStart: `calc(${summaryTab} * ${100 / SUMMARY_TABS.length}% + 4px)`,
    }}
   />
   {SUMMARY_TABS.map((tab, i) => (
    <button
     key={tab.id}
     type="button"
     onClick={() => setSummaryTab(i)}
     className={cn(
      "relative z-10 flex-1 flex items-center justify-center gap-1.5 rounded-lg py-2.5 text-xs font-medium transition-colors duration-150 cursor-pointer",
      summaryTab === i
       ? "text-foreground"
       : "text-muted-foreground hover:text-foreground/80"
     )}
    >
     {tab.icon}
     <span className="hidden sm:inline">{tab.label}</span>
    </button>
   ))}
  </div>

  {/* Tab content */}
  <div className="p-5">
   <AnimatePresence mode="wait">
    <motion.div
     key={summaryTab}
     initial={{ opacity: 0, y: 6 }}
     animate={{ opacity: 1, y: 0 }}
     exit={{ opacity: 0, y: -6 }}
     transition={{ duration: 0.15 }}
    >
     {/* General */}
     {summaryTab === 0 && (
      <div className="space-y-0">
       <div className="flex items-center justify-between py-2.5 border-b border-border/40">
        <span className="flex items-center gap-2 text-xs text-muted-foreground"><Tag className="size-3.5" />שם האופטימיזציה</span>
        <span className="text-sm font-medium">{jobName || "—"}</span>
       </div>
       <div className="flex items-center justify-between py-2.5 border-b border-border/40">
        <span className="flex items-center gap-2 text-xs text-muted-foreground"><Layers className="size-3.5" />סוג אופטימיזציה</span>
        <span className="text-sm font-medium">{jobType === "run" ? "ריצה בודדת" : "סריקה"}</span>
       </div>
       <div className="flex items-center justify-between py-2.5 border-b border-border/40">
        <span className="flex items-center gap-2 text-xs text-muted-foreground"><Component className="size-3.5" />מודול</span>
        <span className="text-sm font-medium font-mono" dir="ltr">{moduleName === "predict" ? "Predict" : "CoT"}</span>
       </div>
       <div className="flex items-center justify-between py-2.5 border-b border-border/40">
        <span className="flex items-center gap-2 text-xs text-muted-foreground"><Target className="size-3.5" />אופטימייזר</span>
        <span className="text-sm font-medium font-mono" dir="ltr">{optimizerName === "miprov2" ? "MIPROv2" : "GEPA"}</span>
       </div>
      </div>
     )}

     {/* Dataset */}
     {summaryTab === 1 && (
      <div className="space-y-4">
       <div className="flex items-center justify-between py-2.5 border-b border-border/40">
        <span className="flex items-center gap-2 text-xs text-muted-foreground"><FileText className="size-3.5" />קובץ</span>
        <span className="text-sm font-medium truncate max-w-[60%]" title={datasetFileName ?? undefined}>{datasetFileName ?? "—"}</span>
       </div>
       {parsedDataset && (
        <div className="flex items-center justify-between py-2.5 border-b border-border/40">
         <span className="flex items-center gap-2 text-xs text-muted-foreground"><Database className="size-3.5" />גודל</span>
         <span className="text-sm font-medium">{parsedDataset.rowCount} שורות · {parsedDataset.columns.length} עמודות</span>
        </div>
       )}
       {parsedDataset && parsedDataset.columns.length > 0 && (
        <>
         <div className="space-y-2 pt-1">
          <span className="flex items-center gap-2 text-xs text-muted-foreground"><Columns className="size-3.5" />מיפוי עמודות</span>
          <div className="space-y-1.5">
           {parsedDataset.columns.map((col) => {
            const role = columnRoles[col];
            if (role === "ignore") return null;
            const roleLabel = role === "input" ? "קלט" : role === "output" ? "פלט" : "התעלם";
            const roleColor = role === "input" ? "text-[#3D2E22] bg-[#3D2E22]/10" : role === "output" ? "text-primary bg-primary/10" : "text-muted-foreground bg-muted";
            return (
             <div key={col} className="flex items-center justify-between gap-2 py-1">
              <span className="text-xs font-mono truncate" dir="ltr">{col}</span>
              <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", roleColor)}>{roleLabel}</span>
             </div>
            );
           })}
          </div>
         </div>
        </>
       )}
       <Separator />
       <div className="space-y-3">
        <span className="flex items-center gap-2 text-xs text-muted-foreground"><Layers className="size-3.5" />חלוקת דאטאסט</span>
        <div className="flex h-3 rounded-full overflow-hidden">
         <div className="bg-[#3D2E22]" style={{ width: `${split.train * 100}%` }} />
         <div className="bg-[#C8A882]" style={{ width: `${split.val * 100}%` }} />
         <div className="bg-[#8C7A6B]" style={{ width: `${split.test * 100}%` }} />
        </div>
        <div className="grid grid-cols-3 gap-4">
         <div className="flex items-center gap-1.5 text-xs"><span className="inline-block w-2 h-2 rounded-full bg-[#3D2E22]"/>אימון {split.train}</div>
         <div className="flex items-center gap-1.5 text-xs"><span className="inline-block w-2 h-2 rounded-full bg-[#C8A882]"/>אימות {split.val}</div>
         <div className="flex items-center gap-1.5 text-xs"><span className="inline-block w-2 h-2 rounded-full bg-[#8C7A6B]"/>בדיקה {split.test}</div>
        </div>
       </div>
       <div className="flex items-center justify-between py-2.5 border-b border-border/40">
        <span className="flex items-center gap-2 text-xs text-muted-foreground"><Shuffle className="size-3.5" />ערבוב</span>
        <span className="text-sm font-medium">{shuffle ? "כן" : "לא"}</span>
       </div>
      </div>
     )}

     {/* Models */}
     {summaryTab === 2 && (
      <div className="space-y-2 pointer-events-none">
       {jobType === "run" ? (
        <div className="space-y-2">
         <ModelChip config={modelConfig} roleLabel="מודל יצירה" onClick={() => {}} />
         {secondModelConfig?.name && (
          <ModelChip config={secondModelConfig} roleLabel="מודל רפלקציה" onClick={() => {}} />
         )}
        </div>
       ) : (
        <div className="space-y-2">
         <span className="text-[10px] uppercase tracking-wide text-muted-foreground">מודלי יצירה</span>
         <div className="space-y-1.5">
          {generationModels.filter(m => m.name).map((m, i) => (
           <ModelChip key={i} config={m} onClick={() => {}} />
          ))}
         </div>
         <span className="text-[10px] uppercase tracking-wide text-muted-foreground">מודלי רפלקציה</span>
         <div className="space-y-1.5">
          {reflectionModels.filter(m => m.name).map((m, i) => (
           <ModelChip key={i} config={m} onClick={() => {}} />
          ))}
         </div>
        </div>
       )}
      </div>
     )}

     {/* Optimizer */}
     {summaryTab === 3 && (
      <div className="space-y-0">
       <div className="flex items-center justify-between py-2.5 border-b border-border/40">
        <span className="flex items-center gap-2 text-xs text-muted-foreground"><Search className="size-3.5" />רמת חיפוש</span>
        <span className="text-sm font-medium">{autoLevel === "light" ? "קלה" : autoLevel === "medium" ? "בינונית" : "מעמיקה"}</span>
       </div>
       {optimizerName === "miprov2" ? (
        <>
         <div className="flex items-center justify-between py-2.5 border-b border-border/40">
          <span className="flex items-center gap-2 text-xs text-muted-foreground"><Cpu className="size-3.5" />דוגמאות אוטומטיות</span>
          <span className="text-sm font-medium font-mono">{maxBootstrappedDemos || "—"}</span>
         </div>
         <div className="flex items-center justify-between py-2.5 border-b border-border/40">
          <span className="flex items-center gap-2 text-xs text-muted-foreground"><Database className="size-3.5" />דוגמאות מהנתונים</span>
          <span className="text-sm font-medium font-mono">{maxLabeledDemos || "—"}</span>
         </div>
         <div className="flex items-center justify-between py-2.5 border-b border-border/40">
          <span className="flex items-center gap-2 text-xs text-muted-foreground"><Layers className="size-3.5" />מספר ניסיונות</span>
          <span className="text-sm font-medium font-mono">{numTrials || "—"}</span>
         </div>
         <div className="flex items-center justify-between py-2.5 border-b border-border/40">
          <span className="flex items-center gap-2 text-xs text-muted-foreground"><Layers className="size-3.5" />בדיקה חלקית</span>
          <span className="text-sm font-medium">{minibatch ? `כן (${minibatchSize})` : "לא"}</span>
         </div>
        </>
       ) : (
        <>
         <div className="flex items-center justify-between py-2.5 border-b border-border/40">
          <span className="flex items-center gap-2 text-xs text-muted-foreground"><Database className="size-3.5" />גודל מדגם לרפלקציה</span>
          <span className="text-sm font-medium font-mono">{reflectionMinibatchSize || "—"}</span>
         </div>
         <div className="flex items-center justify-between py-2.5 border-b border-border/40">
          <span className="flex items-center gap-2 text-xs text-muted-foreground"><Layers className="size-3.5" />מקסימום סבבי הערכה</span>
          <span className="text-sm font-medium font-mono">{maxFullEvals || "—"}</span>
         </div>
         <div className="flex items-center justify-between py-2.5 border-b border-border/40">
          <span className="flex items-center gap-2 text-xs text-muted-foreground"><Shuffle className="size-3.5" />מיזוג מועמדים</span>
          <span className="text-sm font-medium">{useMerge ? "כן" : "לא"}</span>
         </div>
        </>
       )}
      </div>
     )}

     {/* Code */}
     {summaryTab === 4 && (
      <Tabs defaultValue={signatureCode ? "signature" : "metric"} dir="ltr" onValueChange={setSummaryCodeTab}>
       <TabsList className="relative inline-flex w-full rounded-lg bg-muted p-1 gap-1 border-none shadow-none h-auto">
        {signatureCode && metricCode && (
         <div
          className="absolute top-1 bottom-1 w-[calc(50%-6px)] rounded-md bg-[#3D2E22] shadow-sm transition-[inset-inline-start] duration-200 ease-out"
          style={{ insetInlineStart: summaryCodeTab === "signature" ? 4 : "calc(50% + 2px)" }}
         />
        )}
        {signatureCode && <TabsTrigger value="signature" className="relative z-10 rounded-md px-4 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5">חתימה (Signature)</TabsTrigger>}
        {metricCode && <TabsTrigger value="metric" className="relative z-10 rounded-md px-4 py-2 text-sm font-medium cursor-pointer border-none shadow-none bg-transparent data-[state=active]:bg-transparent data-[state=active]:text-white data-[state=active]:shadow-none data-[state=active]:border-none gap-1.5">מטריקה (Metric)</TabsTrigger>}
       </TabsList>
       {signatureCode && (
        <TabsContent value="signature">
         <CodeEditor value={signatureCode} onChange={() => {}} height={`${(Math.min(signatureCode.split("\n").length + 1, 10)) * 19.6 + 8}px`} readOnly />
        </TabsContent>
       )}
       {metricCode && (
        <TabsContent value="metric">
         <CodeEditor value={metricCode} onChange={() => {}} height={`${(Math.min(metricCode.split("\n").length + 1, 10)) * 19.6 + 8}px`} readOnly />
        </TabsContent>
       )}
      </Tabs>
     )}
    </motion.div>
   </AnimatePresence>
  </div>
 </motion.div>
 </>
 );
 })()}
 </div>,
 ];

 /* ════════════════════════════════════════════
 RENDER
 ════════════════════════════════════════════ */

 return (
 <div className="space-y-6 max-w-2xl mx-auto pb-8">
 {/* Breadcrumb */}
 <div className="flex items-center gap-2 text-sm text-muted-foreground">
 <a href="/" className="hover:text-foreground transition-colors">לוח בקרה</a>
 <ChevronLeft className="h-3 w-3"/>
 <span className="text-foreground font-medium">אופטימיזציה חדשה</span>
 </div>

 {/* Step indicator — numbered circles with connecting lines */}
 <div className="relative" data-tutorial="wizard-stepper">
 <div className="flex items-center justify-between">
 {STEPS.map((s, i) => {
 const reachable = i <= maxReachableStep;
 const completed = i < step && validateStep(i);
 const active = i === step;
 return (
 <div key={s.id} className="flex flex-col items-center relative z-10 flex-1">
 <button
 type="button"
 onClick={() => handleTabClick(i)}
 disabled={!reachable && i > step}
 className={cn(
"relative flex items-center justify-center rounded-full transition-all duration-300 cursor-pointer",
"size-9 sm:size-10 text-sm font-semibold",
 active
 ?"bg-primary text-primary-foreground shadow-[0_0_16px_rgba(124,99,80,0.4)] scale-110"
 : completed
 ?"bg-primary/15 text-primary hover:bg-primary/25"
 : reachable
 ?"bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
 :"bg-muted/50 text-muted-foreground/30 cursor-not-allowed"
 )}
 >
 {completed ? <Check className="size-4"/> : i + 1}
 {active && (
 <motion.span
 layoutId="step-ring"
 className="absolute inset-0 rounded-full border-2 border-primary"
 transition={{ type: "spring", stiffness: 400, damping: 30 }}
 />
 )}
 </button>
 <span
 className={cn(
"mt-2 text-[11px] font-medium transition-colors duration-200 hidden sm:block text-center",
 active ?"text-foreground": completed ?"text-primary":"text-muted-foreground"
 )}
 >
 {s.label}
 </span>
 </div>
 );
 })}
 </div>
 {/* Connecting line behind circles */}
 <div className="absolute top-[18px] sm:top-5 inset-x-[10%] h-[2px] bg-muted -z-0 rounded-full">
 <motion.div
 className="h-full rounded-full"
 style={{ background: "linear-gradient(90deg, #c8a882, #a68b6b, #d4b896)"}}
 initial={{ width: 0 }}
 animate={{ width: `${(step / (STEPS.length - 1)) * 100}%` }}
 transition={{ duration: 0.5, ease: [0.2, 0.8, 0.2, 1] }}
 />
 </div>
 </div>

 {/* Animated step content */}
 <div className="relative overflow-hidden pt-[10px]" data-tutorial="submit-wizard">
 <AnimatePresence mode="wait" custom={direction}>
 <motion.div
 key={step}
 custom={direction}
 variants={slideVariants}
 initial="enter"
 animate="center"
 exit="exit"
 transition={{ duration: 0.1 }}
 >
 {stepContent[step]}
 </motion.div>
 </AnimatePresence>
 </div>

 {/* Navigation */}
 {step < STEPS.length - 1 ? (
 <div className="flex items-center justify-between">
 <Button
 variant="outline"
 onClick={goPrev}
 disabled={step === 0}
 className="gap-2 transition-all duration-200 hover:scale-[1.02] active:scale-[0.97]"
 >
 <ChevronRight className="h-4 w-4"/>
 הקודם
 </Button>
 <span className="text-xs text-muted-foreground tabular-nums">
 {step + 1} / {STEPS.length}
 </span>
 <Button
 onClick={handleNext}
 className="gap-2 transition-all duration-200 hover:scale-[1.02] hover:shadow-[0_0_20px_rgba(124,99,80,0.3)] active:scale-[0.97]"
 data-tutorial="wizard-next"
 >
 הבא
 <ChevronLeft className="h-4 w-4"/>
 </Button>
 </div>
 ) : (
 <motion.button
 type="button"
 onClick={handleSubmit}
 disabled={submitting}
 data-tutorial="submit-button"
 animate={{ scale: [1, 1.01, 1] }}
 transition={{ repeat: Infinity, duration: 3, ease: "easeInOut" }}
 className="group relative w-full rounded-2xl bg-primary text-primary-foreground font-semibold text-base pt-5 pb-7 cursor-pointer transition-all duration-300 hover:shadow-[0_0_30px_rgba(61,46,34,0.35)] hover:scale-[1.01] active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed"
 >
 {submitting ? (
 <span className="flex items-center justify-center gap-2">
 <Loader2 className="size-5 animate-spin" />
 שולח...
 </span>
 ) : (
 <div className="flex flex-col items-center gap-4">
 <span>שלח אופטימיזציה</span>
 <div className="flex flex-col items-center -space-y-7 h-0 overflow-visible opacity-70 group-hover:opacity-100 transition-opacity duration-200 [&>svg]:animate-[cascadeDown_1s_ease-in-out_infinite] group-hover:[&>svg]:animate-[cascadeDownHyper_0.5s_ease-out_infinite]">
 <ChevronDown className="size-10 [animation-delay:0s] group-hover:[animation-delay:0s]" />
 <ChevronDown className="size-10 [animation-delay:0.15s] group-hover:[animation-delay:0.08s]" />
 <ChevronDown className="size-10 [animation-delay:0.3s] group-hover:[animation-delay:0.16s]" />
 </div>
 </div>
 )}
 </motion.button>
 )}

 {/* ── Submit splash overlay — portal to body so it covers sidebar + header ── */}
 {typeof document !== "undefined" && createPortal(
 <AnimatePresence>
 {(submitPhase === "splash" || submitPhase === "done") && (
 <motion.div
 className="fixed inset-0 z-[99999] flex items-center justify-center"
 style={{ backgroundColor: "#F0EBE4" }}
 initial={{ y: "-100%" }}
 animate={{ y: 0 }}
 transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
 >
 <motion.div
 initial={{ scale: 0.8, opacity: 0 }}
 animate={{ scale: 1, opacity: 1 }}
 transition={{ delay: 0.3, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
 >
 <AnimatedWordmark size={64} autoMorph morphSpeed={120} />
 </motion.div>
 </motion.div>
 )}
 </AnimatePresence>,
 document.body,
 )}
 </div>
 );
}
