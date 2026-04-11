import type {
  RunRequest,
  GridSearchRequest,
  OptimizationSubmissionResponse,
  OptimizationStatusResponse,
  PaginatedJobsResponse,
  OptimizationPayloadResponse,
  ServeInfoResponse,
  ServeResponse,
} from "@/shared/types/api";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/* ── HTTPS enforcement for production ── */
if (
  typeof window !== "undefined" &&
  process.env.NODE_ENV === "production" &&
  API.startsWith("http://") &&
  !API.includes("localhost") &&
  !API.includes("127.0.0.1")
) {
  console.error(
    "[Skynet] ⚠️ Production API URL uses HTTP — API keys and tokens will be transmitted in plaintext. " +
      "Set NEXT_PUBLIC_API_URL to an https:// URL.",
  );
}

/* ── In-flight dedup + short-lived GET cache ── */
const _inflight = new Map<string, Promise<unknown>>();
const _cache = new Map<string, { data: unknown; ts: number }>();
const GET_CACHE_MS = 2000;

function cachedGet<T>(path: string, maxAge = GET_CACHE_MS): Promise<T> {
  const key = path;

  const cached = _cache.get(key);
  if (cached && Date.now() - cached.ts < maxAge) {
    return Promise.resolve(cached.data as T);
  }

  // Dedup inflight requests to same path
  const existing = _inflight.get(key);
  if (existing) return existing as Promise<T>;

  const promise = request<T>(path)
    .then((data) => {
      _cache.set(key, { data, ts: Date.now() });
      _inflight.delete(key);
      return data;
    })
    .catch((err) => {
      _inflight.delete(key);
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
  for (const [key] of _cache) {
    if (pathSubstrings.length === 0 || pathSubstrings.some((s) => key.includes(s))) {
      _cache.delete(key);
    }
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      ...init,
      headers: { ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    });
  } catch {
    throw new Error("לא ניתן להתחבר לשרת. ודא שהשרת פועל.");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let detail: string | undefined;
    try {
      const body = JSON.parse(text);
      detail = body.detail ?? body.error;
    } catch {
      /* response was not JSON (e.g. HTML error page) */
    }
    throw new Error(detail ?? `שגיאת שרת: ${res.status}`);
  }
  return res.json();
}

/* ── Job Submission ── */

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

/* ── Job Management ── */

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

export function getOptimizationCounts(username?: string) {
  const q = new URLSearchParams();
  if (username) q.set("username", username);
  const qs = q.toString();
  return cachedGet<OptimizationCounts>(`/optimizations/counts${qs ? `?${qs}` : ""}`);
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
  model_usage: { name: string; value: number }[];
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
  improvement_by_optimizer: { name: string; average: number; count: number }[];
  runtime_minutes_by_optimizer: { name: string; average: number; count: number }[];
  top_improvement: DashboardAnalyticsJob[];
  runtime_distribution: DashboardAnalyticsJob[];
  dataset_vs_improvement: DashboardAnalyticsJob[];
  efficiency: DashboardAnalyticsJob[];
  top_jobs_by_improvement: DashboardAnalyticsJob[];
  timeline: { date: string; count: number }[];
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
  return cachedGet<OptimizationStatusResponse>(`/optimizations/${optimizationId}`, 1000);
}

export function getOptimizationPayload(optimizationId: string) {
  return request<OptimizationPayloadResponse>(`/optimizations/${optimizationId}/payload`);
}

export function getOptimizationDataset(optimizationId: string) {
  return request<import("@/shared/types/api").OptimizationDatasetResponse>(
    `/optimizations/${optimizationId}/dataset`,
  );
}

export function evaluateExamples(
  optimizationId: string,
  indices: number[],
  programType: "optimized" | "baseline",
) {
  return request<{ results: import("@/shared/types/api").EvalExampleResult[]; program_type: string }>(
    `/optimizations/${optimizationId}/evaluate-examples`,
    {
      method: "POST",
      body: JSON.stringify({ indices, program_type: programType }),
    },
  );
}

export function getTestResults(optimizationId: string) {
  return request<{
    baseline: import("@/shared/types/api").EvalExampleResult[];
    optimized: import("@/shared/types/api").EvalExampleResult[];
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

export async function bulkDeleteJobs(optimizationIds: string[]) {
  const res = await request<{
    deleted: string[];
    skipped: { optimization_id: string; reason: string }[];
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

export async function toggleArchiveOptimization(optimizationId: string) {
  const res = await request<{ optimization_id: string; archived: boolean }>(
    `/optimizations/${optimizationId}/archive`,
    { method: "PATCH" },
  );
  invalidateCache("/optimizations");
  return res;
}

/* ── Code Validation ── */

export function validateCode(payload: {
  signature_code?: string;
  metric_code?: string;
  column_mapping: import("@/shared/types/api").ColumnMapping;
  sample_row: Record<string, unknown>;
  optimizer_name?: string;
}) {
  return request<import("@/shared/types/api").ValidateCodeResponse>("/validate-code", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/* ── System Status ── */

export function getQueueStatus() {
  return cachedGet<import("@/shared/types/api").QueueStatusResponse>("/queue", 5000);
}

export function getHealth() {
  return request<import("@/shared/types/api").HealthResponse>("/health");
}

/* ── Sidebar (lightweight) ── */

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
    3000,
  );
}

/* ── Serving ── */

export function getServeInfo(optimizationId: string) {
  return request<ServeInfoResponse>(`/serve/${optimizationId}/info`);
}

export function getPairServeInfo(optimizationId: string, pairIndex: number) {
  return request<ServeInfoResponse>(`/serve/${optimizationId}/pair/${pairIndex}/info`);
}

export function getPairTestResults(optimizationId: string, pairIndex: number) {
  return request<{
    baseline: import("@/shared/types/api").EvalExampleResult[];
    optimized: import("@/shared/types/api").EvalExampleResult[];
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
    handlers.onError("לא ניתן להתחבר לשרת. ודא שהשרת פועל.");
    return;
  }
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    let detail: string | undefined;
    try {
      const raw = JSON.parse(text).detail;
      // 422 responses send an array of validation-error objects — coerce to string
      detail = typeof raw === "string" ? raw : raw != null ? JSON.stringify(raw) : undefined;
    } catch {
      /* not json */
    }
    handlers.onError(detail ?? `שגיאת שרת: ${res.status}`);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  const processEvent = (raw: string) => {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of raw.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length === 0) return;
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(dataLines.join("\n"));
    } catch {
      return;
    }
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
      handlers.onError(String(data.error ?? "שגיאה בהרצת התוכנית"));
    }
  };
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) {
        // Flush any trailing event without double-newline terminator
        if (buf.trim()) processEvent(buf);
        break;
      }
      buf += decoder.decode(value, { stream: true });
      let sepIdx: number;
      while ((sepIdx = buf.indexOf("\n\n")) !== -1) {
        const raw = buf.slice(0, sepIdx);
        buf = buf.slice(sepIdx + 2);
        processEvent(raw);
      }
    }
  } catch (err) {
    if ((err as Error)?.name !== "AbortError") {
      handlers.onError(err instanceof Error ? err.message : "שגיאה בהרצת התוכנית");
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
    handlers.onError("לא ניתן להתחבר לשרת. ודא שהשרת פועל.");
    return;
  }
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    let detail: string | undefined;
    try {
      const raw = JSON.parse(text).detail;
      detail = typeof raw === "string" ? raw : raw != null ? JSON.stringify(raw) : undefined;
    } catch {
      /* not json */
    }
    handlers.onError(detail ?? `שגיאת שרת: ${res.status}`);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  const processEvent = (raw: string) => {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of raw.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length === 0) return;
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(dataLines.join("\n"));
    } catch {
      return;
    }
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
      handlers.onError(String(data.error ?? "שגיאה בהרצת התוכנית"));
    }
  };
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) {
        if (buf.trim()) processEvent(buf);
        break;
      }
      buf += decoder.decode(value, { stream: true });
      let sepIdx: number;
      while ((sepIdx = buf.indexOf("\n\n")) !== -1) {
        const raw = buf.slice(0, sepIdx);
        buf = buf.slice(sepIdx + 2);
        processEvent(raw);
      }
    }
  } catch (err) {
    if ((err as Error)?.name !== "AbortError") {
      handlers.onError(err instanceof Error ? err.message : "שגיאה בהרצת התוכנית");
    }
  }
}

/* ── Templates ── */

/* ── Templates (with prefetch cache) ── */

let _templatesCache: import("@/shared/types/api").TemplateResponse[] | null = null;
let _templatesFlight: Promise<import("@/shared/types/api").TemplateResponse[]> | null = null;

export function listTemplates(username?: string): Promise<import("@/shared/types/api").TemplateResponse[]> {
  // Only cache the "all templates" call (no username filter)
  if (!username) {
    if (_templatesCache) return Promise.resolve(_templatesCache);
    if (_templatesFlight) return _templatesFlight;
    _templatesFlight = request<import("@/shared/types/api").TemplateResponse[]>("/templates").then((r) => {
      _templatesCache = r;
      _templatesFlight = null;
      return r;
    });
    return _templatesFlight;
  }
  const q = `?username=${encodeURIComponent(username)}`;
  return request<import("@/shared/types/api").TemplateResponse[]>(`/templates${q}`);
}

/** Prefetch templates on module load so they're ready when submit page opens. */
listTemplates().catch(() => {});

function _invalidateTemplatesCache() {
  _templatesCache = null;
}

export async function createTemplate(payload: {
  name: string;
  description?: string;
  username: string;
  config: Record<string, unknown>;
}) {
  const result = await request<import("@/shared/types/api").TemplateResponse>("/templates", {
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
