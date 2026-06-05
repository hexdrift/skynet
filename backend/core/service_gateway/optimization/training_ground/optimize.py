"""CLI entry point for the training-ground harness.

Loads recorded trajectories from ``agent_messages``, runs ``gepa.optimize``
against the trace-conditioned replay mock, and writes a versioned bundle
that the runtime can mount. Spec lives at
``backend/training_ground_SPEC.md`` §7 / §9 — this module is the executable
half of that contract.

Run with::

    uv run python -m core.service_gateway.optimization.training_ground.optimize \\
        --model openrouter/minimax/minimax-m2.7 \\
        --reflection-lm openrouter/minimax/minimax-m2.7 \\
        --since 14d \\
        --auto medium \\
        --batch-size 8 \\
        --out core/service_gateway/optimization/training_ground/bundles/minimax-2.7/2026-05-28.json
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import dspy
import gepa
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from sqlalchemy import Engine, create_engine

from core.config import settings
from core.models.common import ModelConfig
from core.service_gateway.agents.generalist import GeneralistSig
from core.service_gateway.language_models import build_language_model

from . import persistence
from .batch_sampler import PedagogicalBatchSampler
from .gepa_adapter import (
    TrainingGroundDspyAdapter,
    _candidate_tool_arg_descriptions,
    _candidate_tool_descriptions,
    _candidate_tool_names,
    seed_candidate_from_program,
)
from .grounding import ChatTemplate, FireworksEchoScorer, MiniMaxChatTemplate, PromptScorer
from .metrics import _CRITICAL as CRITICAL_DIMS
from .registry import hash_tool_schema
from .types import Bundle, EvaluationExample, PairedBootstrapResult

logger = logging.getLogger(__name__)


_AUTO_BUDGETS: dict[str, int] = {
    "light": 500,
    "medium": 2000,
    "heavy": 8000,
}
"""Translation table for ``--auto`` into ``max_metric_calls``.

GEPA's public API does not accept an ``auto`` enum; we resolve it here so
the CLI stays ergonomic. Numbers are operator-tunable via
``--max-metric-calls`` for any campaign that doesn't fit the table.
"""


_PROMOTION_CI_LOWER = 0.03
"""Minimum lower-bound on the paired bootstrap 95% CI for promotion. See §11."""

_PROMOTION_REGRESSION_FLOOR = -0.02
"""Per-critical-dim mean delta floor — any worse and the bundle is blocked."""

_PROMOTION_TOTAL_HOLDOUT_FLOOR = 200
"""Minimum total held-out trajectories for the §11 promotion gate."""

_PROMOTION_PER_PHASE_FLOOR = 30
"""Minimum held-out trajectories per wizard phase for the §11 promotion gate.

Without a per-phase floor, an overall ≥200 holdout can still hide a
phase with one or two samples whose bootstrap CI is dominated by noise.
Spec §11 wants every populated phase to clear the floor independently."""

_PROMOTION_BOOTSTRAP_FLOOR = 10_000
"""Minimum ``--bootstrap-resamples`` for a promotable run.

10k is the §11-mandated floor — anything less and the CI bounds aren't
tight enough to gate. ``--dry-run`` is exempt because it skips the gate."""

_DEFAULT_VERSION_TAG_FMT = "%Y-%m-%d"


@dataclass(frozen=True)
class _PromotionVerdict:
    """Outcome of the §11 promotion gate."""

    promotable: bool
    reasons: tuple[str, ...]


def _build_arg_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="training_ground.optimize",
        description="Optimize the generalist agent prompts via GEPA on recorded trajectories.",
    )
    parser.add_argument(
        "--model",
        required=True,
        help="LiteLLM model id for the candidate rollouts (e.g. openrouter/minimax/minimax-m2.7).",
    )
    parser.add_argument(
        "--reflection-lm",
        required=True,
        help="LiteLLM model id used by GEPA's reflective proposer (e.g. openai/gpt-5.5).",
    )
    parser.add_argument(
        "--reflection-base-url",
        default=None,
        help=(
            "Optional base URL for the reflection LM. Leave unset to route by "
            "the model id's provider prefix (openai/gpt-5.5 -> OpenAI). The "
            "reflector deliberately does NOT inherit generalist_agent_base_url "
            "(that serves the student model), so a cross-provider reflector works."
        ),
    )
    parser.add_argument(
        "--mcp-url",
        default=None,
        help="MCP server URL. Defaults to settings.generalist_agent_mcp_url.",
    )
    parser.add_argument(
        "--mcp-auth-header",
        default=None,
        help="Verbatim Authorization header forwarded to the MCP session (e.g. 'Bearer ...').",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL DSN. Defaults to settings.remote_db_url.",
    )
    parser.add_argument(
        "--since",
        default="14d",
        help="Training window expressed as Nd or Nw (default: 14d).",
    )
    parser.add_argument(
        "--holdout-frac",
        type=float,
        default=0.20,
        help="Fraction of examples reserved per wizard phase for the val/holdout set.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Minibatch size passed to PedagogicalBatchSampler.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="RNG seed shared by GEPA, the batch sampler, and the splitter.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Optional override for the candidate (student) LM temperature.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Optional override for the candidate LM max_tokens.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Where to write the bundle JSON.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Hard cap on the number of agent_messages rows loaded (default: 5000 floor).",
    )
    parser.add_argument(
        "--reward",
        choices=("combined", "vector", "grounding"),
        default="combined",
        help=(
            "Reward driving GEPA, mirroring ECHO (arXiv 2605.24517). 'combined' "
            "(default) = the paper's max-gain recipe: the 12-dimension replay "
            "task reward + a --grounding-weight observation-grounding auxiliary. "
            "'vector' = task reward only (the GRPO-only baseline). 'grounding' = "
            "observation-grounding only (the verifier-free env-only ablation). "
            "'combined'/'grounding' need the 'training' extra (transformers + "
            "httpx) and a Fireworks-hosted MiniMax model."
        ),
    )
    parser.add_argument(
        "--grounding-weight",
        type=float,
        default=0.05,
        help=(
            "ECHO's λ — the coefficient on the grounding auxiliary in --reward "
            "combined (paper value: 0.05). Ignored by --reward vector/grounding."
        ),
    )
    parser.add_argument(
        "--fireworks-model",
        default=None,
        help=(
            "Fireworks model path for the --reward grounding echo scorer "
            "(e.g. accounts/fireworks/models/minimax-m2p7). Defaults to --model "
            "with any leading 'fireworks_ai/' stripped."
        ),
    )
    parser.add_argument(
        "--hf-repo",
        default=None,
        help=(
            "Hugging Face repo for the MiniMax chat template used by --reward "
            "grounding (default: MiniMaxAI/MiniMax-M2.7)."
        ),
    )

    budget_group = parser.add_mutually_exclusive_group(required=True)
    budget_group.add_argument(
        "--auto",
        choices=sorted(_AUTO_BUDGETS),
        help="Use a preset budget (light/medium/heavy) — translates to max_metric_calls.",
    )
    budget_group.add_argument(
        "--max-metric-calls",
        type=int,
        help="Exact metric-call budget; overrides --auto.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Score the seed candidate against one minibatch + print projected budget. No write.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Write the bundle even if the §11 promotion gate fails. "
            "Useful for inspection runs; the operator still has to mount it manually."
        ),
    )
    parser.add_argument(
        "--no-frontier-objective",
        action="store_true",
        help="Use GEPA's default frontier instead of the per-objective frontier.",
    )
    parser.add_argument(
        "--bootstrap-resamples",
        type=int,
        default=10_000,
        help="Number of resamples for the paired bootstrap CI (spec §11).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level (default: INFO).",
    )
    return parser


def _budget_kwargs(args: argparse.Namespace) -> dict[str, int]:
    """Translate the CLI's budget mode into ``gepa.optimize`` kwargs.

    Enforces ``--auto`` XOR ``--max-metric-calls`` (already done by argparse's
    mutually exclusive group) and returns the dict to splat into the
    ``gepa.optimize`` call.

    Args:
        args: Parsed CLI namespace.

    Returns:
        ``{"max_metric_calls": int}``.

    Raises:
        SystemExit: when both modes are populated (defense in depth).
    """
    if args.max_metric_calls is not None:
        return {"max_metric_calls": args.max_metric_calls}
    if args.auto is None:
        raise SystemExit("Must pass --auto or --max-metric-calls")
    return {"max_metric_calls": _AUTO_BUDGETS[args.auto]}


def _student_lm_config(args: argparse.Namespace) -> ModelConfig:
    """Build the candidate-LM config from CLI flags + settings."""
    extras: dict[str, Any] = {}
    base_url = settings.generalist_agent_base_url or None
    return ModelConfig(
        name=args.model,
        base_url=base_url,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        extra=extras,
    )


def _reflection_lm_config(args: argparse.Namespace) -> ModelConfig:
    """Build the reflective-proposer LM config from CLI flags.

    The reflection LM is the optimizer's proposer, not the served model, so it
    routes by its own model-id provider prefix (``openai/gpt-5.5`` -> OpenAI)
    and only takes a base URL from the explicit ``--reflection-base-url`` flag.
    It deliberately does NOT inherit ``generalist_agent_base_url`` — that
    endpoint serves the student model and would misroute a cross-provider
    reflector such as GPT-5.5.
    """
    return ModelConfig(
        name=args.reflection_lm,
        base_url=args.reflection_base_url,
    )


_FIREWORKS_LITELLM_PREFIX = "fireworks_ai/"


def _grounding_completions_model(args: argparse.Namespace) -> str:
    """Resolve the Fireworks /completions model path for the grounding scorer.

    LiteLLM model ids carry a ``fireworks_ai/`` provider prefix that the raw
    Fireworks completions endpoint does not accept; strip it unless the
    operator passed an explicit ``--fireworks-model``.
    """
    if args.fireworks_model:
        return args.fireworks_model
    model = args.model
    if model.startswith(_FIREWORKS_LITELLM_PREFIX):
        return model[len(_FIREWORKS_LITELLM_PREFIX) :]
    return model


def _resolve_fireworks_api_key() -> str:
    """Resolve the Fireworks API key from settings or the environment.

    Raises:
        SystemExit: when neither ``settings.fireworks_ai_api_key`` nor the
            ``FIREWORKS_AI_API_KEY`` env var is set — grounding can't score
            without it.
    """
    secret = settings.fireworks_ai_api_key
    if secret is not None:
        return secret.get_secret_value()
    env_key = os.environ.get("FIREWORKS_AI_API_KEY")
    if env_key:
        return env_key
    raise SystemExit(
        "No Fireworks API key — set FIREWORKS_AI_API_KEY (or "
        "settings.fireworks_ai_api_key) for --reward grounding."
    )


def _build_grounding_template_and_scorer(
    args: argparse.Namespace,
) -> tuple[ChatTemplate, PromptScorer]:
    """Build the MiniMax chat template + Fireworks echo scorer for grounding.

    Both are optimizer-only and require the 'training' extra; their
    constructors raise a clear error when ``transformers`` / ``httpx`` are
    absent.
    """
    template = (
        MiniMaxChatTemplate(repo=args.hf_repo) if args.hf_repo else MiniMaxChatTemplate()
    )
    scorer = FireworksEchoScorer(
        api_key=_resolve_fireworks_api_key(),
        model=_grounding_completions_model(args),
    )
    return template, scorer


def _build_adapter(
    *,
    args: argparse.Namespace,
    seed_program: dspy.ReActV2,
    student_lm: dspy.LM,
    reflection_lm: dspy.LM,
) -> TrainingGroundDspyAdapter:
    """Construct the parameterized ECHO adapter for the selected ``--reward``.

    Maps the three modes onto the one adapter: ``vector`` = task term only,
    ``grounding`` = grounding term only, ``combined`` = task term plus a
    ``--grounding-weight`` grounding auxiliary (the paper's max-gain recipe).
    """
    if args.reward == "vector":
        return TrainingGroundDspyAdapter(
            seed_program=seed_program,
            student_lm=student_lm,
            reflection_lm=reflection_lm,
            include_task_reward=True,
            grounding_weight=0.0,
        )
    template, scorer = _build_grounding_template_and_scorer(args)
    if args.reward == "grounding":
        return TrainingGroundDspyAdapter(
            seed_program=seed_program,
            student_lm=student_lm,
            reflection_lm=reflection_lm,
            include_task_reward=False,
            grounding_weight=1.0,
            template=template,
            scorer=scorer,
        )
    return TrainingGroundDspyAdapter(
        seed_program=seed_program,
        student_lm=student_lm,
        reflection_lm=reflection_lm,
        include_task_reward=True,
        grounding_weight=args.grounding_weight,
        template=template,
        scorer=scorer,
    )


def _resolve_db_url(args: argparse.Namespace) -> str:
    """Pick the database DSN from CLI override or settings.

    Raises:
        SystemExit: when neither is configured.
    """
    if args.db_url:
        return args.db_url
    secret = settings.remote_db_url
    if secret is None:
        raise SystemExit(
            "No database URL — pass --db-url or set REMOTE_DB_URL."
        )
    return secret.get_secret_value()


def _build_engine(db_url: str) -> Engine:
    """Construct a plain SQLAlchemy engine for the optimize CLI.

    Importing :class:`core.storage.remote.RemoteJobStore` pulls in the
    embedding / vector-bootstrap path which is overkill for read-only
    trajectory loading — we use ``create_engine`` directly with
    application_name set for observability.
    """
    return create_engine(
        db_url,
        connect_args={"application_name": "skynet-training-ground-optimize"},
        pool_pre_ping=True,
    )


# ``dspy.Tool`` drops MCP ``annotations`` when wrapping a server tool, so we
# stash the derived approval severity on the wrapped object under this attr and
# read it back at overlay-build time. Kept off the schema hash (it is identity
# metadata, not part of the call contract) so it never perturbs drift detection.
_TOOL_SEVERITY_ATTR = "_skynet_severity"


def _severity_from_annotations(annotations: Any) -> str | None:
    """Map MCP tool annotations to an approval severity, or ``None`` if unstated.

    Mirrors the frontend ``ApprovalSeverity`` tiers from the MCP annotation
    hints: a read-only tool is ``info``, an explicitly destructive one is
    ``destructive``, and a declared-but-mutating tool is ``warning``. When the
    server states no relevant hint we return ``None`` so the surface never
    fabricates a severity it was not told.

    Args:
        annotations: The MCP ``ToolAnnotations`` object (or ``None``).

    Returns:
        ``"info"``/``"warning"``/``"destructive"``, or ``None`` when no hint
        applies.
    """
    if annotations is None:
        return None
    if getattr(annotations, "readOnlyHint", None) is True:
        return "info"
    if getattr(annotations, "destructiveHint", None) is True:
        return "destructive"
    if getattr(annotations, "readOnlyHint", None) is False:
        return "warning"
    return None


def set_tool_severity(tool: dspy.Tool, severity: str | None) -> None:
    """Stash a derived approval severity on a wrapped tool (no-op when ``None``).

    Args:
        tool: The ``dspy.Tool`` to annotate.
        severity: The severity tier, or ``None`` to leave the tool unmarked.
    """
    if severity is not None:
        setattr(tool, _TOOL_SEVERITY_ATTR, severity)


def tool_severity(tool: dspy.Tool) -> str | None:
    """Read a tool's stashed approval severity, or ``None`` when unmarked.

    Args:
        tool: The ``dspy.Tool`` to read.

    Returns:
        The severity tier set by :func:`set_tool_severity`, or ``None``.
    """
    return getattr(tool, _TOOL_SEVERITY_ATTR, None)


async def _list_live_tools(
    mcp_url: str, auth_header: str | None
) -> list[dspy.Tool]:
    """Open one MCP session and return the live ``dspy.Tool`` roster.

    Each tool's session-bound callable is irrelevant for our purposes —
    the optimize CLI never invokes them. Only ``.name``, ``.desc``,
    ``.args`` and the approval-severity hint from ``.annotations`` are read
    (for the seed candidate, the bundle's schema-hash snapshot, and the
    overlay's per-tool severity). Rollout-time tool calls are routed through
    :class:`TraceConditionedMCPMock`.

    Args:
        mcp_url: MCP server URL.
        auth_header: Optional ``Authorization`` header to forward.

    Returns:
        List of dspy.Tool objects, one per MCP-exposed tool, each carrying its
        derived approval severity (see :func:`set_tool_severity`).
    """
    headers = {"Authorization": auth_header} if auth_header else None
    async with (
        streamablehttp_client(mcp_url, headers=headers) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        listing = await session.list_tools()
        tools: list[dspy.Tool] = []
        for tool in listing.tools:
            wrapped = dspy.Tool.from_mcp_tool(session, tool)
            set_tool_severity(
                wrapped, _severity_from_annotations(getattr(tool, "annotations", None))
            )
            tools.append(wrapped)
        return tools


def _load_seed_program_and_hashes(
    *,
    mcp_url: str,
    mcp_auth_header: str | None,
    max_iters: int = 8,
    signature_cls: type = GeneralistSig,
) -> tuple[dspy.ReActV2, dict[str, str], list[dspy.Tool]]:
    """Construct the seed ReActV2 + capture the live tool-schema hashes.

    Args:
        mcp_url: Endpoint of the MCP server hosting the agent's tools.
        mcp_auth_header: Verbatim ``Authorization`` header for the session.
        max_iters: ReActV2 loop budget. Mirrors the production setting.
        signature_cls: Signature the seed ReActV2 is built around. Defaults to
            ``GeneralistSig`` so the CLI path is identical; the /run path passes
            a resolved signature to drive arbitrary modules.

    Returns:
        ``(seed_program, tool_schema_hashes, dspy_tools)``. ``dspy_tools`` is
        returned so the caller can filter the trainset by tool-roster overlap.
    """
    dspy_tools = asyncio.run(_list_live_tools(mcp_url, mcp_auth_header))
    if not dspy_tools:
        raise SystemExit(
            f"MCP at {mcp_url!r} exposed zero tools — refusing to optimize an empty surface."
        )
    program = dspy.ReActV2(signature_cls, tools=dspy_tools, max_iters=max_iters)
    schema_hashes = {tool.name: hash_tool_schema(tool) for tool in dspy_tools}
    return program, schema_hashes, dspy_tools


def _filter_trainable_examples(
    examples: list[EvaluationExample],
    *,
    live_hashes: dict[str, str],
) -> list[EvaluationExample]:
    """Drop turns whose recorded tool surface is no longer compatible.

    Three failure modes filtered here:

    1. Allowed-tool name drift — a tool the example called is no longer
       exposed by the live MCP. The bundle would hard-fail at runtime.
    2. Recorded-hash name drift — a tool whose schema was hashed at
       record time is no longer in the live roster. Schemas the example
       conditioned on are unverifiable, so the example is untrustworthy.
    3. Schema-hash drift — a tool the example called has a different
       canonical schema than what was recorded. The optimized instructions
       may refer to stale wording/args and lead the optimizer astray.

    Args:
        examples: Raw examples from ``load_trajectories``.
        live_hashes: ``{tool_name: sha256_hex}`` for the live MCP roster as
            captured by :func:`registry.snapshot_tool_schema_hashes`.

    Returns:
        Examples whose recorded ``allowed_tools`` AND ``tool_schema_hashes``
        keys are both subsets of the live roster AND whose hashes agree
        with the live hashes for every tool they reference.
    """
    live_names = frozenset(live_hashes)
    kept: list[EvaluationExample] = []
    dropped_missing = 0
    dropped_drifted = 0
    for example in examples:
        if not example.allowed_tools.issubset(live_names):
            dropped_missing += 1
            continue
        recorded_names = frozenset(example.tool_schema_hashes)
        if not recorded_names.issubset(live_names):
            dropped_missing += 1
            continue
        drifted = False
        for name, recorded in example.tool_schema_hashes.items():
            if live_hashes[name] != recorded:
                drifted = True
                break
        if drifted:
            dropped_drifted += 1
            continue
        kept.append(example)
    if dropped_missing:
        logger.warning(
            "Dropped %d/%d examples whose recorded allowed_tools mention dropped MCP tools",
            dropped_missing,
            len(examples),
        )
    if dropped_drifted:
        logger.warning(
            "Dropped %d/%d examples whose tool_schema_hashes drifted from the live roster",
            dropped_drifted,
            len(examples),
        )
    return kept


def _evaluate_candidate_on_examples(
    *,
    adapter: TrainingGroundDspyAdapter,
    candidate: dict[str, str],
    examples: list[EvaluationExample],
) -> tuple[list[float], list[dict[str, float]], dict[str, float], list[Any]]:
    """Score one candidate against ``examples`` via ``adapter.evaluate``.

    Used by both the seed (baseline) and the optimized candidate so both
    rollouts go through the exact same instantiation + ``dspy.context``
    binding that GEPA uses during optimization. Sharing the path is what
    makes the §11 paired bootstrap comparison apples-to-apples.

    Returns:
        ``(per_example_scalars, per_example_objectives, mean_objective_scores,
        per_example_outputs)`` where ``per_example_outputs`` carries the rollout
        ``Prediction`` (or ``None`` on a failed rollout) for each example, in
        ``examples`` order — the service path reads these to surface the agent's
        per-example answer in the data view.
    """
    batch = adapter.evaluate(examples, candidate, capture_traces=False)
    scalars = list(batch.scores)
    per_example: list[dict[str, float]] = []
    means: dict[str, float] = {}
    if batch.objective_scores:
        for record in batch.objective_scores:
            entry = dict(record) if isinstance(record, dict) else {}
            per_example.append(entry)
            for name, value in entry.items():
                means.setdefault(name, 0.0)
                means[name] += float(value)
        n = max(1, len(batch.objective_scores))
        means = {name: total / n for name, total in means.items()}
    return scalars, per_example, means, list(batch.outputs)


def _critical_regressions(
    baseline_objectives: list[dict[str, float]],
    candidate_objectives: list[dict[str, float]],
) -> list[tuple[str, float]]:
    """Return per-critical-dim mean deltas worse than the §11 floor.

    Args:
        baseline_objectives: Per-example dim dicts for the seed program.
        candidate_objectives: Per-example dim dicts for the optimized candidate.

    Returns:
        ``[(dim_name, delta)]`` for every critical dim whose candidate-mean is
        more than ``_PROMOTION_REGRESSION_FLOOR`` below the baseline-mean. The
        list is empty when no regressions exceed the floor.
    """
    regressions: list[tuple[str, float]] = []
    for dim in CRITICAL_DIMS:
        baseline_mean = _mean_of_dim(baseline_objectives, dim)
        candidate_mean = _mean_of_dim(candidate_objectives, dim)
        delta = candidate_mean - baseline_mean
        if delta < _PROMOTION_REGRESSION_FLOOR:
            regressions.append((dim, delta))
    return regressions


def _mean_of_dim(records: list[dict[str, float]], dim: str) -> float:
    """Mean of ``dim`` across records, treating missing entries as 0.0."""
    if not records:
        return 0.0
    total = 0.0
    for record in records:
        total += float(record.get(dim, 0.0))
    return total / len(records)


def _resolve_promotion(
    *,
    bootstrap: PairedBootstrapResult,
    baseline_objectives: list[dict[str, float]],
    candidate_objectives: list[dict[str, float]],
    holdout_examples: list[EvaluationExample],
    stratifier: Callable[[EvaluationExample], str] | None = None,
) -> _PromotionVerdict:
    """Apply the §11 promotion gate and explain the result.

    Args:
        bootstrap: Paired bootstrap stats from ``paired_bootstrap_ci``.
        baseline_objectives: Per-example dim dicts for the seed candidate.
        candidate_objectives: Per-example dim dicts for the optimized candidate.
        holdout_examples: The held-out evaluation examples — used to
            compute both the total and per-phase trajectory floors.
        stratifier: Maps each example to a per-bucket label for the per-bucket
            holdout floor. The CLI passes ``persistence.phase_of`` to recover
            the wizard-phase floor; ``None`` collapses to a single bucket so
            the advisory (non-CLI) caller floors on total scale only.

    Returns:
        A ``_PromotionVerdict`` whose ``reasons`` field is empty on PASS and
        a non-empty list of failure strings on BLOCK.
    """
    bucket_of = stratifier if stratifier is not None else (lambda _e: "")
    reasons: list[str] = []
    held_out = len(holdout_examples)
    if held_out < _PROMOTION_TOTAL_HOLDOUT_FLOOR:
        reasons.append(
            f"held-out scale: {held_out} < {_PROMOTION_TOTAL_HOLDOUT_FLOOR} required by §11"
        )
    bucket_counts: dict[str, int] = {}
    for example in holdout_examples:
        bucket = bucket_of(example)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    for bucket in sorted(bucket_counts):
        count = bucket_counts[bucket]
        if count < _PROMOTION_PER_PHASE_FLOOR:
            reasons.append(
                f"phase {bucket!r} held-out scale: {count} < "
                f"{_PROMOTION_PER_PHASE_FLOOR} required by §11"
            )
    if bootstrap.ci95_lower <= _PROMOTION_CI_LOWER:
        reasons.append(
            f"bootstrap CI lower bound {bootstrap.ci95_lower:+.4f} "
            f"≤ {_PROMOTION_CI_LOWER:+.4f}"
        )
    regressions = _critical_regressions(baseline_objectives, candidate_objectives)
    for dim, delta in regressions:
        reasons.append(
            f"critical dim {dim!r} regressed by {delta:+.4f} "
            f"(floor {_PROMOTION_REGRESSION_FLOOR:+.4f})"
        )
    return _PromotionVerdict(promotable=not reasons, reasons=tuple(reasons))


_GATE_LOGIC_SOURCE_PATH = (
    "backend/core/service_gateway/optimization/training_ground/metrics.py"
)
"""Repo-relative path of the canonical gate-scoring source.

``_gate_score`` in this file defines what each wizard phase scores; a
bundle trained against version A cannot be safely compared against a
runtime that has refactored the scoring function. The git sha of this
file is stamped into ``Bundle.gate_logic_version`` so the runtime can
sanity-check at mount time."""


def _git_sha_for(path: str) -> str:
    """Return the git sha of ``HEAD:path`` or ``"unknown"`` when unavailable.

    Used to stamp the bundle with ``gate_logic_version`` (see spec §8). A
    stale ``gate_logic_version`` is itself a useful runtime signal — a
    bundle stamped against one git sha of the gate logic can be sanity-
    checked against the runtime's installed version.
    """
    try:
        completed = subprocess.run(
            ["git", "rev-parse", f"HEAD:{path}"],
            check=True,
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[4],
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _bundle_from_result(
    *,
    result: Any,
    args: argparse.Namespace,
    schema_hashes: dict[str, str],
    candidate_scalars: list[float],
    candidate_objective_mean: dict[str, float],
    bootstrap: PairedBootstrapResult,
    train_size: int,
    holdout_size: int,
    window_days: int,
    program_state: dict[str, Any],
    tool_descriptions: dict[str, str],
    tool_arg_descriptions: dict[str, dict[str, str]],
    tool_names: dict[str, str] | None = None,
) -> Bundle:
    """Assemble a ``Bundle`` from GEPA result + post-eval statistics."""
    version_tag = datetime.now(UTC).strftime(_DEFAULT_VERSION_TAG_FMT)
    candidate_mean = (
        sum(candidate_scalars) / len(candidate_scalars) if candidate_scalars else 0.0
    )
    gate_sha = _git_sha_for(_GATE_LOGIC_SOURCE_PATH)
    return Bundle(
        bundle_format_version=1,
        model_id=args.model,
        version=version_tag,
        dspy_version=_installed_version("dspy"),
        gepa_version=_installed_version("gepa"),
        gate_logic_version=gate_sha,
        tool_schema_hashes=schema_hashes,
        max_iters=8,
        program_state=program_state,
        tool_descriptions=tool_descriptions,
        tool_arg_descriptions=tool_arg_descriptions,
        tool_names=tool_names,
        scalar_score=candidate_mean,
        objective_scores=candidate_objective_mean,
        window_days=window_days,
        trajectories_trained_on=train_size,
        trajectories_held_out=holdout_size,
        paired_bootstrap=bootstrap,
        optimizer_kwargs={
            "batch_size": args.batch_size,
            "auto": args.auto,
            "max_metric_calls": args.max_metric_calls,
            "frontier_type": "instance" if args.no_frontier_objective else "objective",
            "seed": args.seed,
            "result_score": float(getattr(result, "best_score", 0.0) or 0.0),
        },
    )


def _installed_version(distribution_name: str) -> str:
    """Return the installed version or ``"unknown"`` if introspection fails."""
    try:
        return version(distribution_name)
    except PackageNotFoundError:
        return "unknown"


def _best_candidate(result: Any) -> dict[str, str]:
    """Pull the best candidate dict out of GEPA's result wrapper.

    GEPA's ``GEPAResult`` exposes ``best_candidate`` as a ``dict[str, str]`` of
    component text. We tolerate either shape (object or dict) to survive
    future refactors.
    """
    best = getattr(result, "best_candidate", None) or getattr(result, "candidate", None)
    if isinstance(best, dict):
        return dict(best)
    raise SystemExit(
        f"Unable to extract best candidate from GEPA result of type {type(result)!r}."
    )


def _program_state_from(
    *,
    best_candidate: dict[str, str],
    adapter: TrainingGroundDspyAdapter,
) -> dict[str, Any]:
    """Realize the best candidate as a concrete ReActV2 program-state dict.

    GEPA returns a candidate as text components — the bundle persists the
    DSPy ``state`` JSON via ``program.save(path, save_program=False)``.
    Reusing ``adapter.build_program`` deepcopies the seed and applies the
    text components canonically so the saved state matches what GEPA's
    own evaluator would load.
    """
    program = adapter.build_program(best_candidate)
    return persistence.extract_program_state(program)


def _run_dry_run(
    *,
    seed_program: dspy.ReActV2,
    train: list[EvaluationExample],
    adapter: TrainingGroundDspyAdapter,
    args: argparse.Namespace,
) -> None:
    """Score the seed candidate against one minibatch and print a budget hint.

    Honest about its limits — GEPA's call count depends on the reflective
    proposer's per-iteration LM usage, which is provider-specific. The
    dry run reports per-minibatch metric calls + the budgeted cap so the
    operator can sanity-check the request shape before committing tokens.
    """
    seed_candidate = seed_candidate_from_program(seed_program)
    sample = train[: max(1, args.batch_size)]
    batch = adapter.evaluate(sample, seed_candidate, capture_traces=False)
    scalars = list(batch.scores)
    if not scalars:
        print("Dry-run: empty trainset — nothing to evaluate.", file=sys.stderr)
        return
    mean = sum(scalars) / len(scalars)
    worst = min(scalars)
    best = max(scalars)
    print("Dry-run summary:")
    print(f"  examples evaluated     : {len(scalars)}")
    print(f"  seed mean scalar       : {mean:.4f}")
    print(f"  seed worst / best      : {worst:.4f} / {best:.4f}")
    budget = _budget_kwargs(args)["max_metric_calls"]
    print(f"  budgeted max metric calls : {budget}")
    print(
        f"  projected minibatches  : ~{max(1, budget // max(1, args.batch_size))} "
        "(upper bound — GEPA early-stops on stagnation)"
    )
    print(
        "  cost estimate          : per provider; not asserted here. "
        "Multiply minibatches × per-example LM calls × pricing manually."
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point invoked by ``python -m core.service_gateway...optimize``.

    Args:
        argv: Optional argv override (used by tests).

    Returns:
        Process exit code — 0 on success or promotion-pass, 1 on §11 BLOCK
        without ``--force``.
    """
    # LiteLLM authenticates the student + reflection LMs from os.environ, which
    # pydantic-settings never populates; load .env so a bare CLI run finds the
    # provider keys without the operator exporting them by hand. override=False
    # keeps any real exported env var ahead of the .env value.
    load_dotenv(Path(__file__).resolve().parents[4] / ".env", override=False)
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if not args.dry_run and args.bootstrap_resamples < _PROMOTION_BOOTSTRAP_FLOOR:
        raise SystemExit(
            f"--bootstrap-resamples must be ≥ {_PROMOTION_BOOTSTRAP_FLOOR} for a "
            f"promotable run (got {args.bootstrap_resamples}); use --dry-run for "
            f"smaller smoke tests."
        )

    mcp_url = args.mcp_url or settings.generalist_agent_mcp_url
    seed_program, schema_hashes, _dspy_tools = _load_seed_program_and_hashes(
        mcp_url=mcp_url, mcp_auth_header=args.mcp_auth_header
    )

    db_url = _resolve_db_url(args)
    engine = _build_engine(db_url)

    examples_all = persistence.load_trajectories(
        engine, window=args.since, limit=args.max_rows
    )
    examples_filtered = _filter_trainable_examples(
        examples_all, live_hashes=schema_hashes
    )
    if not examples_filtered:
        raise SystemExit(
            "No trainable trajectories after filtering — verify the persistence "
            "migration is applied and the window contains annotated rows."
        )
    train, holdout = persistence.split_stratified(
        examples_filtered,
        holdout_frac=args.holdout_frac,
        seed=args.seed,
        stratifier=persistence.phase_of,
    )
    logger.info(
        "Loaded %d examples (window=%s); split into train=%d holdout=%d",
        len(examples_filtered),
        args.since,
        len(train),
        len(holdout),
    )

    student_lm = build_language_model(_student_lm_config(args), disable_cache=True)
    reflection_lm = build_language_model(_reflection_lm_config(args))
    adapter = _build_adapter(
        args=args,
        seed_program=seed_program,
        student_lm=student_lm,
        reflection_lm=reflection_lm,
    )

    if args.dry_run:
        _run_dry_run(seed_program=seed_program, train=train, adapter=adapter, args=args)
        return 0

    if not train:
        raise SystemExit(
            "Train split is empty — try a larger --since window or lower --holdout-frac."
        )
    if not holdout:
        raise SystemExit(
            "Holdout split is empty — promotion gate needs ≥1 held-out example."
        )

    seed_candidate = seed_candidate_from_program(seed_program)
    sampler = PedagogicalBatchSampler(batch_size=args.batch_size, seed=args.seed)
    frontier_type = "instance" if args.no_frontier_objective else "objective"
    budget_kwargs = _budget_kwargs(args)

    logger.info(
        "Starting gepa.optimize with frontier=%s, batch=%d, seed=%d, budget=%s",
        frontier_type,
        args.batch_size,
        args.seed,
        budget_kwargs,
    )
    result = gepa.optimize(
        seed_candidate=seed_candidate,
        trainset=train,
        valset=holdout,
        adapter=adapter,
        batch_sampler=sampler,
        reflection_minibatch_size=None,
        frontier_type=frontier_type,
        cache_evaluation=True,
        seed=args.seed,
        **budget_kwargs,
    )

    best_candidate = _best_candidate(result)
    baseline_scalars, baseline_objectives, _, _ = _evaluate_candidate_on_examples(
        adapter=adapter, candidate=seed_candidate, examples=holdout
    )
    (
        candidate_scalars,
        candidate_objectives_full,
        candidate_objective_mean,
        _,
    ) = _evaluate_candidate_on_examples(
        adapter=adapter, candidate=best_candidate, examples=holdout
    )
    bootstrap = persistence.paired_bootstrap_ci(
        baseline_scores=baseline_scalars,
        candidate_scores=candidate_scalars,
        resamples=args.bootstrap_resamples,
        seed=args.seed,
    )
    verdict = _resolve_promotion(
        bootstrap=bootstrap,
        baseline_objectives=baseline_objectives,
        candidate_objectives=candidate_objectives_full,
        holdout_examples=holdout,
        stratifier=persistence.phase_of,
    )

    program_state = _program_state_from(
        best_candidate=best_candidate,
        adapter=adapter,
    )
    window_days = _window_days(args.since)
    bundle = _bundle_from_result(
        result=result,
        args=args,
        schema_hashes=schema_hashes,
        candidate_scalars=candidate_scalars,
        candidate_objective_mean=candidate_objective_mean,
        bootstrap=bootstrap,
        train_size=len(train),
        holdout_size=len(holdout),
        window_days=window_days,
        program_state=program_state,
        tool_descriptions=_candidate_tool_descriptions(best_candidate),
        tool_arg_descriptions=_candidate_tool_arg_descriptions(best_candidate),
        tool_names=_candidate_tool_names(best_candidate),
    )

    _report_verdict(bundle=bundle, verdict=verdict)
    if not verdict.promotable:
        if not args.force:
            print(
                "Refusing to write the bundle because the §11 promotion gate failed. "
                "Re-run with --force to write it to an inspection-only path.",
                file=sys.stderr,
            )
            return 1
        out_path = _inspection_only_path(args.out)
        print(
            f"§11 BLOCKED — --force diverting bundle to inspection-only path "
            f"{out_path} so the production --out is not clobbered.",
            file=sys.stderr,
        )
    else:
        out_path = args.out
    persistence.write_bundle(bundle=bundle, out_path=out_path)
    print(f"Bundle written to {out_path}")
    return 0


def _inspection_only_path(out_path: Path) -> Path:
    """Derive a sibling path the operator must manually promote.

    Mounting an inspection-only file at the live ConfigMap path is a
    deliberate act — the suffix forces the operator to rename it before
    k8s picks it up.
    """
    suffix = out_path.suffix or ".json"
    return out_path.with_name(f"{out_path.stem}.inspection-only{suffix}")


def _window_days(window: str) -> int:
    """Convert ``Nd`` / ``Nw`` to a day count for the bundle field."""
    delta = persistence.parse_window(window)
    return max(1, delta.days)


def _report_verdict(*, bundle: Bundle, verdict: _PromotionVerdict) -> None:
    """Print a human-readable summary + the §11 verdict."""
    print()
    print("=" * 72)
    print(f"Bundle for model_id = {bundle.model_id}")
    print(f"  scalar_score     : {bundle.scalar_score:.4f}")
    print(
        f"  paired bootstrap : mean Δ {bundle.paired_bootstrap.mean_delta:+.4f}, "
        f"CI95 [{bundle.paired_bootstrap.ci95_lower:+.4f}, "
        f"{bundle.paired_bootstrap.ci95_upper:+.4f}]"
    )
    print(
        f"  trajectories     : trained {bundle.trajectories_trained_on}, "
        f"held out {bundle.trajectories_held_out}"
    )
    print(f"  dspy / gepa      : {bundle.dspy_version} / {bundle.gepa_version}")
    print("Critical objective means:")
    for dim, value in bundle.objective_scores.items():
        marker = "*" if dim in CRITICAL_DIMS else " "
        print(f"  [{marker}] {dim:<32s} {value:.4f}")
    if verdict.promotable:
        print()
        print("§11 verdict: PROMOTABLE")
    else:
        print()
        print("§11 verdict: BLOCKED")
        for reason in verdict.reasons:
            print(f"  - {reason}")
    print("=" * 72)
    print()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    raise SystemExit(main())


__all__ = ["main"]
