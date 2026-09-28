"""LLM-backed task summariser feeding ``embedding_summary``.

Given a finished job, we want ~2-3 sentences describing *what the task is*
in natural language. This text is embedded into ``embedding_summary``, which
drives explore semantic search. The summary is built from only what a human
recognises the task by — its title, its description, and a sample of its
training rows — never from the run's signature, metric, column mapping or
optimiser, which are fragile, gameable signals that pull unrelated tasks
together. Because a published job's summary is surfaced to other users, the
signature steers the model to describe the task's domain and shape in general
terms and never to reproduce verbatim values from the data sample — the
sample is evidence of *what kind* of task this is, not content to be echoed.
Keeping a natural-language summary (rather than raw fields) lets
semantically-similar tasks cluster together even when their submissions look
unrelated.

The summariser is cheap to stub: ``settings.embeddings_summary_model`` (or
``settings.code_agent_model`` as fallback) is a normal LiteLLM model id,
wrapped in ``dspy.Predict``. If it fails for any reason (no key, network
error, quota) we fall back to a heuristic text composed from the title and
description — the pipeline keeps working, just with weaker signal.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import dspy

from ...config import settings
from ...models import ModelConfig
from ..language_models import build_language_model

logger = logging.getLogger(__name__)


def _truncate(value: str, limit: int, *, label: str) -> str:
    """Truncate ``value`` to ``limit`` chars, appending ``…`` and logging when cut.

    Args:
        value: The string to bound.
        limit: Maximum length before truncation kicks in.
        label: Short identifier logged when truncation happens, so debug
            output points at the offending field.

    Returns:
        ``value`` unchanged when within ``limit``; otherwise the first
        ``limit`` characters with a single-character ``…`` marker so the
        downstream LLM (and any future log reader) can see the cut.
    """
    if len(value) <= limit:
        return value
    logger.debug("summariser truncated %s from %d chars to %d", label, len(value), limit)
    return value[:limit] + "…"


class _TaskSummary(dspy.Signature):
    """Describe a DSPy optimization task in 2-3 sentences."""

    title: str = dspy.InputField(desc="The task's name.")
    description: str = dspy.InputField(desc="The user's own description of what the task does.")
    dataset_sample: str = dspy.InputField(
        desc=(
            "Several sample rows from the training dataset, as illustrative "
            "evidence of the task's domain and shape. They may be unrepresentative, "
            "so infer the general task — not the specifics of these particular rows."
        )
    )
    task_description: str = dspy.OutputField(
        desc=(
            "2-3 sentences describing the task in plain English, drawn only "
            "from its title, description and sample data: what the inputs are "
            "and what output is produced. Avoid naming the optimizer or model "
            "— this text describes the task itself, not how it's trained. "
            "Describe the domain in general terms; never quote or reproduce "
            "specific values, names, emails, identifiers or other verbatim "
            "content from the sample rows, and don't fixate on their formatting."
        )
    )


def _heuristic_summary(title: str | None, description: str | None) -> str:
    """Fallback summary built from the task's title and description.

    Used when the summariser LLM is unavailable. Weaker than a real summary
    for semantic search, but non-empty and deterministic whenever the task
    carried a title or a description.

    Args:
        title: The task's name.
        description: The user's description of the task.

    Returns:
        The non-empty parts joined by a space, capped at 600 characters;
        empty only when the task had neither a title nor a description.
    """
    parts = [part.strip() for part in (title, description) if part and part.strip()]
    return " ".join(parts)[:600]


def _build_lm() -> dspy.LM | None:
    """Build the LM used for summarisation, preferring the dedicated setting.

    Routes through :func:`build_language_model` so the summariser obeys
    the same provider/base-url/extra-kwargs handling as the optimization
    path — keeps one factory in charge of LiteLLM idiosyncrasies.

    Returns:
        A :class:`dspy.LM` instance configured with
        ``embeddings_summary_model`` (or ``code_agent_model`` as fallback),
        or ``None`` when no model id is set or instantiation fails.
    """
    model_id = (settings.embeddings_summary_model or settings.code_agent_model).strip()
    if not model_id:
        return None
    try:
        return build_language_model(
            ModelConfig(name=model_id, max_tokens=1024, temperature=0.0)
        )
    except Exception as exc:
        logger.warning("Could not build summariser LM (%s): %s", model_id, exc)
        return None


def summarize_task(
    *,
    title: str | None,
    description: str | None,
    dataset_sample: list[dict[str, Any]] | None,
) -> str:
    """Return a short natural-language description of a DSPy task.

    Never raises. Returns an empty string if nothing useful can be
    produced — callers should treat empty as "skip the summary
    embedding for this job."

    Args:
        title: The task's name.
        description: The user's description of the task.
        dataset_sample: Optional list of sample rows; the first ten
            are forwarded to the summariser LM.

    Returns:
        A 2-3 sentence task description from the LLM, or the heuristic
        fallback (title + description) when the LLM is unavailable or its
        call fails.
    """
    fallback = _heuristic_summary(title, description)
    lm = _build_lm()
    if lm is None:
        return fallback
    try:
        sample_rows = dataset_sample[:10] if dataset_sample else []
        predictor = dspy.Predict(_TaskSummary)
        with dspy.context(lm=lm):
            out = predictor(
                title=_truncate((title or "").strip(), 500, label="title"),
                description=_truncate((description or "").strip(), 4000, label="description"),
                dataset_sample=_truncate(
                    json.dumps(sample_rows, ensure_ascii=False), 6000, label="dataset_sample"
                ),
            )
        text = (out.task_description or "").strip()
        return text or fallback
    except Exception as exc:
        logger.warning("Summariser LLM call failed: %s", exc)
        return fallback
