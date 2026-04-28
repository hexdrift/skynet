"""LLM-backed task summariser for the ``summary`` embedding aspect.

Given a finished job, we want ~2-3 sentences describing *what the
task is* in natural language: input → output, objective, metric
shape. This text is what the ``embedding_summary`` column captures,
separate from the raw code (``embedding_code``) and the column
layout (``embedding_schema``). Keeping summary text in a dedicated
embedding lets the search query a user's natural-language description
of what they want to do — "classify customer complaints by urgency" —
against historical jobs without the raw Python source dragging the
cosine distance around.

The summariser is cheap to stub: ``settings.recommendations_summary_model``
(or ``settings.code_agent_model`` as fallback) is a normal LiteLLM
model id, wrapped in ``dspy.Predict``. If it fails for any reason
(no key, network error, quota) we fall back to a heuristic text
composed from the column mapping — the pipeline keeps working,
just with weaker summary-side signal.
"""

from __future__ import annotations

import logging
from typing import Any

import dspy

from ...config import settings

logger = logging.getLogger(__name__)


class _TaskSummary(dspy.Signature):
    """Describe a DSPy optimization task in 2-3 sentences."""

    signature_code: str = dspy.InputField(desc="The DSPy Signature source code being optimised.")
    metric_code: str = dspy.InputField(desc="The metric function source code (scoring rule).")
    column_mapping: str = dspy.InputField(desc="JSON column → role map (which columns feed inputs vs outputs).")
    dataset_sample: str = dspy.InputField(desc="A handful of sample rows from the training dataset.")
    task_description: str = dspy.OutputField(
        desc=(
            "2-3 sentences describing the task in plain English: what the "
            "inputs are, what output is produced, what the objective is. "
            "Avoid naming the optimizer or model — this text describes the "
            "task itself, not how it's trained."
        )
    )


def _heuristic_summary(
    signature_code: str | None,
    metric_code: str | None,
    column_mapping: dict[str, Any] | None,
) -> str:
    """Fallback summary built by inspecting the code + column mapping.

    Used when the LLM call is unavailable. Worse than a real summary
    for semantic search, but still non-empty and deterministic.

    Args:
        signature_code: Source code of the user's DSPy signature.
        metric_code: Source code of the user's metric function.
        column_mapping: Optional ``{"inputs": ..., "outputs": ...}`` map.

    Returns:
        A short text summary derived from the column mapping and metric
        first-line, or the truncated signature code when the mapping is
        missing.
    """
    if not column_mapping:
        return (signature_code or "").strip()[:500]
    inputs = column_mapping.get("inputs", {}) or {}
    outputs = column_mapping.get("outputs", {}) or {}
    in_names = list(inputs.values()) if isinstance(inputs, dict) else []
    out_names = list(outputs.values()) if isinstance(outputs, dict) else []
    parts: list[str] = []
    if in_names and out_names:
        parts.append(f"Task maps {', '.join(in_names)} to {', '.join(out_names)}.")
    elif in_names:
        parts.append(f"Task takes {', '.join(in_names)} as input.")
    if metric_code and len(metric_code) < 400:
        parts.append(f"Scored by: {metric_code.strip().splitlines()[0] if metric_code.strip() else ''}")
    return " ".join(p for p in parts if p).strip() or (signature_code or "").strip()[:500]


def _build_lm() -> dspy.LM | None:
    """Build the LM used for summarisation, preferring the dedicated setting.

    Returns:
        A :class:`dspy.LM` instance configured with
        ``recommendations_summary_model`` (or ``code_agent_model`` as
        fallback), or ``None`` when no model id is set or instantiation
        fails.
    """
    model_id = (settings.recommendations_summary_model or settings.code_agent_model).strip()
    if not model_id:
        return None
    try:
        return dspy.LM(model=model_id, max_tokens=1024, temperature=0.0)
    except Exception as exc:
        logger.warning("Could not build summariser LM (%s): %s", model_id, exc)
        return None


def summarize_task(
    *,
    signature_code: str | None,
    metric_code: str | None,
    column_mapping: dict[str, Any] | None,
    dataset_sample: list[dict[str, Any]] | None,
) -> str:
    """Return a short natural-language description of the task.

    Never raises. Returns an empty string if nothing useful can be
    produced — callers should treat empty as "skip the summary
    embedding for this job."

    Args:
        signature_code: Source code of the user's DSPy signature.
        metric_code: Source code of the user's metric function.
        column_mapping: Optional column → role map for the dataset.
        dataset_sample: Optional list of sample rows; the first three
            are forwarded to the summariser LM.

    Returns:
        A 2-3 sentence task description from the LLM, or the heuristic
        fallback string when the LLM is unavailable or its call fails.
    """
    fallback = _heuristic_summary(signature_code, metric_code, column_mapping)
    lm = _build_lm()
    if lm is None:
        return fallback
    try:
        import json as _json

        sample_rows = dataset_sample[:3] if dataset_sample else []
        predictor = dspy.Predict(_TaskSummary)
        with dspy.context(lm=lm):
            out = predictor(
                signature_code=(signature_code or "").strip()[:4000],
                metric_code=(metric_code or "").strip()[:4000],
                column_mapping=_json.dumps(column_mapping or {}, ensure_ascii=False)[:1000],
                dataset_sample=_json.dumps(sample_rows, ensure_ascii=False)[:2000],
            )
        text = (out.task_description or "").strip()
        return text or fallback
    except Exception as exc:
        logger.warning("Summariser LLM call failed: %s", exc)
        return fallback
