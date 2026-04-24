"""Centralized mock/fake builders for core/api/tests/.

All domain fakes that were previously scattered inline across individual test
files live here.  Test-specific values (e.g. a particular metric pair that
the test is asserting against) stay inline in the test — only the generic
"give me any valid fake X" belongs here.

Usage
-----
    from core.api.tests.mocks import (
        fake_background_worker,
        real_run_response_dict,
        real_grid_response_dict,
        real_program_artifact_dict,
        make_artifact,
        make_run_result,
        make_grid_job,
        REAL_OPTIMIZATION_ID,
        REAL_USERNAME
    )
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from ...models import (
    GridSearchResponse,
    OptimizedPredictor,
    PairResult,
    ProgramArtifact,
    RunResponse,
    SplitCounts,
)

_FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


@lru_cache(maxsize=None)
def _read_fixture_text(name: str) -> str:
    """Read a fixture file by name relative to ``backend/tests/fixtures/``.

    Args:
        name: Path relative to the fixtures root (e.g.
            ``"jobs/success_single_gepa.detail.json"``).

    Returns:
        The raw text contents of the fixture file.
    """
    return (_FIXTURES_ROOT / name).read_text()


def load_fixture(name: str) -> Any:
    """Load and parse a JSON fixture by name.

    Args:
        name: Path relative to ``backend/tests/fixtures/``.

    Returns:
        A freshly-parsed JSON payload (safe to mutate between calls).
    """
    return json.loads(_read_fixture_text(name))


# These come from jobs/success_single_gepa.detail.json
REAL_OPTIMIZATION_ID: str = load_fixture("jobs/success_single_gepa.detail.json")[
    "optimization_id"
]
REAL_USERNAME: str = load_fixture("jobs/success_single_gepa.detail.json")["username"]



def real_run_response_dict() -> dict:
    """Return the ``result`` block of the gepa success fixture (fresh copy)."""
    return load_fixture("jobs/success_single_gepa.detail.json")["result"]


def real_grid_response_dict() -> dict:
    """Return the ``grid_result`` block of the grid success fixture (fresh copy)."""
    return load_fixture("jobs/success_grid.detail.json")["grid_result"]


def real_program_artifact_dict() -> dict:
    """Return the ``program_artifact`` sub-dict from the gepa success fixture."""
    return load_fixture("jobs/success_single_gepa.detail.json")["result"][
        "program_artifact"
    ]


def real_optimization_status_dict(kind: str) -> dict:
    """Return the full detail fixture dict for the requested scenario.

    Parameters
    ----------
    kind:
        One of ``"success"``, ``"failed"``, ``"canceled"``, ``"grid"``.
    """
    mapping = {
        "success": "jobs/success_single_gepa.detail.json",
        "failed": "jobs/failed_runtime.detail.json",
        "cancelled": "jobs/cancelled_mid_run.detail.json",
        "grid": "jobs/success_grid.detail.json",
    }
    if kind not in mapping:
        raise ValueError(f"Unknown kind {kind!r}; choose from {list(mapping)}")
    return load_fixture(mapping[kind])



def make_artifact(
    input_fields: list[str] | None = None,
    output_fields: list[str] | None = None,
) -> ProgramArtifact:
    """Build a ProgramArtifact for serve-layer tests.

    Args:
        input_fields: Explicit input field names. Pass ``[]`` to drive the
            400 "missing inputs" response. Leave as ``None`` together with
            ``output_fields`` to get the real fixture-backed artifact.
        output_fields: Explicit output field names. Pass ``[]`` to drive the
            409 "missing outputs" response.

    Returns:
        A real ``ProgramArtifact`` from the grid fixture when both args are
        ``None``, otherwise a hand-built one with the supplied field lists.
    """
    if input_fields is None and output_fields is None:
        raw = load_fixture("jobs/success_grid.detail.json")
        return ProgramArtifact.model_validate(
            raw["grid_result"]["pair_results"][0]["program_artifact"]
        )
    prompt = OptimizedPredictor(
        predictor_name="predict",
        instructions="Be helpful.",
        input_fields=input_fields or [],
        output_fields=output_fields or [],
    )
    return ProgramArtifact(program_pickle_base64="AAAA", optimized_prompt=prompt)


def make_run_result(artifact: ProgramArtifact) -> RunResponse:
    """Build a RunResponse model with the given ProgramArtifact substituted in.

    Args:
        artifact: The artifact to splice into the fixture-backed result.

    Returns:
        A validated ``RunResponse`` backed by real metric values.
    """
    raw = dict(load_fixture("jobs/success_single_gepa.detail.json")["result"])
    raw["program_artifact"] = artifact.model_dump()
    return RunResponse.model_validate(raw)


def make_grid_job(
    opt_id: str,
    pair_index: int = 0,
    pair_error: str | None = None,
    artifact: ProgramArtifact | None = None,
    status: str = "success",
) -> dict:
    """Return a raw job dict for a grid-search job with one pair.

    Args:
        opt_id: Optimization id to stamp on the job dict.
        pair_index: Index of the single pair when hand-building.
        pair_error: Optional error string to attach to the pair.
        artifact: Optional ProgramArtifact override; built on demand otherwise.
        status: Job status string.

    Returns:
        A raw job dict: the real captured fixture when ``artifact`` and
        ``pair_error`` are both ``None``, otherwise a hand-built minimal grid.
    """
    if artifact is None and pair_error is None:
        raw = load_fixture("jobs/success_grid.detail.json")
        return {
            "optimization_id": opt_id,
            "status": status,
            "payload_overview": {
                "optimization_type": "grid_search",
                "model_name": "openai/gpt-4o-mini",
                "module_name": raw["module_name"],
                "optimizer_name": raw["optimizer_name"],
            },
            "result": raw["grid_result"],
        }
    if artifact is None:
        artifact = make_artifact()
    pair = PairResult(
        pair_index=pair_index,
        generation_model="openai/gpt-4o-mini",
        reflection_model="openai/gpt-4o",
        program_artifact=artifact,
        error=pair_error,
    )
    grid = GridSearchResponse(
        module_name="MyModule",
        optimizer_name="GEPA",
        metric_name="accuracy",
        split_counts=SplitCounts(train=10, val=3, test=3),
        total_pairs=1,
        completed_pairs=1,
        pair_results=[pair],
        best_pair=pair,
    )
    return {
        "optimization_id": opt_id,
        "status": status,
        "payload_overview": {
            "optimization_type": "grid_search",
            "model_name": "openai/gpt-4o-mini",
            "module_name": "MyModule",
            "optimizer_name": "gepa",
        },
        "result": grid.model_dump(),
    }



class _BaseFakeJobStore:
    """Minimal in-memory job store shared by all variants."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._logs: dict[str, list] = {}
        self._progress: dict[str, list] = {}

    def seed_job(self, optimization_id: str, **fields: Any) -> dict:
        """Seed a minimal success-state job dict for the given optimization id.

        Args:
            optimization_id: The job id to insert.
            **fields: Extra top-level fields to merge onto the default job dict.

        Returns:
            The freshly-inserted job dict.
        """
        now = datetime.now(timezone.utc).isoformat()
        job = {
            "optimization_id": optimization_id,
            "status": "success",
            "created_at": now,
            "started_at": now,
            "completed_at": now,
            "payload_overview": {},
            "payload": {},
            "result": None,
            "latest_metrics": {},
            "message": None,
            **fields,
        }
        self._jobs[optimization_id] = job
        return job

    def update_job(self, optimization_id: str, **fields: Any) -> None:
        self._jobs[optimization_id].update(fields)

    def delete_job(self, optimization_id: str) -> None:
        self._jobs.pop(optimization_id, None)
        self._logs.pop(optimization_id, None)
        self._progress.pop(optimization_id, None)

    def get_job(self, optimization_id: str) -> dict:
        if optimization_id not in self._jobs:
            raise KeyError(optimization_id)
        return dict(self._jobs[optimization_id])

    def job_exists(self, optimization_id: str) -> bool:
        return optimization_id in self._jobs

    def list_jobs(self, **kwargs: Any) -> list[dict]:
        rows = list(self._jobs.values())
        status = kwargs.get("status")
        username = kwargs.get("username")
        optimization_type = kwargs.get("optimization_type")
        if status:
            rows = [r for r in rows if r.get("status") == status]
        if username:
            rows = [
                r
                for r in rows
                if r.get("payload_overview", {}).get("username") == username
            ]
        if optimization_type:
            rows = [
                r
                for r in rows
                if r.get("payload_overview", {}).get("job_type") == optimization_type
            ]
        limit = kwargs.get("limit", len(rows))
        offset = kwargs.get("offset", 0)
        return rows[offset : offset + limit]

    def count_jobs(self, **kwargs: Any) -> int:
        k = dict(kwargs)
        k.pop("limit", None)
        k.pop("offset", None)
        return len(self.list_jobs(limit=10**9, offset=0, **k))

    def get_logs(self, optimization_id: str, **kwargs: Any) -> list:
        rows = list(self._logs.get(optimization_id, []))
        level = kwargs.get("level")
        if level:
            rows = [r for r in rows if r.get("level") == level]
        limit = kwargs.get("limit")
        offset = kwargs.get("offset", 0)
        rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        return rows

    def get_log_count(self, optimization_id: str) -> int:
        return len(self._logs.get(optimization_id, []))

    def get_progress_events(self, optimization_id: str) -> list:
        return list(self._progress.get(optimization_id, []))

    def get_progress_count(self, optimization_id: str) -> int:
        return len(self._progress.get(optimization_id, []))

    def set_payload_overview(self, optimization_id: str, overview: dict) -> None:
        """Overwrite the ``payload_overview`` sub-dict for an existing job.

        Args:
            optimization_id: The job to update.
            overview: New overview dict (copied into place).
        """
        self._jobs[optimization_id]["payload_overview"] = dict(overview)

    def seed_raw(
        self,
        optimization_id: str,
        *,
        job: dict,
        logs: list | None = None,
        progress: list | None = None,
    ) -> None:
        """Seed a fully-formed job dict plus its logs and progress events.

        Args:
            optimization_id: The job id to insert under.
            job: The complete job dict to store.
            logs: Optional log entry list (empty list if omitted).
            progress: Optional progress event list (empty list if omitted).
        """
        self._jobs[optimization_id] = job
        self._logs[optimization_id] = list(logs or [])
        self._progress[optimization_id] = list(progress or [])

    def delete_jobs(self, optimization_ids: list[str]) -> None:
        for oid in optimization_ids:
            self.delete_job(oid)

    def get_jobs_status_by_ids(
        self, optimization_ids: list[str]
    ) -> dict[str, str | None]:
        return {
            oid: self._jobs[oid]["status"] if oid in self._jobs else None
            for oid in optimization_ids
        }


class FakeJobStore(_BaseFakeJobStore):
    """Public alias of ``_BaseFakeJobStore`` for use in test type annotations."""


def fake_job_store_with_success_single() -> _BaseFakeJobStore:
    """Return a FakeJobStore pre-seeded with the gepa success fixture.

    Returns:
        A ``_BaseFakeJobStore`` seeded with the real gepa success detail
        fixture, including logs and progress events.
    """
    store = _BaseFakeJobStore()
    detail = load_fixture("jobs/success_single_gepa.detail.json")
    store.seed_raw(
        detail["optimization_id"],
        job={
            "optimization_id": detail["optimization_id"],
            "status": detail["status"],
            "created_at": detail["created_at"],
            "started_at": detail["started_at"],
            "completed_at": detail["completed_at"],
            "payload_overview": {
                "username": detail["username"],
                "job_type": detail["optimization_type"],
                "module_name": detail["module_name"],
                "optimizer_name": detail["optimizer_name"],
                "model_name": detail.get("model_name", ""),
            },
            "payload": {},
            "result": detail["result"],
            "latest_metrics": detail.get("latest_metrics", {}),
            "message": detail.get("message"),
        },
        logs=detail.get("logs", []),
        progress=detail.get("progress_events", []),
    )
    return store


def fake_job_store_with_grid() -> _BaseFakeJobStore:
    """Return a FakeJobStore pre-seeded with the grid success fixture.

    Returns:
        A ``_BaseFakeJobStore`` seeded with the real 2-pair grid success
        detail fixture, including logs and progress events.
    """
    store = _BaseFakeJobStore()
    detail = load_fixture("jobs/success_grid.detail.json")
    gr = detail["grid_result"]
    store.seed_raw(
        detail["optimization_id"],
        job={
            "optimization_id": detail["optimization_id"],
            "status": detail["status"],
            "created_at": detail["created_at"],
            "started_at": detail["started_at"],
            "completed_at": detail["completed_at"],
            "payload_overview": {
                "username": detail["username"],
                "job_type": detail["optimization_type"],
                "optimization_type": "grid_search",
                "module_name": gr["module_name"],
                "optimizer_name": gr["optimizer_name"],
                "model_name": detail.get("model_name", ""),
            },
            "payload": {},
            "result": gr,
            "latest_metrics": detail.get("latest_metrics", {}),
            "message": detail.get("message"),
        },
        logs=detail.get("logs", []),
        progress=detail.get("progress_events", []),
    )
    return store


def fake_job_store_with_failed() -> _BaseFakeJobStore:
    """Return a FakeJobStore pre-seeded with the failed_runtime fixture.

    Returns:
        A ``_BaseFakeJobStore`` seeded with the real failed-runtime detail
        fixture, including logs and progress events.
    """
    store = _BaseFakeJobStore()
    detail = load_fixture("jobs/failed_runtime.detail.json")
    store.seed_raw(
        detail["optimization_id"],
        job={
            "optimization_id": detail["optimization_id"],
            "status": detail["status"],
            "created_at": detail["created_at"],
            "started_at": detail["started_at"],
            "completed_at": detail["completed_at"],
            "payload_overview": {
                "username": detail.get("username", ""),
                "job_type": detail.get("optimization_type", "run"),
                "module_name": detail.get("module_name", ""),
                "optimizer_name": detail.get("optimizer_name", ""),
            },
            "payload": {},
            "result": detail.get("result"),
            "latest_metrics": detail.get("latest_metrics", {}),
            "message": detail.get("message"),
        },
        logs=detail.get("logs", []),
        progress=detail.get("progress_events", []),
    )
    return store



def fake_background_worker() -> MagicMock:
    """Return a MagicMock that quacks like BackgroundWorker.

    Configured with realistic defaults (threads alive, small queue).
    """
    w = MagicMock()
    w.threads_alive.return_value = True
    w.seconds_since_last_activity.return_value = 0.0
    w.queue_size.return_value = 0
    w.active_jobs.return_value = 0
    w.thread_count.return_value = 2
    w.submit_job = MagicMock()
    w.cancel = MagicMock()
    w.pending_ids = []
    w.status.return_value = "idle"
    return w



@contextmanager
def override_job_store(app: Any, store: Any):
    """Temporarily replace ``core.api.app.get_job_store`` for *app*.

    Args:
        app: The FastAPI app whose lifespan would call ``get_job_store``.
        store: The in-memory store to substitute.

    Yields:
        The supplied ``store`` object, unchanged.
    """
    with patch("core.api.app.get_job_store", return_value=store):
        yield store


@contextmanager
def override_worker(app: Any, worker: Any):
    """Temporarily replace ``core.api.app.get_worker`` for *app*.

    Args:
        app: The FastAPI app whose lifespan would call ``get_worker``.
        worker: The fake worker to substitute.

    Yields:
        The supplied ``worker`` object, unchanged.
    """
    with patch("core.api.app.get_worker", return_value=worker):
        yield worker


@contextmanager
def override_dspy_service(app: Any, service: Any = None):
    """Temporarily replace ``core.api.app.DspyService`` constructor for *app*.

    Args:
        app: The FastAPI app whose lifespan would instantiate ``DspyService``.
        service: Optional service stand-in; ``None`` simply blocks real
            DSPy initialization.

    Yields:
        The supplied ``service`` object, unchanged.
    """
    with patch("core.api.app.DspyService", return_value=service):
        yield service
