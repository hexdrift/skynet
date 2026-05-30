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
  ValidateCodeResponse,
  ValidateDatasetRequest,
  ValidateDatasetResponse,
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

let _authTokenRefresher: (() => Promise<string | undefined>) | undefined;

/**
 * Register an async refresher that mints a fresh backend bearer token (e.g.
 * by re-fetching the NextAuth session). Used to recover from a 401 when the
 * cached token expired while a tab sat idle during a long optimization run.
 */
export function setApiAuthTokenRefresher(
  refresher: (() => Promise<string | undefined>) | undefined,
) {
  _authTokenRefresher = refresher;
}

/**
 * Run a one-shot bearer-token refresh after a 401 and hand back a fresh
 * token to retry with. Returns `undefined` when there is no refresher, the
 * refresh failed, or the refreshed token is unchanged (so the caller should
 * surface the original 401 instead of looping).
 */
async function refreshAuthTokenOn401(): Promise<string | undefined> {
  if (!_authTokenRefresher) return undefined;
  let fresh: string | undefined;
  try {
    fresh = await _authTokenRefresher();
  } catch {
    return undefined;
  }
  if (!fresh || fresh === _authToken) return undefined;
  _authToken = fresh;
  return fresh;
}

/**
 * `fetch` for raw SSE/NDJSON callers that can't go through `request`.
 * Attaches the cached bearer token and, on a 401, transparently refreshes
 * the token and retries once — the in-memory token has a short TTL and goes
 * stale while a long run keeps the tab idle/backgrounded.
 */
export async function fetchWithAuthRetry(url: string, init: RequestInit): Promise<Response> {
  const send = (token: string | undefined) =>
    fetch(url, {
      ...init,
      headers: {
        ...(init.headers as Record<string, string> | undefined),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
  const res = await send(_authToken);
  if (res.status !== 401) return res;
  const fresh = await refreshAuthTokenOn401();
  if (!fresh) return res;
  return send(fresh);
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
  const send = (token: string | undefined) =>
    fetch(`${API}${path}`, {
      ...init,
      headers: {
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    });
  let res: Response;
  try {
    res = await send(_authToken);
    if (res.status === 401) {
      const fresh = await refreshAuthTokenOn401();
      if (fresh) res = await send(fresh);
    }
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

export interface ApiTokenInfo {
  last4: string;
  created_at: string;
  last_used_at: string | null;
}

export interface ApiTokenCreated {
  token: string;
  last4: string;
  created_at: string;
}

/** Fetch metadata for the caller's active API token, or ``null`` if none exists. */
export function getApiToken() {
  return request<ApiTokenInfo | null>("/settings/api-token");
}

/** Generate (or rotate) the caller's API token; the plaintext is returned once. */
export function generateApiToken() {
  return request<ApiTokenCreated>("/settings/api-token", { method: "POST" });
}

/** Revoke the caller's active API token. Idempotent; the route returns 204. */
export async function revokeApiToken(): Promise<void> {
  const res = await fetchWithAuthRetry(`${API}/settings/api-token`, { method: "DELETE" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(
      parseErrorMessage(text) ?? formatMsg("auto.shared.lib.api.template.1", { p1: res.status }),
    );
  }
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

/** Member tier role on a shared optimization (full-access tiers). */
export type ShareRole = "viewer" | "editor" | "owner";

/** General-access policy on the active share link. */
export type GeneralAccess = "restricted" | "anyone";

/** One invited member of an optimization (username + tier role). */
export interface SharingMember {
  username: string;
  role: ShareRole;
}

/** Owner/editor-facing sharing config for one optimization. */
export interface SharingState {
  general_access: GeneralAccess;
  token: string | null;
  share_path: string | null;
  owner: string | null;
  members: SharingMember[];
}

/** Envelope for ``GET /users/search`` — matching distinct usernames. */
export interface UserSearchResponse {
  usernames: string[];
}

/**
 * Composite, access-gated read behind a ``/share/<token>`` page.
 *
 * `role` is the caller's effective access: `"view"` (anonymous, read-only,
 * owner hidden, no inference/clone) or `viewer`/`editor`/`owner` (real owner
 * shown, inference + clone enabled). `serve_info` is only populated for
 * viewer+; it is `null` for the anonymous `view` role.
 */
export interface SharedOptimizationData {
  optimization_id: string;
  role: "view" | ShareRole;
  owner: string | null;
  status: OptimizationStatusResponse;
  payload: Record<string, unknown>;
  dataset: OptimizationDatasetResponse | null;
  test_results: { baseline: EvalExampleResult[]; optimized: EvalExampleResult[] } | null;
  serve_info: ServeInfoResponse | null;
}

/** Fetch the current sharing config (general access + members) for an optimization. */
export function getSharing(optimizationId: string) {
  return request<SharingState>(`/optimizations/${optimizationId}/sharing`);
}

/** Set the general-access policy (restricted vs anyone-with-link); mints a link if needed. */
export function putSharing(optimizationId: string, body: { general_access: GeneralAccess }) {
  return request<SharingState>(`/optimizations/${optimizationId}/sharing`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

/** Invite a user (add or replace a member grant). */
export function addShareMember(
  optimizationId: string,
  body: { username: string; role: ShareRole },
) {
  return request<SharingState>(`/optimizations/${optimizationId}/sharing/members`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Change an existing member's tier role. */
export function updateShareMember(
  optimizationId: string,
  username: string,
  body: { role: ShareRole },
) {
  return request<SharingState>(
    `/optimizations/${optimizationId}/sharing/members/${encodeURIComponent(username)}`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
}

/** Remove a member's grant from the optimization. */
export function removeShareMember(optimizationId: string, username: string) {
  return request<SharingState>(
    `/optimizations/${optimizationId}/sharing/members/${encodeURIComponent(username)}`,
    { method: "DELETE" },
  );
}

/** Autocomplete distinct known usernames by prefix (any authed caller). */
export function searchUsers(q: string) {
  return request<UserSearchResponse>(`/users/search?q=${encodeURIComponent(q)}`);
}

/** Public read — no auth token required; the token in the path is the capability. */
export function getSharedOptimization(token: string) {
  return request<SharedOptimizationData>(`/share/${encodeURIComponent(token)}`);
}

/**
 * Run one inference through the owner's stored model on a shared optimization.
 * Requires an effective role of viewer or higher (403 for anonymous `view`).
 */
export function serveSharedOptimization(token: string, inputs: Record<string, string>) {
  return request<ServeResponse>(`/share/${encodeURIComponent(token)}/serve`, {
    method: "POST",
    body: JSON.stringify({ inputs }),
  });
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

export function stageDatasetForAgent(payload: {
  dataset: Array<Record<string, unknown>>;
  dataset_filename: string;
}) {
  return request<{ staged_dataset_id: string; row_count: number }>(
    "/datasets/stage-for-agent",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export interface StagedDatasetResponse {
  staged_dataset_id: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  row_count: number;
}

/**
 * Fetch the rows a chat-side upload staged, by id, so the /submit wizard can
 * mirror the exact dataset the agent is working with. The shared wizard state
 * only carries the opaque `staged_dataset_id`; this materialises its rows.
 */
export function getStagedDataset(stagedDatasetId: string) {
  return request<StagedDatasetResponse>(
    `/datasets/staged/${encodeURIComponent(stagedDatasetId)}`,
  );
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

export function validateDataset(payload: ValidateDatasetRequest) {
  return request<ValidateDatasetResponse>("/datasets/validate", {
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
    res = await fetchWithAuthRetry(`${API}/models/probe`, {
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
  completed_pairs?: number | null;
  failed_pairs?: number | null;
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
    res = await fetchWithAuthRetry(`${API}/serve/${optimizationId}/stream`, {
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
    res = await fetchWithAuthRetry(`${API}/serve/${optimizationId}/pair/${pairIndex}/stream`, {
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
    /**
     * Seed-path validation outcome. The seed runner validates (and repairs)
     * the generated code; these flags are absent on the chat path (where
     * ``edit_signature``/``edit_metric`` already validate every edit), so a
     * missing flag is treated as valid.
     */
    signatureValid?: boolean;
    metricValid?: boolean;
    validationError?: string | null;
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
    res = await fetchWithAuthRetry(`${API}/optimizations/ai-generate-code`, {
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
        // Absent on the chat path → treat as valid; the seed path sends
        // explicit booleans after its validate-and-repair pass.
        signatureValid: data.signature_valid !== false,
        metricValid: data.metric_valid !== false,
        validationError:
          typeof data.validation_error === "string" ? data.validation_error : null,
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
  siblings: string[];
  task_fingerprint: string | null;
  compare_fingerprint: string | null;
  has_coordinates?: boolean;
}

export interface PublicDashboardResponse {
  points: PublicDashboardPoint[];
}

export function getPublicDashboard(): Promise<PublicDashboardResponse> {
  return cachedGet("/dashboard/public", 15000);
}

export type SearchSort = "relevance" | "recent" | "gain";

export interface SearchFilters {
  query?: string;
  models?: string[];
  optimizers?: string[];
  optimization_types?: string[];
  date_from?: string; // ISO date (YYYY-MM-DD)
  date_to?: string; // ISO date (YYYY-MM-DD)
  sort?: SearchSort;
  page?: number;
  size?: number;
  /**
   * Scope the search to the caller's own jobs (including private rows). The
   * backend requires the bearer token to match this username, so only the
   * logged-in user can set this to their own name.
   */
  owner_username?: string;
}

export interface SearchResult {
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
  relevance: number | null;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
  matched_ids: string[];
  /** Which backend branch served the response — drives per-row source badges. */
  search_type?: "semantic" | "lexical";
}

export function searchPublicDashboard(
  filters: SearchFilters,
  init?: { signal?: AbortSignal },
): Promise<SearchResponse> {
  return request<SearchResponse>("/dashboard/search", {
    method: "POST",
    body: JSON.stringify(filters),
    signal: init?.signal,
  });
}
