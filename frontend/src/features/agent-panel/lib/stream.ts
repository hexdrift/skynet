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
import { readServerSentEvents } from "@/shared/lib/sse";
import { dispatchGeneralistEvent } from "./stream-events";
import { fetchWithAuthRetry } from "@/shared/lib/api";

// Resolve lazily — a module-load const races the injected window.__SKYNET_ENV__
// and freezes the build-time localhost fallback. See shared/lib/api.ts.
const apiBase = () => getRuntimeEnv().apiUrl;

export interface GeneralistAgentRequest {
  user_message: string;
  chat_history: ChatTurn[];
  wizard_state: WizardState;
  trust_mode: TrustMode;
  conversation_id?: string | null;
  regenerate?: boolean;
  locale?: string;
}

export interface ConversationMetaPayload {
  conversation_id: string;
  title: string;
}

export interface GeneralistAgentHandlers {
  onReasoningPatch?: (chunk: string) => void;
  onToolStart?: (ev: ToolStartPayload) => void;
  onToolEnd?: (ev: ToolEndPayload) => void;
  onPendingApproval?: (ev: PendingApprovalPayload) => void;
  onApprovalResolved?: (ev: ApprovalResolvedPayload) => void;
  onMessagePatch?: (chunk: string) => void;
  onConversationMeta?: (ev: ConversationMetaPayload) => void;
  onDone: (result: {
    assistant_message: string;
    /** Raw `stats` block; read it with `parseTurnStats`. */
    stats: unknown;
  }) => void;
  onError: (message: string, code?: string) => void;
  signal?: AbortSignal;
}

/** Stream generalist-agent events via SSE. Mirrors `streamCodeAgent`. */
export async function streamGeneralistAgent(
  req: GeneralistAgentRequest,
  handlers: GeneralistAgentHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetchWithAuthRetry(`${apiBase()}/optimizations/generalist-agent`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
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
  const processEvent = ({ event, data }: { event: string; data: Record<string, unknown> }) =>
    dispatchGeneralistEvent(handlers, event, data, () =>
      msg("auto.features.agent.panel.lib.stream.literal.2"),
    );
  try {
    await readServerSentEvents(res.body, processEvent);
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
    res = await fetchWithAuthRetry(`${apiBase()}/optimizations/generalist-agent/confirm`, {
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
