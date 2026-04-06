import type {
  RunRequest,
  GridSearchRequest,
  JobSubmissionResponse,
  JobStatusResponse,
  PaginatedJobsResponse,
  JobPayloadResponse,
  ServeInfoResponse,
  ServeResponse,
} from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  return request<JobSubmissionResponse>("/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function submitGridSearch(payload: GridSearchRequest) {
  return request<JobSubmissionResponse>("/grid-search", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/* ── Job Management ── */

export function listJobs(params?: {
  status?: string;
  username?: string;
  job_type?: string;
  limit?: number;
  offset?: number;
}) {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.username) q.set("username", params.username);
  if (params?.job_type) q.set("job_type", params.job_type);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  const qs = q.toString();
  return request<PaginatedJobsResponse>(`/jobs${qs ? `?${qs}` : ""}`);
}

export function getJob(jobId: string) {
  return request<JobStatusResponse>(`/jobs/${jobId}`);
}

export function getJobPayload(jobId: string) {
  return request<JobPayloadResponse>(`/jobs/${jobId}/payload`);
}

export function cancelJob(jobId: string) {
  return request<{ job_id: string; status: string }>(`/jobs/${jobId}/cancel`, { method: "POST" });
}

export function deleteJob(jobId: string) {
  return request<{ job_id: string; deleted: boolean }>(`/jobs/${jobId}`, { method: "DELETE" });
}

export function renameJob(jobId: string, name: string) {
  return request<{ job_id: string; name: string }>(`/jobs/${jobId}/name`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function togglePinJob(jobId: string) {
  return request<{ job_id: string; pinned: boolean }>(`/jobs/${jobId}/pin`, { method: "PATCH" });
}

export function toggleArchiveJob(jobId: string) {
  return request<{ job_id: string; archived: boolean }>(`/jobs/${jobId}/archive`, { method: "PATCH" });
}

/* ── Code Validation ── */

export function validateCode(payload: {
  signature_code?: string;
  metric_code?: string;
  column_mapping: import("./types").ColumnMapping;
  sample_row: Record<string, unknown>;
  optimizer_name?: string;
}) {
  return request<import("./types").ValidateCodeResponse>("/validate-code", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/* ── System Status ── */

export function getQueueStatus() {
  return request<import("./types").QueueStatusResponse>("/queue");
}

export function getHealth() {
  return request<import("./types").HealthResponse>("/health");
}

/* ── Serving ── */

export function getServeInfo(jobId: string) {
  return request<ServeInfoResponse>(`/serve/${jobId}/info`);
}

export function serveProgram(jobId: string, inputs: Record<string, string>) {
  return request<ServeResponse>(`/serve/${jobId}`, {
    method: "POST",
    body: JSON.stringify({ inputs }),
  });
}

export interface StreamServeHandlers {
  onToken: (field: string, chunk: string) => void;
  onFinal: (result: { outputs: Record<string, unknown>; model_used: string; input_fields: string[]; output_fields: string[] }) => void;
  onError: (message: string) => void;
  signal?: AbortSignal;
}

/** Stream program inference via SSE. Calls handlers as tokens arrive. */
export async function serveProgramStream(
  jobId: string,
  inputs: Record<string, string>,
  handlers: StreamServeHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API}/serve/${jobId}/stream`, {
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
    } catch { /* not json */ }
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
    try { data = JSON.parse(dataLines.join("\n")); } catch { return; }
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

/* ── Templates ── */

/* ── Templates (with prefetch cache) ── */

let _templatesCache: import("./types").TemplateResponse[] | null = null;
let _templatesFlight: Promise<import("./types").TemplateResponse[]> | null = null;

export function listTemplates(username?: string): Promise<import("./types").TemplateResponse[]> {
  // Only cache the "all templates" call (no username filter)
  if (!username) {
    if (_templatesCache) return Promise.resolve(_templatesCache);
    if (_templatesFlight) return _templatesFlight;
    _templatesFlight = request<import("./types").TemplateResponse[]>("/templates").then((r) => {
      _templatesCache = r;
      _templatesFlight = null;
      return r;
    });
    return _templatesFlight;
  }
  const q = `?username=${encodeURIComponent(username)}`;
  return request<import("./types").TemplateResponse[]>(`/templates${q}`);
}

/** Prefetch templates on module load so they're ready when submit page opens. */
listTemplates().catch(() => {});

function _invalidateTemplatesCache() { _templatesCache = null; }

export async function createTemplate(payload: { name: string; description?: string; username: string; config: Record<string, unknown> }) {
  const result = await request<import("./types").TemplateResponse>("/templates", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  _invalidateTemplatesCache();
  return result;
}

export async function deleteTemplate(templateId: string, username: string) {
  const result = await request<{ template_id: string; deleted: boolean }>(`/templates/${templateId}?username=${encodeURIComponent(username)}`, { method: "DELETE" });
  _invalidateTemplatesCache();
  return result;
}

