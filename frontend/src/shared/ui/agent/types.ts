export type AgentStatus = "idle" | "streaming" | "done" | "error";

export type AgentToolStatus = "running" | "done" | "error";

export interface AgentToolCall {
  id: string;
  tool: string;
  reason: string;
  status: AgentToolStatus;
  startedAt: number;
  endedAt: number | null;
  payload?: Record<string, unknown>;
}

export interface AgentMessage {
  role: "assistant" | "user";
  content: string;
  toolCalls?: AgentToolCall[];
  model?: string | null;
}

export interface AgentThinking {
  reasoning: string;
  startedAt: number | null;
  endedAt: number | null;
  streaming: boolean;
}
