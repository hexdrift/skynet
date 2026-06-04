/**
 * Builds a default DSPy metric from a column-role map.
 *
 * Compares each output column on the prediction to its labeled value
 * on the gold example. Single-output tasks degenerate to a 0/1 score;
 * multi-output tasks get partial credit (average of matches).
 *
 * String comparison is case-insensitive + whitespace-trimmed so that
 * trivial formatting differences ("Yes " vs "yes") don't tank scores.
 */
export function buildMetricTemplate(
  roles: Record<string, "input" | "output" | "ignore" | string>,
): string {
  const outputs = Object.entries(roles)
    .filter(([, r]) => r === "output")
    .map(([c]) => c);
  const toId = (s: string) => s.replace(/[^a-zA-Z0-9_\u0590-\u05FF]/g, "_").replace(/^(\d)/, "_$1");

  // Fallback when no roles are set yet — mirrors buildSignatureTemplate's
  // fallback so the editor always compiles even before the user maps columns.
  const fields = outputs.length > 0 ? outputs.map(toId) : ["output_field"];
  const fieldsLiteral = `[${fields.map((f) => `"${f}"`).join(", ")}]`;

  return `def metric(gold: dspy.Example, pred: dspy.Prediction, trace: bool = None, pred_name: str = None, pred_trace: list = None) -> dspy.Prediction:
    fields = ${fieldsLiteral}
    total = len(fields)
    correct = 0
    mismatches = []
    for f in fields:
        expected = getattr(gold, f, None)
        actual = getattr(pred, f, None)
        if expected is None:
            continue
        if str(actual).strip().lower() == str(expected).strip().lower():
            correct += 1
        else:
            mismatches.append(f"{f}: expected {expected!r}, got {actual!r}")
    score = correct / total if total else 0.0
    feedback = "Matches all outputs." if not mismatches else "Mismatches: " + "; ".join(mismatches)
    return dspy.Prediction(score=score, feedback=feedback)
`;
}

/**
 * Builds a starting ReAct metric template.
 *
 * A ReAct run scores a tool-use trajectory, not a single prediction, so the
 * metric receives `(example, rollout)` — NOT the `(gold, pred, trace)` shape of
 * the standard metric — and returns a float in [0, 1]. The seed scores
 * tool-selection coverage (how many recorded steps the candidate reproduced);
 * the code agent refines weighting, argument fidelity, and gate progress from
 * the documented fields.
 */
export function buildReactMetricTemplate(): string {
  return `def metric(example, rollout) -> float:
    """Score a ReAct rollout against the recorded trajectory. Return [0, 1].

    example fields:
      example.replay_steps     -> recorded tool calls (each .tool_name, .argument_hash)
      example.allowed_tools    -> tool names allowed this turn
      example.tool_schema_hashes -> {tool_name: schema_hash}
      example.state_before / example.state_after -> wizard-state snapshots (dict)
      example.chat_history, example.signature_inputs
    rollout fields:
      rollout.events           -> per-step events (.outcome, .candidate_tool,
                                  .candidate_argument_hash, .matched_step, .evidence)
      rollout.submit_called, rollout.submit_payload, rollout.terminated_early
    """
    recorded = list(getattr(example, "replay_steps", []) or [])
    events = list(getattr(rollout, "events", []) or [])
    hits = sum(1 for e in events if getattr(e, "matched_step", None) is not None)
    if not recorded:
        return 0.0 if getattr(rollout, "terminated_early", False) else 1.0
    return min(1.0, hits / len(recorded))
`;
}
