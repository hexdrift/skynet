import type {
  ApprovalResolvedPayload,
  ChatTurn,
  PendingApprovalPayload,
  ToolEndPayload,
  ToolStartPayload,
  TrustMode,
  WizardState,
} from "./types";
import { formatMsg, msg } from "@/shared/lib/messages";
import { getRuntimeEnv } from "@/shared/lib/runtime-env";

const API = getRuntimeEnv().apiUrl;

export interface GeneralistAgentRequest {
  user_message: string;
  chat_history: ChatTurn[];
  wizard_state: WizardState;
  trust_mode: TrustMode;
}

export interface GeneralistAgentHandlers {
  onReasoningPatch?: (chunk: string) => void;
  onToolStart?: (ev: ToolStartPayload) => void;
  onToolEnd?: (ev: ToolEndPayload) => void;
  onStatusPatch?: (label: string) => void;
  onPendingApproval?: (ev: PendingApprovalPayload) => void;
  onApprovalResolved?: (ev: ApprovalResolvedPayload) => void;
  onMessagePatch?: (chunk: string) => void;
  onDone: (result: { assistant_message: string; model: string | null }) => void;
  onError: (message: string) => void;
  signal?: AbortSignal;
}

/** Stream generalist-agent events via SSE. Mirrors `streamCodeAgent`. */
export async function streamGeneralistAgent(
  req: GeneralistAgentRequest,
  handlers: GeneralistAgentHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API}/optimizations/generalist-agent`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(req),
      signal: handlers.signal,
    });
  } catch (err) {
    if ((err as Error)?.name === "AbortError") return;
    handlers.onError(msg("auto.features.agent.panel.lib.stream.literal.1"));
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
    handlers.onError(
      detail ?? formatMsg("auto.features.agent.panel.lib.stream.template.1", { p1: res.status }),
    );
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
    if (!dataLines.length) return;
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(dataLines.join("\n"));
    } catch {
      return;
    }
    switch (event) {
      case "reasoning_patch":
        handlers.onReasoningPatch?.(String(data.chunk ?? ""));
        break;
      case "tool_start":
        handlers.onToolStart?.({
          id: String(data.id ?? ""),
          tool: String(data.tool ?? ""),
          reason: String(data.reason ?? ""),
          arguments: (data.arguments as Record<string, unknown>) ?? {},
        });
        break;
      case "tool_end":
        handlers.onToolEnd?.({
          id: String(data.id ?? ""),
          tool: String(data.tool ?? ""),
          status: String(data.status ?? "ok"),
          result: data.result,
        });
        break;
      case "status_patch":
        handlers.onStatusPatch?.(String(data.label ?? ""));
        break;
      case "pending_approval":
        handlers.onPendingApproval?.({
          id: String(data.id ?? ""),
          tool: String(data.tool ?? ""),
          arguments: (data.arguments as Record<string, unknown>) ?? {},
        });
        break;
      case "approval_resolved":
        handlers.onApprovalResolved?.({
          id: String(data.id ?? ""),
          tool: String(data.tool ?? ""),
          approved: Boolean(data.approved),
        });
        break;
      case "message_patch":
        handlers.onMessagePatch?.(String(data.chunk ?? ""));
        break;
      case "done": {
        const rawModel = data.model;
        handlers.onDone({
          assistant_message: String(data.assistant_message ?? ""),
          model: typeof rawModel === "string" && rawModel.length > 0 ? rawModel : null,
        });
        break;
      }
      case "error":
        handlers.onError(
          String(data.error ?? msg("auto.features.agent.panel.lib.stream.literal.2")),
        );
        break;
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
      handlers.onError(
        err instanceof Error ? err.message : msg("auto.features.agent.panel.lib.stream.literal.3"),
      );
    }
  }
}

/** Resolve a pending approval via the companion confirm endpoint. */
export async function confirmGeneralistApproval(
  callId: string,
  approved: boolean,
): Promise<boolean> {
  let res: Response;
  try {
    res = await fetch(`${API}/optimizations/generalist-agent/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ call_id: callId, approved }),
    });
  } catch {
    return false;
  }
  if (!res.ok) return false;
  const data = (await res.json().catch(() => ({ resolved: false }))) as { resolved?: boolean };
  return Boolean(data.resolved);
}
