import type {
  ColumnMapping,
  EvalExampleResult,
  GridSearchResult,
  GridSearchRequest,
  OptimizationDatasetResponse,
  OptimizationPayloadResponse,
  OptimizationSubmissionResponse,
  OptimizationStatusResponse,
  PaginatedJobsResponse,
  ProfileDatasetRequest,
  ProfileDatasetResponse,
  QueueStatusResponse,
  RunRequest,
  ServeInfoResponse,
  ServeResponse,
  TemplateResponse,
  ValidateCodeResponse,
} from "@/shared/types/api";
import { formatMsg, msg } from "@/shared/lib/messages";
import { tI18n } from "@/shared/lib/i18n";
import { getRuntimeEnv } from "@/shared/lib/runtime-env";
import { readNdjsonStream, readServerSentEvents, type ServerSentEvent } from "@/shared/lib/sse";

const API = getRuntimeEnv().apiUrl;
const JOB_CACHE_MS = 1000;
const QUEUE_CACHE_MS = 5000;
const SIDEBAR_CACHE_MS = 3000;

if (
  typeof window !== "undefined" &&
  process.env.NODE_ENV === "production" &&
  API.startsWith("http://") &&
  !API.includes("localhost") &&
  !API.includes("127.0.0.1")
) {
  console.error(
    "[Skynet] Production API URL uses HTTP — API keys and tokens will be transmitted in plaintext. " +
      "Set API_URL (or NEXT_PUBLIC_API_URL) to an https:// URL.",
  );
}

const _inflight = new Map<string, Promise<unknown>>();
const _cache = new Map<string, { data: unknown; ts: number }>();
const GET_CACHE_MS = 2000;
// Bumped by invalidateCache. A request that started before an invalidation
// must not write its (possibly-stale) result into _cache or complete a
// post-invalidation dedup — otherwise callers that fetch right after a
// mutation can get pre-mutation data via a still-resolving in-flight promise.
let _cacheGen = 0;
let _authToken: string | undefined;

export function setApiAuthToken(token: string | undefined) {
  _authToken = token;
}

function cachedGet<T>(path: string, maxAge = GET_CACHE_MS): Promise<T> {
  const key = path;
  const startGen = _cacheGen;

  const cached = _cache.get(key);
  if (cached && Date.now() - cached.ts < maxAge) {
    return Promise.resolve(cached.data as T);
  }

  const existing = _inflight.get(key);
  if (existing) return existing as Promise<T>;

  const promise = request<T>(path)
    .then((data) => {
      if (startGen === _cacheGen) _cache.set(key, { data, ts: Date.now() });
      if (_inflight.get(key) === promise) _inflight.delete(key);
      return data;
    })
    .catch((err) => {
      if (_inflight.get(key) === promise) _inflight.delete(key);
      throw err;
    });
  _inflight.set(key, promise);
  return promise;
}

/**
 * Invalidate all cached GET responses whose path includes any of the
 * given substrings. Call after mutations (delete, cancel, rename, pin)
 * so the next fetch hits the server.
 */
export function invalidateCache(...pathSubstrings: string[]) {
  _cacheGen++;
  const matches = (key: string) =>
    pathSubstrings.length === 0 ||
    pathSubstrings.some((s) => key === s || key.startsWith(`${s}/`) || key.startsWith(`${s}?`));
  for (const [key] of _cache) if (matches(key)) _cache.delete(key);
  for (const [key] of _inflight) if (matches(key)) _inflight.delete(key);
}

// Listeners that keep the GET cache honest when mutations fire from
// anywhere in the app (UI buttons, bulk dialogs, or agent MCP tool calls).
// Without these, the 2s GET cache can serve pre-mutation data to sidebar
// and dashboard re-fetches that happen immediately after an event.
if (typeof window !== "undefined") {
  window.addEventListener("optimizations-changed", () =>
    invalidateCache("/optimizations", "/analytics"),
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      ...init,
      headers: {
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...(_authToken ? { Authorization: `Bearer ${_authToken}` } : {}),
        ...init?.headers,
      },
    });
  } catch (err) {
    throw new Error(msg("auto.shared.lib.api.literal.1"), { cause: err });
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(
      parseErrorMessage(text) ?? formatMsg("auto.shared.lib.api.template.1", { p1: res.status }),
    );
  }
  return res.json();
}

/**
 * Extract a human-readable error message from an error response body.
 *
 * Preference order:
 *   1. ``body.code`` + ``body.params`` — re-rendered client-side via
 *      :func:`tI18n` so UI copy comes from the local catalog.
 *   2. ``body.detail`` — the rendered Hebrew string from the server.
 *   3. ``body.error`` — legacy envelope fallback.
 *
 * Returns ``undefined`` when the body is not JSON (e.g. an HTML error page)
 * so the caller can fall back to a status-code template.
 */
function parseErrorMessage(text: string): string | undefined {
  try {
    const body = JSON.parse(text) as {
      code?: string;
      params?: Record<string, unknown>;
      detail?: unknown;
      error?: unknown;
    };
    if (typeof body.code === "string") {
      const translated = tI18n(body.code, body.params);
      if (translated !== body.code) return translated;
    }
    const raw = body.detail ?? body.error;
    if (typeof raw === "string") return raw;
    if (raw != null) return JSON.stringify(raw);
  } catch {
    /* response was not JSON (e.g. HTML error page) */
  }
  return undefined;
}

export function submitRun(payload: RunRequest) {
  return request<OptimizationSubmissionResponse>("/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function submitGridSearch(payload: GridSearchRequest) {
  return request<OptimizationSubmissionResponse>("/grid-search", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listJobs(params?: {
  status?: string;
  username?: string;
  optimization_type?: string;
  limit?: number;
  offset?: number;
}) {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.username) q.set("username", params.username);
  if (params?.optimization_type) q.set("optimization_type", params.optimization_type);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  const qs = q.toString();
  return cachedGet<PaginatedJobsResponse>(`/optimizations${qs ? `?${qs}` : ""}`);
}

export interface OptimizationCounts {
  total: number;
  pending: number;
  validating: number;
  running: number;
  success: number;
  failed: number;
  cancelled: number;
}

export interface UserQuotaOverride {
  username: string;
  quota: number | null;
  updated_at?: string | null;
  updated_by?: string | null;
  effective_quota?: number | null;
  job_count: number;
  last_action?: string | null;
}

export interface UserQuotaAuditEvent {
  id: number;
  actor: string;
  target_username: string;
  action: string;
  old_quota: number | null;
  new_quota: number | null;
  created_at?: string | null;
}

export interface UserQuotaOverridesResponse {
  default_quota: number;
  overrides: UserQuotaOverride[];
  audit_events: UserQuotaAuditEvent[];
}

export function getOptimizationCounts(username?: string) {
  const q = new URLSearchParams();
  if (username) q.set("username", username);
  const qs = q.toString();
  return cachedGet<OptimizationCounts>(`/optimizations/counts${qs ? `?${qs}` : ""}`);
}

export function getUserQuotaOverrides() {
  return request<UserQuotaOverridesResponse>("/admin/quotas");
}

export function setUserQuotaOverride(username: string, quota: number | null) {
  return request<UserQuotaOverride>("/admin/quotas", {
    method: "PUT",
    body: JSON.stringify({ username, quota }),
  });
}

export function deleteUserQuotaOverride(username: string) {
  return request<UserQuotaOverride>(`/admin/quotas/${encodeURIComponent(username)}`, {
    method: "DELETE",
  });
}

export interface DirectoryUserMatch {
  username: string;
  display_name?: string | null;
  email?: string | null;
  source: "db" | "directory";
}

export interface DirectoryUserSearchResponse {
  matches: DirectoryUserMatch[];
}

export function searchAdminUsers(query: string, limit = 10) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return request<DirectoryUserSearchResponse>(`/admin/users/search?${params.toString()}`);
}

export interface DashboardAnalyticsJob {
  optimization_id: string;
  name?: string | null;
  optimizer_name?: string | null;
  model_name?: string | null;
  status: string;
  baseline_test_metric?: number | null;
  optimized_test_metric?: number | null;
  metric_improvement?: number | null;
  elapsed_seconds?: number | null;
  dataset_rows?: number | null;
  optimization_type?: string | null;
  best_pair_label?: string | null;
  created_at?: string | null;
}

export interface DashboardAnalytics {
  filtered_total: number;
  status_counts: Record<string, number>;
  optimizer_counts: Record<string, number>;
  job_type_counts: Record<string, number>;
  model_usage: Array<{ name: string; value: number }>;
  success_count: number;
  failed_count: number;
  running_count: number;
  terminal_count: number;
  success_rate: number;
  avg_improvement: number | null;
  avg_runtime_seconds: number | null;
  total_dataset_rows: number;
  total_pairs_run: number;
  grid_search_count: number;
  single_run_count: number;
  best_improvement: number | null;
  improvement_by_optimizer: Array<{ name: string; average: number; count: number }>;
  runtime_minutes_by_optimizer: Array<{ name: string; average: number; count: number }>;
  top_improvement: DashboardAnalyticsJob[];
  runtime_distribution: DashboardAnalyticsJob[];
  dataset_vs_improvement: DashboardAnalyticsJob[];
  efficiency: DashboardAnalyticsJob[];
  top_jobs_by_improvement: DashboardAnalyticsJob[];
  timeline: Array<{ date: string; count: number }>;
  available_optimizers: string[];
  available_models: string[];
}

export function getDashboardAnalytics(params?: {
  username?: string;
  optimizer?: string;
  model?: string;
  status?: string;
  optimization_id?: string;
  date?: string;
}) {
  const q = new URLSearchParams();
  if (params?.username) q.set("username", params.username);
  if (params?.optimizer) q.set("optimizer", params.optimizer);
  if (params?.model) q.set("model", params.model);
  if (params?.status) q.set("status", params.status);
  if (params?.optimization_id) q.set("optimization_id", params.optimization_id);
  if (params?.date) q.set("date", params.date);
  const qs = q.toString();
  return cachedGet<DashboardAnalytics>(`/analytics/dashboard${qs ? `?${qs}` : ""}`);
}

export function getJob(optimizationId: string) {
  return cachedGet<OptimizationStatusResponse>(`/optimizations/${optimizationId}`, JOB_CACHE_MS);
}

export function getOptimizationPayload(optimizationId: string) {
  return request<OptimizationPayloadResponse>(`/optimizations/${optimizationId}/payload`);
}

export function getOptimizationDataset(optimizationId: string) {
  return request<OptimizationDatasetResponse>(`/optimizations/${optimizationId}/dataset`);
}

export function getTestResults(optimizationId: string) {
  return request<{
    baseline: EvalExampleResult[];
    optimized: EvalExampleResult[];
  }>(`/optimizations/${optimizationId}/test-results`);
}

export async function cancelJob(optimizationId: string) {
  const res = await request<{ optimization_id: string; status: string }>(
    `/optimizations/${optimizationId}/cancel`,
    { method: "POST" },
  );
  invalidateCache("/optimizations");
  return res;
}

export async function deleteJob(optimizationId: string) {
  const res = await request<{ optimization_id: string; deleted: boolean }>(
    `/optimizations/${optimizationId}`,
    { method: "DELETE" },
  );
  invalidateCache("/optimizations");
  return res;
}

export async function deleteGridPair(optimizationId: string, pairIndex: number) {
  const res = await request<GridSearchResult>(
    `/optimizations/${optimizationId}/pair/${pairIndex}`,
    { method: "DELETE" },
  );
  invalidateCache("/optimizations");
  return res;
}

export async function bulkDeleteJobs(optimizationIds: string[]) {
  const res = await request<{
    deleted: string[];
    skipped: Array<{ optimization_id: string; reason: string }>;
  }>("/optimizations/bulk-delete", {
    method: "POST",
    body: JSON.stringify({ optimization_ids: optimizationIds }),
  });
  invalidateCache("/optimizations");
  return res;
}

export async function renameOptimization(optimizationId: string, name: string) {
  const res = await request<{ optimization_id: string; name: string }>(
    `/optimizations/${optimizationId}/name`,
    {
      method: "PATCH",
      body: JSON.stringify({ name }),
    },
  );
  invalidateCache("/optimizations");
  return res;
}

export async function togglePinOptimization(optimizationId: string) {
  const res = await request<{ optimization_id: string; pinned: boolean }>(
    `/optimizations/${optimizationId}/pin`,
    { method: "PATCH" },
  );
  invalidateCache("/optimizations");
  return res;
}

export function profileDataset(payload: ProfileDatasetRequest) {
  return request<ProfileDatasetResponse>("/datasets/profile", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function validateCode(payload: {
  signature_code?: string;
  metric_code?: string;
  column_mapping: ColumnMapping;
  sample_row: Record<string, unknown>;
  optimizer_name?: string;
}) {
  return request<ValidateCodeResponse>("/validate-code", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface ModelProbeRequest {
  signature_code: string;
  metric_code: string;
  module_name: string;
  optimizer_name: string;
  dataset: Array<Record<string, unknown>>;
  column_mapping: ColumnMapping;
  train_count?: number;
  eval_count?: number;
  shuffle?: boolean;
  seed?: number | null;
  model_ids?: string[] | null;
  reflection_model_name?: string | null;
}

export interface ModelProbeStartEvent {
  event: "start";
  total: number;
  train_count: number;
  eval_count: number;
  dataset_size?: number;
}

export interface ProbeScalingFit {
  asymptote: number | null;
  last_score: number | null;
  method: string;
  points: number;
  signal: "strong" | "observed" | "weak";
  message?: string;
}

export interface ModelProbeModelStartEvent {
  event: "model_start";
  position: number;
  model: string;
  label: string;
  provider: string;
}

export interface ModelProbeLogEvent {
  event: "model_log";
  position: number;
  timestamp: string;
  level: string;
  logger: string;
  message: string;
}

export interface ModelProbeTrajectoryEvent {
  event: "model_trajectory";
  position: number;
  point: { step: number; score: number };
  scaling: ProbeScalingFit;
}

export interface ModelProbeResultEvent {
  event: "result";
  position: number;
  model: string;
  label: string;
  provider: string;
  status: "ok" | "error";
  score: number | null;
  scaling: ProbeScalingFit | null;
  duration_ms: number;
  message?: string;
}

export interface ModelProbeCompleteEvent {
  event: "complete";
}

export interface ModelProbeErrorEvent {
  event: "error";
  message: string;
}

export type ModelProbeEvent =
  | ModelProbeStartEvent
  | ModelProbeModelStartEvent
  | ModelProbeLogEvent
  | ModelProbeTrajectoryEvent
  | ModelProbeResultEvent
  | ModelProbeCompleteEvent
  | ModelProbeErrorEvent;

export interface ModelProbeHandlers {
  onStart?: (event: ModelProbeStartEvent) => void;
  onModelStart?: (event: ModelProbeModelStartEvent) => void;
  onLog?: (event: ModelProbeLogEvent) => void;
  onTrajectory?: (event: ModelProbeTrajectoryEvent) => void;
  onResult?: (event: ModelProbeResultEvent) => void;
  onComplete?: (event: ModelProbeCompleteEvent) => void;
  onError?: (message: string) => void;
  signal?: AbortSignal;
}

/** Stream per-model probe scores via POST /models/probe (NDJSON). */
export async function probeModels(
  payload: ModelProbeRequest,
  handlers: ModelProbeHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API}/models/probe`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
      body: JSON.stringify(payload),
      signal: handlers.signal,
    });
  } catch (err) {
    if ((err as Error)?.name === "AbortError") return;
    handlers.onError?.(msg("auto.shared.lib.api.literal.2"));
    return;
  }
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    handlers.onError?.(
      parseErrorMessage(text) ?? formatMsg("auto.shared.lib.api.template.2", { p1: res.status }),
    );
    return;
  }
  const dispatch = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    let data: ModelProbeEvent;
    try {
      data = JSON.parse(trimmed) as ModelProbeEvent;
    } catch {
      return;
    }
    if (data.event === "start") handlers.onStart?.(data);
    else if (data.event === "model_start") handlers.onModelStart?.(data);
    else if (data.event === "model_log") handlers.onLog?.(data);
    else if (data.event === "model_trajectory") handlers.onTrajectory?.(data);
    else if (data.event === "result") handlers.onResult?.(data);
    else if (data.event === "complete") handlers.onComplete?.(data);
    else if (data.event === "error") handlers.onError?.(data.message);
  };
  try {
    await readNdjsonStream(res.body, dispatch);
  } catch (err) {
    if ((err as Error)?.name !== "AbortError") {
      handlers.onError?.(err instanceof Error ? err.message : msg("auto.shared.lib.api.literal.3"));
    }
  }
}

export function getQueueStatus() {
  return cachedGet<QueueStatusResponse>("/queue", QUEUE_CACHE_MS);
}

export interface SidebarJobItem {
  optimization_id: string;
  status: string;
  name?: string | null;
  module_name?: string | null;
  optimizer_name?: string | null;
  model_name?: string | null;
  username?: string | null;
  created_at?: string | null;
  pinned?: boolean;
  optimization_type?: string | null;
  total_pairs?: number | null;
}

export function listJobsSidebar(params?: { username?: string; limit?: number; offset?: number }) {
  const q = new URLSearchParams();
  if (params?.username) q.set("username", params.username);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  const qs = q.toString();
  return cachedGet<{ items: SidebarJobItem[]; total: number }>(
    `/optimizations/sidebar${qs ? `?${qs}` : ""}`,
    SIDEBAR_CACHE_MS,
  );
}

export function getServeInfo(optimizationId: string) {
  return request<ServeInfoResponse>(`/serve/${optimizationId}/info`);
}

export function getPairServeInfo(optimizationId: string, pairIndex: number) {
  return request<ServeInfoResponse>(`/serve/${optimizationId}/pair/${pairIndex}/info`);
}

export function getPairTestResults(optimizationId: string, pairIndex: number) {
  return request<{
    baseline: EvalExampleResult[];
    optimized: EvalExampleResult[];
  }>(`/optimizations/${optimizationId}/pair/${pairIndex}/test-results`);
}

export function serveProgram(optimizationId: string, inputs: Record<string, string>) {
  return request<ServeResponse>(`/serve/${optimizationId}`, {
    method: "POST",
    body: JSON.stringify({ inputs }),
  });
}

export interface StreamServeHandlers {
  onToken: (field: string, chunk: string) => void;
  onFinal: (result: {
    outputs: Record<string, unknown>;
    model_used: string;
    input_fields: string[];
    output_fields: string[];
  }) => void;
  onError: (message: string) => void;
  signal?: AbortSignal;
}

/** Stream program inference via SSE. Calls handlers as tokens arrive. */
export async function serveProgramStream(
  optimizationId: string,
  inputs: Record<string, string>,
  handlers: StreamServeHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API}/serve/${optimizationId}/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ inputs }),
      signal: handlers.signal,
    });
  } catch (err) {
    if ((err as Error)?.name === "AbortError") return;
    handlers.onError(msg("auto.shared.lib.api.literal.4"));
    return;
  }
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    handlers.onError(
      parseErrorMessage(text) ?? formatMsg("auto.shared.lib.api.template.3", { p1: res.status }),
    );
    return;
  }
  const processEvent = ({ event, data }: ServerSentEvent) => {
    if (event === "token") {
      handlers.onToken(String(data.field ?? ""), String(data.chunk ?? ""));
    } else if (event === "final") {
      handlers.onFinal({
        outputs: (data.outputs as Record<string, unknown>) ?? {},
        model_used: String(data.model_used ?? ""),
        input_fields: (data.input_fields as string[]) ?? [],
        output_fields: (data.output_fields as string[]) ?? [],
      });
    } else if (event === "error") {
      handlers.onError(String(data.error ?? msg("auto.shared.lib.api.literal.5")));
    }
  };
  try {
    await readServerSentEvents(res.body, processEvent);
  } catch (err) {
    if ((err as Error)?.name !== "AbortError") {
      handlers.onError(err instanceof Error ? err.message : msg("auto.shared.lib.api.literal.6"));
    }
  }
}

/** Stream pair program inference via SSE. Same as serveProgramStream but for a specific grid pair. */
export async function servePairProgramStream(
  optimizationId: string,
  pairIndex: number,
  inputs: Record<string, string>,
  handlers: StreamServeHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API}/serve/${optimizationId}/pair/${pairIndex}/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ inputs }),
      signal: handlers.signal,
    });
  } catch (err) {
    if ((err as Error)?.name === "AbortError") return;
    handlers.onError(msg("auto.shared.lib.api.literal.7"));
    return;
  }
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    handlers.onError(
      parseErrorMessage(text) ?? formatMsg("auto.shared.lib.api.template.4", { p1: res.status }),
    );
    return;
  }
  const processEvent = ({ event, data }: ServerSentEvent) => {
    if (event === "token") {
      handlers.onToken(String(data.field ?? ""), String(data.chunk ?? ""));
    } else if (event === "final") {
      handlers.onFinal({
        outputs: (data.outputs as Record<string, unknown>) ?? {},
        model_used: String(data.model_used ?? ""),
        input_fields: (data.input_fields as string[]) ?? [],
        output_fields: (data.output_fields as string[]) ?? [],
      });
    } else if (event === "error") {
      handlers.onError(String(data.error ?? msg("auto.shared.lib.api.literal.8")));
    }
  };
  try {
    await readServerSentEvents(res.body, processEvent);
  } catch (err) {
    if ((err as Error)?.name !== "AbortError") {
      handlers.onError(err instanceof Error ? err.message : msg("auto.shared.lib.api.literal.9"));
    }
  }
}

export interface CodeAgentChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface CodeAgentRequest {
  dataset_columns: string[];
  column_roles: Record<string, "input" | "output" | "ignore">;
  column_kinds?: Record<string, "text" | "image">;
  sample_rows: Array<Record<string, unknown>>;
  user_message?: string;
  chat_history?: CodeAgentChatTurn[];
  prior_signature?: string;
  prior_metric?: string;
  prior_signature_validation?: string;
  prior_metric_validation?: string;
  initial_signature?: string;
  initial_metric?: string;
}

export type CodeAgentToolName = "edit_signature" | "edit_metric";

export interface CodeAgentToolStart {
  id: string;
  tool: CodeAgentToolName;
  reason: string;
}

export interface CodeAgentToolEnd {
  id: string;
  tool: CodeAgentToolName;
  status: string;
}

export interface CodeAgentHandlers {
  onSignaturePatch: (chunk: string) => void;
  onMetricPatch: (chunk: string) => void;
  onReasoningPatch?: (chunk: string) => void;
  onMessagePatch?: (chunk: string) => void;
  onSignatureReplace?: (code: string) => void;
  onMetricReplace?: (code: string) => void;
  onToolStart?: (ev: CodeAgentToolStart) => void;
  onToolEnd?: (ev: CodeAgentToolEnd) => void;
  onDone: (result: {
    signature_code: string;
    metric_code: string;
    assistant_message: string;
    model: string | null;
  }) => void;
  onError: (message: string) => void;
  signal?: AbortSignal;
}

/** Stream AI-generated signature + metric code via SSE. */
export async function streamCodeAgent(
  req: CodeAgentRequest,
  handlers: CodeAgentHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API}/optimizations/ai-generate-code`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(req),
      signal: handlers.signal,
    });
  } catch (err) {
    if ((err as Error)?.name === "AbortError") return;
    handlers.onError(msg("auto.shared.lib.api.literal.11"));
    return;
  }
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    handlers.onError(
      parseErrorMessage(text) ?? formatMsg("auto.shared.lib.api.template.5", { p1: res.status }),
    );
    return;
  }
  const processEvent = ({ event, data }: ServerSentEvent) => {
    if (event === "signature_patch") {
      handlers.onSignaturePatch(String(data.chunk ?? ""));
    } else if (event === "metric_patch") {
      handlers.onMetricPatch(String(data.chunk ?? ""));
    } else if (event === "reasoning_patch") {
      handlers.onReasoningPatch?.(String(data.chunk ?? ""));
    } else if (event === "message_patch") {
      handlers.onMessagePatch?.(String(data.chunk ?? ""));
    } else if (event === "signature_replace") {
      handlers.onSignatureReplace?.(String(data.code ?? ""));
    } else if (event === "metric_replace") {
      handlers.onMetricReplace?.(String(data.code ?? ""));
    } else if (event === "tool_start") {
      const tool = String(data.tool ?? "");
      if (tool === "edit_signature" || tool === "edit_metric") {
        handlers.onToolStart?.({
          id: String(data.id ?? ""),
          tool,
          reason: String(data.reason ?? ""),
        });
      }
    } else if (event === "tool_end") {
      const tool = String(data.tool ?? "");
      if (tool === "edit_signature" || tool === "edit_metric") {
        handlers.onToolEnd?.({
          id: String(data.id ?? ""),
          tool,
          status: String(data.status ?? "ok"),
        });
      }
    } else if (event === "done") {
      const rawModel = data.model;
      handlers.onDone({
        signature_code: String(data.signature_code ?? ""),
        metric_code: String(data.metric_code ?? ""),
        assistant_message: String(data.assistant_message ?? ""),
        model: typeof rawModel === "string" && rawModel.length > 0 ? rawModel : null,
      });
    } else if (event === "error") {
      handlers.onError(String(data.error ?? msg("auto.shared.lib.api.literal.12")));
    }
  };
  try {
    await readServerSentEvents(res.body, processEvent);
  } catch (err) {
    if ((err as Error)?.name !== "AbortError") {
      handlers.onError(err instanceof Error ? err.message : msg("auto.shared.lib.api.literal.10"));
    }
  }
}

let _templatesCache: TemplateResponse[] | null = null;
let _templatesFlight: Promise<TemplateResponse[]> | null = null;

export function listTemplates(username?: string): Promise<TemplateResponse[]> {
  if (!username) {
    if (_templatesCache) return Promise.resolve(_templatesCache);
    if (_templatesFlight) return _templatesFlight;
    _templatesFlight = request<TemplateResponse[]>("/templates")
      .then((r) => {
        _templatesCache = r;
        return r;
      })
      .finally(() => {
        _templatesFlight = null;
      });
    return _templatesFlight;
  }
  const q = `?username=${encodeURIComponent(username)}`;
  return request<TemplateResponse[]>(`/templates${q}`);
}

if (typeof window !== "undefined") {
  listTemplates().catch(() => {});
}

function _invalidateTemplatesCache() {
  _templatesCache = null;
}

// Agent-driven template mutations (update/apply) fire ``templates-changed``;
// other tabs and dialogs fire the same event. Invalidate the cache globally
// so the next ``listTemplates()`` call re-fetches from the server.
if (typeof window !== "undefined") {
  window.addEventListener("templates-changed", _invalidateTemplatesCache);
}

export async function createTemplate(payload: {
  name: string;
  description?: string;
  username: string;
  config: Record<string, unknown>;
}) {
  const result = await request<TemplateResponse>("/templates", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  _invalidateTemplatesCache();
  return result;
}

export async function deleteTemplate(templateId: string, username: string) {
  const result = await request<{ template_id: string; deleted: boolean }>(
    `/templates/${templateId}?username=${encodeURIComponent(username)}`,
    { method: "DELETE" },
  );
  _invalidateTemplatesCache();
  return result;
}

export interface PublicDashboardPoint {
  optimization_id: string;
  optimization_type: string | null;
  winning_model: string | null;
  baseline_metric: number | null;
  optimized_metric: number | null;
  summary_text: string | null;
  task_name: string | null;
  module_name: string | null;
  optimizer_name: string | null;
  created_at: string | null;
  x: number;
  y: number;
  cluster_levels: number[];
}

export interface PublicDashboardMeta {
  count: number;
  level_cluster_counts: number[];
}

export interface PublicDashboardResponse {
  points: PublicDashboardPoint[];
  meta: PublicDashboardMeta;
}

export function getPublicDashboard(): Promise<PublicDashboardResponse> {
  return cachedGet("/dashboard/public", 15000);
}
