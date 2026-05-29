"""Loader, splitter, bootstrap statistician, and bundle writer.

All DB access goes through one ``Engine`` so the CLI can build it from
``settings.remote_db_url`` without dragging the whole ``RemoteJobStore``
in. The bundle writer mirrors
``core/service_gateway/optimization/artifacts.persist_program`` — the
state JSON is produced by ``program.save(path, save_program=False)``.
"""

from __future__ import annotations

import json
import logging
import random
import statistics
import tempfile
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import dspy
from sqlalchemy import Engine, text
from sqlalchemy.engine import Row

from .replay import adapt_agent_tool_calls_v1_to_replay
from .types import Bundle, EvaluationExample, PairedBootstrapResult, ReplayStep

logger = logging.getLogger(__name__)


_WINDOW_SUFFIXES = {"d": 1, "w": 7}


def parse_window(window: str) -> timedelta:
    """Parse a ``Nd`` / ``Nw`` window expression into a ``timedelta``.

    Args:
        window: e.g. ``14d`` (14 days), ``2w`` (14 days), ``30d``.

    Returns:
        The corresponding ``timedelta``.

    Raises:
        ValueError: when ``window`` does not match the expected shape.
    """
    if not window or len(window) < 2:
        raise ValueError(f"Invalid window: {window!r}")
    suffix = window[-1].lower()
    if suffix not in _WINDOW_SUFFIXES:
        raise ValueError(f"Unsupported window suffix: {window!r} (use d or w)")
    try:
        count = int(window[:-1])
    except ValueError as exc:
        raise ValueError(f"Invalid window count in {window!r}") from exc
    if count <= 0:
        raise ValueError(f"Window count must be positive: {window!r}")
    return timedelta(days=count * _WINDOW_SUFFIXES[suffix])


def load_trajectories(
    engine: Engine,
    *,
    window: str = "14d",
    limit: int | None = None,
) -> list[EvaluationExample]:
    """Hydrate evaluation examples from the assistant turns within ``window``.

    Only rows where ``wizard_state_before``, ``allowed_tools``, and
    ``tool_schema_hashes`` are all populated are considered — older turns
    predate the training-metadata migration and lack one or more of these
    fields, which makes them unsafe for replay (we can't enforce the tool
    allow-list or detect schema drift without the recorded hashes).

    Args:
        engine: SQLAlchemy engine bound to the Skynet database.
        window: Time window expression (see :func:`parse_window`).
        limit: Optional cap on the number of rows returned.

    Returns:
        The list of evaluation examples in chronological order.
    """
    threshold = datetime.now(UTC) - parse_window(window)
    rows = _fetch_assistant_rows(engine, since=threshold, limit=limit)
    examples: list[EvaluationExample] = []
    for row in rows:
        try:
            examples.append(_row_to_example(row))
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Skipped malformed agent_messages row %s: %s", row.id, exc
            )
    return examples


def _fetch_assistant_rows(
    engine: Engine, *, since: datetime, limit: int | None
) -> list[Row]:
    """Pull every annotated assistant turn since ``since``.

    Joined with a window over the conversation's prior messages so each
    row carries a ``chat_history`` JSON array sitting alongside it. Hard
    cap at 5000 rows so a bad window doesn't blow up memory; tighten via
    ``limit`` when needed.
    """
    sql = """
        WITH ordered AS (
            SELECT
                id,
                conversation_id,
                role,
                content,
                tool_calls,
                model,
                wizard_state_before,
                wizard_state_after,
                allowed_tools,
                tool_schema_hashes,
                created_at,
                ROW_NUMBER() OVER (
                    PARTITION BY conversation_id
                    ORDER BY created_at, id
                ) AS row_index
            FROM agent_messages
        )
        SELECT
            assistant.id,
            assistant.conversation_id,
            assistant.content,
            assistant.tool_calls,
            assistant.model,
            assistant.wizard_state_before,
            assistant.wizard_state_after,
            assistant.allowed_tools,
            assistant.tool_schema_hashes,
            assistant.created_at,
            COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'role', prior.role,
                        'content', prior.content
                    )
                    ORDER BY prior.row_index
                ) FILTER (WHERE prior.id IS NOT NULL),
                '[]'::jsonb
            ) AS chat_history,
            assistant_user.content AS user_message
        FROM ordered AS assistant
        LEFT JOIN ordered AS prior
            ON prior.conversation_id = assistant.conversation_id
           AND prior.row_index < assistant.row_index - 1
        LEFT JOIN ordered AS assistant_user
            ON assistant_user.conversation_id = assistant.conversation_id
           AND assistant_user.row_index = assistant.row_index - 1
           AND assistant_user.role = 'user'
        WHERE assistant.role = 'assistant'
          AND assistant.wizard_state_before IS NOT NULL
          AND assistant.allowed_tools IS NOT NULL
          AND assistant.tool_schema_hashes IS NOT NULL
          AND assistant.created_at >= :since
        GROUP BY
            assistant.id,
            assistant.conversation_id,
            assistant.content,
            assistant.tool_calls,
            assistant.model,
            assistant.wizard_state_before,
            assistant.wizard_state_after,
            assistant.allowed_tools,
            assistant.tool_schema_hashes,
            assistant.created_at,
            assistant_user.content
        ORDER BY assistant.created_at, assistant.id
        LIMIT :hard_cap
    """
    hard_cap = limit if limit is not None else 5000
    with engine.connect() as conn:
        result = conn.execute(text(sql), {"since": since, "hard_cap": hard_cap})
        return list(result.fetchall())


def _row_to_example(row: Row) -> EvaluationExample:
    """Convert a SQL row into an ``EvaluationExample``.

    Args:
        row: Result row from :func:`_fetch_assistant_rows`.

    Returns:
        A fully-populated evaluation example.
    """
    turn_id = str(row.id)
    tool_calls_payload = row.tool_calls or []
    replay_steps: tuple[ReplayStep, ...] = tuple(
        adapt_agent_tool_calls_v1_to_replay(tool_calls_payload, turn_id=turn_id)
    )
    allowed_tools_raw = row.allowed_tools or []
    if isinstance(allowed_tools_raw, dict):
        allowed_tools_raw = list(allowed_tools_raw.keys())
    schema_hashes = row.tool_schema_hashes or {}
    chat_history_raw = row.chat_history or []
    user_message = (row.user_message or "").strip()
    return EvaluationExample(
        turn_id=turn_id,
        user_message=user_message,
        wizard_state_before=dict(row.wizard_state_before or {}),
        wizard_state_after=dict(row.wizard_state_after or {}),
        allowed_tools=frozenset(str(name) for name in allowed_tools_raw),
        tool_schema_hashes={str(k): str(v) for k, v in schema_hashes.items()},
        replay_steps=replay_steps,
        chat_history=tuple(chat_history_raw),
    )


def phase_of(example: EvaluationExample) -> str:
    """Bucket an example into a wizard-phase label.

    Shared by the stratified splitter and the §11 per-phase floor in
    the promotion gate — the names must stay consistent across both call
    sites or the floor's bookkeeping drifts from the splitter's buckets.
    """
    state = example.wizard_state_before
    if state.get("submitted") or state.get("job_id"):
        return "post_submit"
    has_dataset = bool(state.get("dataset_ready") or state.get("staged_dataset_id"))
    has_signature = bool(state.get("signature_code"))
    has_metric = bool(state.get("metric_code"))
    model_cfg = state.get("model_config") if isinstance(state.get("model_config"), dict) else None
    has_model = bool(state.get("model_configured")) or bool(model_cfg and model_cfg.get("name"))
    if has_dataset and has_signature and has_metric and has_model:
        return "ready_to_submit"
    if has_dataset and state.get("columns_configured"):
        return "configured"
    if has_dataset:
        return "dataset_ready"
    return "intake"


def split_stratified(
    examples: list[EvaluationExample],
    *,
    holdout_frac: float = 0.20,
    seed: int = 0,
) -> tuple[list[EvaluationExample], list[EvaluationExample]]:
    """Stratify by wizard phase, then split each bucket by ``holdout_frac``.

    Args:
        examples: All loaded examples.
        holdout_frac: Fraction reserved for valset (per phase).
        seed: RNG seed for reproducibility.

    Returns:
        ``(trainset, holdout)`` — order within each side is randomized.
    """
    if not examples:
        return [], []
    rng = random.Random(seed)
    buckets: dict[str, list[EvaluationExample]] = defaultdict(list)
    for example in examples:
        buckets[phase_of(example)].append(example)
    train: list[EvaluationExample] = []
    holdout: list[EvaluationExample] = []
    for bucket in buckets.values():
        rng.shuffle(bucket)
        cut = max(1, round(len(bucket) * holdout_frac)) if len(bucket) > 1 else 0
        holdout.extend(bucket[:cut])
        train.extend(bucket[cut:])
    rng.shuffle(train)
    rng.shuffle(holdout)
    return train, holdout


def paired_bootstrap_ci(
    baseline_scores: list[float],
    candidate_scores: list[float],
    *,
    resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int = 0,
) -> PairedBootstrapResult:
    """Paired bootstrap CI over per-trajectory ``candidate - baseline`` deltas.

    Args:
        baseline_scores: Per-trajectory scalar for the seed program.
        candidate_scores: Per-trajectory scalar for the candidate program.
        resamples: Number of bootstrap resamples to draw.
        confidence: Two-sided coverage (default 0.95 ⇒ 2.5% / 97.5%).
        seed: RNG seed for reproducibility.

    Returns:
        A ``PairedBootstrapResult`` carrying mean delta + CI bounds.

    Raises:
        ValueError: when the two score lists have different lengths or are empty.
    """
    if len(baseline_scores) != len(candidate_scores):
        raise ValueError("paired_bootstrap_ci requires aligned per-trajectory scores")
    if not baseline_scores:
        raise ValueError("paired_bootstrap_ci requires at least one trajectory")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    deltas = [c - b for b, c in zip(baseline_scores, candidate_scores, strict=False)]
    n = len(deltas)
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(resamples):
        sample = [deltas[rng.randrange(n)] for _ in range(n)]
        means.append(statistics.fmean(sample))
    means.sort()
    alpha = (1.0 - confidence) / 2.0
    low_index = max(0, round(alpha * resamples) - 1)
    high_index = min(resamples - 1, round((1.0 - alpha) * resamples) - 1)
    return PairedBootstrapResult(
        resamples=resamples,
        mean_delta=statistics.fmean(deltas),
        ci95_lower=means[low_index],
        ci95_upper=means[high_index],
    )


def write_bundle(
    *,
    bundle: Bundle,
    out_path: Path,
) -> None:
    """Atomically write the bundle JSON to ``out_path``.

    Uses ``tempfile`` + ``Path.replace`` so a partial write never produces
    a half-formed bundle on disk.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = bundle.model_dump(mode="json")
    encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    with tempfile.NamedTemporaryFile(
        mode="w",
        delete=False,
        dir=out_path.parent,
        prefix=".bundle-",
        suffix=".json",
        encoding="utf-8",
    ) as fh:
        fh.write(encoded)
        tmp_path = Path(fh.name)
    tmp_path.replace(out_path)


def extract_program_state(program: dspy.Module) -> dict[str, Any]:
    """Return the JSON-shaped state dict from ``program.save``.

    Mirrors the path used by
    ``core/service_gateway/optimization/artifacts.persist_program``
    (artifacts.py:191) so the bundle's ``program_state`` round-trips with
    ``fresh_program.load_state(state)`` at runtime.
    """
    with tempfile.TemporaryDirectory(prefix="tg_bundle_") as tmpdir:
        state_path = Path(tmpdir) / "program.json"
        program.save(str(state_path), save_program=False)
        return json.loads(state_path.read_text())


__all__ = [
    "extract_program_state",
    "load_trajectories",
    "paired_bootstrap_ci",
    "parse_window",
    "phase_of",
    "split_stratified",
    "write_bundle",
]
