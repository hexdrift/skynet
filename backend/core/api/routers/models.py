"""Routes for model catalog, live discovery, and per-model probe ranking.

``GET /models`` returns the curated catalog. ``POST /models/discover`` probes
an OpenAI-compatible endpoint for its available models. ``POST /models/probe``
streams a per-model eval score so the UI can rank the catalog for a given
task without the user having to guess.
"""

from __future__ import annotations

import json as _json
import logging
import queue
import random
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from functools import partial
from typing import Any, cast

import dspy
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ...exceptions import ServiceError
from ...models import ColumnMapping, ModelConfig
from ...registry import ResolverError, resolve_module_factory, resolve_optimizer_factory
from ...service_gateway.language_models import build_language_model
from ...service_gateway.optimization.data import (
    DatasetSplits,
    load_metric_from_code,
    load_signature_from_code,
    rows_to_examples,
)
from ...service_gateway.optimization.optimizers import (
    compile_program,
    evaluate_on_test,
    instantiate_optimizer,
)
from ..model_catalog import ModelCatalogResponse, get_catalog_cached
from ..response_limits import AGENT_MAX_LIST, AGENT_MAX_TEXT, cap_list, truncate_text
from ._probe import (
    GEPAProgressHook,
    ProbeProgressTracker,
    TrajectoryPoint,
    compute_eval_count,
    fit_scaling_law,
    stratified_split,
)

logger = logging.getLogger(__name__)

_PROBE_MAX_WORKERS = 4


class DiscoverModelsRequest(BaseModel):
    """Request payload for POST /models/discover."""

    base_url: str
    api_key: str | None = None


class DiscoverModelsResponse(BaseModel):
    """Response payload for POST /models/discover."""

    models: list[str] = []
    base_url: str
    error: str | None = None
    truncated: bool = False
    total: int | None = None


class ModelProbeRequest(BaseModel):
    """Request payload for POST /models/probe.

    Runs a tiny optimization pass per catalog model using the caller's
    signature, metric, module, and optimizer at light settings, so the
    UI can rank every available model for the current task.
    """

    signature_code: str
    metric_code: str
    module_name: str = "predict"
    module_kwargs: dict[str, Any] = Field(default_factory=dict)
    optimizer_name: str = "gepa"
    dataset: list[dict[str, Any]]
    column_mapping: ColumnMapping
    train_count: int = Field(default=12, ge=2, le=64)
    eval_count: int = Field(default=4, ge=1, le=32)
    shuffle: bool = True
    seed: int | None = None
    model_ids: list[str] | None = Field(
        default=None,
        description=(
            "Optional allowlist of LiteLLM model IDs to probe. When omitted, "
            "every available catalog model is probed. Unknown IDs are silently "
            "dropped; an empty filter result yields an immediate 'complete' event."
        ),
    )
    reflection_model_name: str | None = Field(
        default=None,
        description=(
            "Optional shared reflection/instruction LM used across every probed "
            "candidate. For GEPA this fills ``reflection_lm``. When omitted, each "
            "candidate fills the role itself, which biases the ranking toward "
            "models that also self-reflect well — keep this set for a fair "
            "cross-model comparison."
        ),
    )


def create_models_router() -> APIRouter:
    """Build the models' router.

    Returns:
        A FastAPI ``APIRouter`` exposing ``/models``, ``/models/discover``,
        and ``/models/probe``.
    """
    router = APIRouter()

    @router.get(
        "/models",
        response_model=ModelCatalogResponse,
        summary="List the curated model catalog",
        tags=["agent"],
    )
    def list_models() -> ModelCatalogResponse:
        """Return the curated model catalog with provider API-key status.

        Response is effectively static per process lifetime (cached 5 min).

        Returns:
            The cached catalog including each model's availability flag.
        """
        catalog = get_catalog_cached()
        return catalog

    @router.post(
        "/models/discover",
        response_model=DiscoverModelsResponse,
        summary="Probe an OpenAI-compatible endpoint for its model list",
        tags=["agent"],
    )
    def discover_models(payload: DiscoverModelsRequest) -> DiscoverModelsResponse:
        """Probe an OpenAI-compatible endpoint for its model list.

        Tries ``{base_url}/v1/models`` then ``{base_url}/models``. Never
        raises: on any failure ``models`` is empty and ``error`` describes
        the reason.

        Args:
            payload: The endpoint URL plus optional bearer token.

        Returns:
            Discovered model ids (clipped) with truncation flag, or an
            error message when the endpoint is unreachable.
        """
        base = payload.base_url.rstrip("/")
        candidates = [f"{base}/v1/models", f"{base}/models"]
        headers = {"Accept": "application/json"}
        if payload.api_key:
            headers["Authorization"] = f"Bearer {payload.api_key}"

        last_error: str | None = None
        for url in candidates:
            try:
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=8) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                data = _json.loads(body)
                raw = data.get("data") if isinstance(data, dict) else data
                if not isinstance(raw, list):
                    last_error = "Unexpected response shape"
                    continue
                ids: list[str] = []
                for item in raw:
                    if isinstance(item, dict):
                        val = item.get("id") or item.get("name")
                        if isinstance(val, str) and val:
                            ids.append(val)
                    elif isinstance(item, str):
                        ids.append(item)
                sorted_ids = sorted(set(ids))
                clipped, truncated, total = cap_list(sorted_ids, AGENT_MAX_LIST)
                return DiscoverModelsResponse(
                    models=clipped,
                    base_url=base,
                    truncated=truncated,
                    total=total,
                )
            except urllib.error.HTTPError as exc:
                last_error = f"HTTP {exc.code}"
                if exc.code == 404:
                    continue
                break
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = str(exc.reason if hasattr(exc, "reason") else exc)
                break
            except (ValueError, _json.JSONDecodeError) as exc:
                last_error = f"Invalid JSON: {exc}"
                break
        return DiscoverModelsResponse(
            models=[],
            base_url=base,
            error=truncate_text(last_error or "Unable to fetch models", AGENT_MAX_TEXT),
        )

    @router.post(
        "/models/probe",
        summary="Stream a per-model eval score to rank the catalog",
    )
    def probe_models(payload: ModelProbeRequest) -> StreamingResponse:
        """Run a tiny optimization pass per catalog model and stream NDJSON.

        Each line is one of:
        - ``{"event": "start", "total": N, "train_count": T, "eval_count": E, "dataset_size": D}``
        - ``{"event": "model_start", "position": i, "model": ..., "label": ..., "provider": ...}`` emitted before the probe thread starts
        - ``{"event": "model_log", "position": i, "level": str, "logger": str, "message": str}`` emitted live as dspy/litellm/app loggers fire inside the probe thread
        - ``{"event": "model_trajectory", "position": i, "point": {"step": n, "score": float}, "scaling": {...}}`` emitted whenever the log parser detects a new full-eval score — the ``scaling`` block is the incrementally re-fit asymptote so the UI can watch the prediction converge as the optimizer runs
        - ``{"event": "result", "position": i, "model": ..., "label": ..., "provider": ..., "status": "ok"|"error", "score": float|null, "duration_ms": int, "scaling": {...}|null, "message"?: str}``
        - ``{"event": "complete"}``
        - ``{"event": "error", "message": str}`` on top-level setup failures

        The result event's ``scaling`` block is the asymptote fit (see
        ``_probe.fit_scaling_law``) — ``signal="strong"`` means the fitted
        asymptote can be trusted for ranking; ``signal="weak"`` means the
        UI should show "could not determine" and fall back to ``score``.

        Probes run in parallel on a ``ThreadPoolExecutor`` (up to
        ``_PROBE_MAX_WORKERS``) and share one NDJSON queue, so events from
        different models interleave in the stream and the UI sees several
        race-board rows advancing at once. Each worker attaches a
        thread-filtered log handler so parallel rows don't cross-talk.
        Per-model failures are captured inline and never abort the stream.

        Args:
            payload: The probe configuration including dataset, signature,
                metric, optimizer settings, and optional model allowlist.

        Returns:
            A streaming NDJSON response carrying the events listed above.
        """

        return StreamingResponse(_probe_iter(payload), media_type="application/x-ndjson")

    return router


_PROBE_LOG_TARGETS: tuple[str, ...] = ("dspy", "litellm", "backend", "core")


class _QueueLogHandler(logging.Handler):
    """Enqueue formatted log records as ``model_log`` NDJSON events.

    Filters by ``thread_id`` so multiple parallel workers can attach handlers
    to the same logger without cross-talk. Trajectory extraction is handled
    by the ``GEPAProgressHook`` structured callback, not by log parsing.
    """

    def __init__(
        self,
        event_queue: queue.Queue,
        position: int,
        thread_id: int,
    ) -> None:
        """Store the shared queue plus the ``(position, thread_id)`` this handler fans out to.

        Args:
            event_queue: Shared NDJSON event queue.
            position: Index of the probed model in the catalog list.
            thread_id: Worker thread id used to filter cross-talk.
        """
        super().__init__()
        self._queue = event_queue
        self._position = position
        self._thread_id = thread_id

    def emit(self, record: logging.LogRecord) -> None:
        """Enqueue a ``model_log`` event for records produced by the matching thread.

        Args:
            record: The log record dispatched by the underlying logger.
        """
        if record.thread != self._thread_id:
            return
        try:
            message = self.format(record)
        except Exception:
            return
        self._queue.put(
            {
                "event": "model_log",
                "position": self._position,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
                "level": record.levelname,
                "logger": record.name,
                "message": message[:500],
            }
        )


@contextmanager
def _probe_log_capture(
    event_queue: queue.Queue,
    position: int,
) -> Iterator[None]:
    """Attach a per-worker log handler for the duration of a probe.

    Tagged with the current thread id so parallel probes can all push to a
    shared queue without cross-talk. Attaches directly to each target logger
    (not root) because ``dspy`` sets ``propagate=False``.

    Args:
        event_queue: Shared NDJSON event queue.
        position: Index of the probed model in the catalog list.

    Yields:
        ``None`` — the handler is removed when the context exits.
    """

    handler = _QueueLogHandler(event_queue, position, threading.get_ident())
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    handler.setLevel(logging.INFO)
    for name in _PROBE_LOG_TARGETS:
        logging.getLogger(name).addHandler(handler)
    try:
        yield
    finally:
        for name in _PROBE_LOG_TARGETS:
            logging.getLogger(name).removeHandler(handler)


@contextmanager
def _probe_log_levels() -> Iterator[None]:
    """Temporarily raise probe target loggers to INFO for the whole stream.

    Loggers check their effective level before dispatching to handlers, so
    the per-worker handlers won't see anything if the target logger is still
    at WARNING. Managed once around the whole stream (not per worker) to
    keep restore semantics sane under parallel attach/detach.

    Yields:
        ``None`` — the original levels are restored when the context exits.
    """

    previous: dict[str, int] = {}
    for name in _PROBE_LOG_TARGETS:
        target = logging.getLogger(name)
        previous[name] = target.level
        if target.level == logging.NOTSET or target.level > logging.INFO:
            target.setLevel(logging.INFO)
    try:
        yield
    finally:
        for name, level in previous.items():
            target = logging.getLogger(name)
            if target.level != level:
                target.setLevel(level)


def _probe_budget(optimizer_name: str, *, eval_count: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a probe-sized optimizer budget that scales with ``eval_count``.

    The probe's job is to produce a trajectory dense enough that the
    best-so-far envelope either plateaus visibly (letting us rank on
    best-observed) or exposes enough curvature for a saturation fit. A
    3-parameter curve fit needs ~8-12 points for DOF, so we target the
    upper end of that range — five points is too close to the edge and
    was producing "could not determine" for nearly every model.

    GEPA reference: ``auto="light"`` → ~400 metric calls. We pin
    ``max_metric_calls = max(120, eval_count * 16)`` (explicit budget;
    overrides ``auto``), drop ``reflection_minibatch_size`` to 2 for
    denser reflection iterations, switch to
    ``candidate_selection_strategy="current_best"`` to skip Pareto
    bookkeeping, and enable ``track_stats`` so ``detailed_results``
    (including ``val_aggregate_scores``) gets attached to the compiled
    program — this is NOT the GEPA default and is the only source of the
    trajectory for scaling-law extrapolation.

    Args:
        optimizer_name: Optimizer identifier; only ``"gepa"`` is supported.
        eval_count: Number of held-out eval examples — drives the metric
            call budget.

    Returns:
        ``(optimizer_kwargs, compile_kwargs)`` matching the optimizer's
        ``compile()`` signature.
    """

    del optimizer_name  # GEPA is the only supported optimizer.
    optimizer_kwargs: dict[str, Any] = {
        "max_metric_calls": max(120, eval_count * 16),
        "reflection_minibatch_size": 2,
        "candidate_selection_strategy": "current_best",
        "track_stats": True,
    }
    compile_kwargs: dict[str, Any] = {}
    return optimizer_kwargs, compile_kwargs


def _probe_single_model(
    *,
    catalog_model_value: str,
    signature_cls: type[dspy.Signature],
    metric: Any,
    module_factory: Any,
    auto_signature: bool,
    module_kwargs: dict[str, Any],
    optimizer_factory: Any,
    optimizer_name: str,
    optimizer_kwargs: dict[str, Any],
    compile_kwargs: dict[str, Any],
    splits: DatasetSplits,
    eval_examples: list[Any],
    oracle_config: ModelConfig | None,
    progress_tracker: ProbeProgressTracker | None = None,
) -> tuple[Any, float | None]:
    """Compile + evaluate the program and return ``(compiled, final_score)``.

    When ``progress_tracker`` is provided, a ``StopperProtocol`` hook is
    injected via ``gepa_kwargs`` that reads
    ``GEPAState.program_full_scores_val_set`` at every iteration — no
    regex needed.

    Args:
        catalog_model_value: LiteLLM model id to probe.
        signature_cls: Compiled DSPy signature class for the task.
        metric: Compiled metric callable.
        module_factory: Factory returning a DSPy module (e.g. ``Predict``).
        auto_signature: Whether the factory should be passed ``signature``
            automatically when callers haven't supplied one.
        module_kwargs: Extra kwargs forwarded to ``module_factory``.
        optimizer_factory: Factory returning an instantiated optimizer.
        optimizer_name: Optimizer id (used for fingerprinting).
        optimizer_kwargs: Optimizer constructor arguments.
        compile_kwargs: Extra arguments forwarded to ``optimizer.compile()``.
        splits: Train/val/test splits for the optimization run.
        eval_examples: Held-out examples used for the final scoring step.
        oracle_config: Optional shared reflection LM for cross-model fairness.
        progress_tracker: Optional tracker that observes the val-set trajectory.

    Returns:
        ``(compiled_program, final_score)`` where ``final_score`` is the
        held-out aggregate score, or ``None`` if no eval examples remain.
    """

    model_config = ModelConfig(name=catalog_model_value)
    lm = build_language_model(model_config)

    kwargs = dict(module_kwargs)
    if auto_signature or "signature" not in kwargs:
        kwargs["signature"] = signature_cls
    program = module_factory(**kwargs)

    reflection_cfg = oracle_config or model_config

    opt_kwargs = dict(optimizer_kwargs)
    ctx_kwargs: dict[str, Any] = {"lm": lm}

    if progress_tracker is not None:
        gepa_extra = opt_kwargs.get("gepa_kwargs", {})
        existing_cbs = gepa_extra.get("stop_callbacks", [])
        if not isinstance(existing_cbs, list):
            existing_cbs = [existing_cbs]
        existing_cbs.append(GEPAProgressHook(progress_tracker))
        gepa_extra["stop_callbacks"] = existing_cbs
        opt_kwargs["gepa_kwargs"] = gepa_extra

    with dspy.context(**ctx_kwargs):
        optimizer = instantiate_optimizer(
            factory=optimizer_factory,
            optimizer_name=optimizer_name,
            optimizer_kwargs=opt_kwargs,
            metric=metric,
            default_model=model_config,
            reflection_model=reflection_cfg,
        )
        compiled = compile_program(
            optimizer=optimizer,
            program=program,
            splits=splits,
            metric=metric,
            compile_kwargs=compile_kwargs,
        )
        final_score = cast("float | None", evaluate_on_test(compiled, eval_examples, metric))
        return compiled, final_score


def _ndjson(obj: dict[str, Any]) -> bytes:
    """Serialize ``obj`` as one UTF-8 JSON line terminated with ``\\n`` for NDJSON streaming.

    Args:
        obj: A JSON-serialisable dict.

    Returns:
        UTF-8 encoded bytes ready to be yielded from a streaming response.
    """
    return (_json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


def _probe_run_worker(
    position: int,
    catalog_model: Any,
    *,
    shared_queue: queue.Queue,
    cancel_event: threading.Event,
    signature_cls: type[dspy.Signature],
    metric: Any,
    module_factory: Any,
    auto_signature: bool,
    module_kwargs: dict[str, Any],
    optimizer_factory: Any,
    optimizer_name: str,
    optimizer_kwargs: dict[str, Any],
    compile_kwargs: dict[str, Any],
    splits: DatasetSplits,
    eval_examples: list[Any],
    oracle_config: ModelConfig | None,
) -> None:
    """Probe one catalog model on the shared splits and emit events to ``shared_queue``.

    Designed to run inside a ``ThreadPoolExecutor`` worker. Emits a
    ``model_start`` event immediately, optional ``model_log`` /
    ``model_trajectory`` events during compilation via
    ``_probe_log_capture`` and ``ProbeProgressTracker``, and a terminal
    ``result`` event with either ``status="ok"`` (plus ``score`` and
    ``scaling``) or ``status="error"`` (plus truncated ``message``).
    Bails out early without emitting anything when ``cancel_event`` is set
    before the worker begins so the probe loop can shut down promptly.

    Args:
        position: Index of this model in the catalog list.
        catalog_model: The catalog entry being probed.
        shared_queue: Shared queue all probe workers push events to.
        cancel_event: Signal used to short-circuit pending workers.
        signature_cls: Compiled DSPy signature class.
        metric: Compiled metric callable.
        module_factory: Factory returning a DSPy module.
        auto_signature: Whether to inject ``signature`` into the factory.
        module_kwargs: Extra kwargs for ``module_factory``.
        optimizer_factory: Factory returning the configured optimizer.
        optimizer_name: Optimizer id (used for fingerprinting).
        optimizer_kwargs: Optimizer constructor arguments.
        compile_kwargs: Extra arguments forwarded to ``compile()``.
        splits: Train/val/test splits.
        eval_examples: Held-out examples used for the final score.
        oracle_config: Optional shared reflection LM for fair comparisons.
    """
    if cancel_event.is_set():
        return
    started_at = time.time()
    shared_queue.put(
        {
            "event": "model_start",
            "position": position,
            "model": catalog_model.value,
            "label": catalog_model.label,
            "provider": catalog_model.provider,
        }
    )
    tracker = ProbeProgressTracker(event_queue=shared_queue, position=position)
    error: BaseException | None = None
    score: float | None = None
    with _probe_log_capture(shared_queue, position):
        try:
            _, score = _probe_single_model(
                catalog_model_value=catalog_model.value,
                signature_cls=signature_cls,
                metric=metric,
                module_factory=module_factory,
                auto_signature=auto_signature,
                module_kwargs=module_kwargs,
                optimizer_factory=optimizer_factory,
                optimizer_name=optimizer_name,
                optimizer_kwargs=optimizer_kwargs,
                compile_kwargs=compile_kwargs,
                splits=splits,
                eval_examples=eval_examples,
                oracle_config=oracle_config,
                progress_tracker=tracker,
            )
        except Exception as worker_exc:
            error = worker_exc
    duration_ms = int((time.time() - started_at) * 1000)
    line: dict[str, Any] = {
        "event": "result",
        "position": position,
        "model": catalog_model.value,
        "label": catalog_model.label,
        "provider": catalog_model.provider,
        "duration_ms": duration_ms,
    }
    if error is not None:
        logger.warning("Probe failed for %s: %s", catalog_model.value, error, exc_info=error)
        line.update(
            {
                "status": "error",
                "score": None,
                "scaling": None,
                "message": str(error)[:500],
            }
        )
    else:
        scaling_payload: dict[str, Any] | None = None
        try:
            trajectory = list(tracker.points)
            if score is not None:
                last_step = trajectory[-1].step if trajectory else 0
                final_score = float(score)
                if not trajectory or trajectory[-1].score != final_score:
                    trajectory.append(TrajectoryPoint(step=last_step + 1, score=final_score))
                    tracker.record(last_step + 1, final_score)
            fit = fit_scaling_law(trajectory)
            scaling_payload = fit.to_dict()
        except Exception as scaling_exc:
            logger.debug(
                "Scaling fit failed for %s: %s",
                catalog_model.value,
                scaling_exc,
            )
        line.update(
            {
                "status": "ok",
                "score": float(score) if score is not None else None,
                "scaling": scaling_payload,
            }
        )
    shared_queue.put(line)


def _probe_drain_futures_and_signal(futures: list[Any], shared_queue: queue.Queue) -> None:
    """Block until every probe future resolves, then push a ``None`` sentinel.

    Runs on a daemon thread so the main streaming loop can stop yielding
    as soon as the sentinel arrives instead of polling ``as_completed``
    from the NDJSON generator (which would interleave awkwardly with the
    ``shared_queue.get`` timeout loop).

    Args:
        futures: The probe-worker futures to drain.
        shared_queue: Shared NDJSON queue; receives a terminal ``None``.
    """
    for f in futures:
        with suppress(Exception):
            f.result()
    shared_queue.put(None)


def _probe_iter(payload: ModelProbeRequest) -> Iterator[bytes]:
    """Drive the per-model probe loop and yield NDJSON event bytes.

    See ``probe_models`` for the full event contract. This is the generator
    body — emitting a ``start``, per-model ``model_start`` /
    ``model_log`` / ``model_trajectory`` / ``result`` events, and a final
    ``complete``. On top-level setup failure a single ``error`` event is
    emitted and the generator returns.

    Args:
        payload: The probe configuration submitted by the caller.

    Yields:
        UTF-8 NDJSON event bytes.
    """
    # exec() isolation gap: runs user code in the API process. Moving this
    # into a persistent subprocess pool is tracked as Phase B — the probe
    # loop invokes the compiled metric + module many times per worker, so
    # it cannot use the per-call ``safe_exec`` wrappers without thrashing.
    # Payloads reaching this endpoint have already passed the subprocess
    # boundary in ``validate_payload`` / ``/validate-code``.
    try:
        signature_cls = load_signature_from_code(payload.signature_code)
        metric = load_metric_from_code(payload.metric_code)
        module_factory, auto_signature = resolve_module_factory(payload.module_name)
        optimizer_factory = resolve_optimizer_factory(payload.optimizer_name)
        examples = rows_to_examples(payload.dataset, payload.column_mapping)
    except (ServiceError, ResolverError) as exc:
        yield _ndjson({"event": "error", "message": str(exc)})
        return

    dataset_size = len(examples)
    eval_count_actual = compute_eval_count(dataset_size, default=payload.eval_count)
    train_count_actual = min(payload.train_count, dataset_size - eval_count_actual)
    if train_count_actual < 2 or eval_count_actual < 1:
        yield _ndjson(
            {
                "event": "error",
                "message": (
                    f"Dataset only has {dataset_size} rows — probe needs at least {2 + eval_count_actual} rows."
                ),
            }
        )
        return

    rng = random.Random(payload.seed)
    train_examples, eval_examples = stratified_split(
        examples=examples,
        dataset=payload.dataset,
        mapping=payload.column_mapping,
        train_count=train_count_actual,
        eval_count=eval_count_actual,
        rng=rng,
    )
    splits = DatasetSplits(train=train_examples, val=eval_examples, test=eval_examples)

    catalog = get_catalog_cached()
    if payload.model_ids:
        allow = set(payload.model_ids)
        models = [m for m in catalog.models if m.value in allow]
    else:
        models = catalog.models
    yield _ndjson(
        {
            "event": "start",
            "total": len(models),
            "train_count": len(train_examples),
            "eval_count": len(eval_examples),
            "dataset_size": dataset_size,
        }
    )

    optimizer_kwargs, compile_kwargs = _probe_budget(payload.optimizer_name, eval_count=len(eval_examples))
    oracle_config = ModelConfig(name=payload.reflection_model_name) if payload.reflection_model_name else None

    if not models:
        yield _ndjson({"event": "complete"})
        return

    shared_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
    cancel_event = threading.Event()

    probe_fn = partial(
        _probe_run_worker,
        shared_queue=shared_queue,
        cancel_event=cancel_event,
        signature_cls=signature_cls,
        metric=metric,
        module_factory=module_factory,
        auto_signature=auto_signature,
        module_kwargs=payload.module_kwargs,
        optimizer_factory=optimizer_factory,
        optimizer_name=payload.optimizer_name,
        optimizer_kwargs=optimizer_kwargs,
        compile_kwargs=compile_kwargs,
        splits=splits,
        eval_examples=eval_examples,
        oracle_config=oracle_config,
    )

    max_workers = min(len(models), _PROBE_MAX_WORKERS)
    with _probe_log_levels():
        executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="probe")
        try:
            futures = [executor.submit(probe_fn, i, m) for i, m in enumerate(models)]

            threading.Thread(
                target=_probe_drain_futures_and_signal,
                args=(futures, shared_queue),
                daemon=True,
            ).start()

            while True:
                try:
                    event = shared_queue.get(timeout=1.0)
                except queue.Empty:
                    if cancel_event.is_set():
                        break
                    continue
                if event is None:
                    break
                yield _ndjson(event)
        finally:
            cancel_event.set()
            for f in futures:
                f.cancel()
            executor.shutdown(wait=False, cancel_futures=True)

    yield _ndjson({"event": "complete"})
