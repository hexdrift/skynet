import type { WorkflowSpec } from "@/shared/types/api";

/**
 * The stored workflow graph of a run that used the workflow module, or null
 * when the payload carries none — every other module submits a single
 * `signature_code` instead. A shape check keeps a legacy or malformed payload
 * out: the canvas is driven by `nodes` and `edges`, and the wizard seeds a
 * fresh starter graph when they're absent.
 */
export function cloneWorkflowSpec(payload: Record<string, unknown>): WorkflowSpec | null {
  const spec = payload.workflow;
  if (!spec || typeof spec !== "object" || Array.isArray(spec)) return null;
  const record = spec as Record<string, unknown>;
  if (!Array.isArray(record.nodes) || !Array.isArray(record.edges)) return null;
  return spec as WorkflowSpec;
}
