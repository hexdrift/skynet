"""Unit test fixtures.

These tests run without a live server, a real database, or an LLM key.
They rely on in-memory fakes of the job store and FastAPI's ``TestClient``.
Intended to run in CI as a fast gate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Make the backend package importable when pytest is invoked from the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class FakeJobStore:
    """In-memory stand-in for the Postgres-backed job store.

    Implements just the surface the routers hit. Each instance is isolated
    per test so the ordering of test execution doesn't matter.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._logs: dict[str, list] = {}
        self._progress: dict[str, list] = {}

    def seed_job(self, optimization_id: str, **fields: Any) -> dict:
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
            rows = [r for r in rows if r.get("payload_overview", {}).get("username") == username]
        if optimization_type:
            rows = [r for r in rows if r.get("payload_overview", {}).get("job_type") == optimization_type]
        limit = kwargs.get("limit", len(rows))
        offset = kwargs.get("offset", 0)
        return rows[offset:offset + limit]

    def count_jobs(self, **kwargs: Any) -> int:
        # Count matching, ignoring limit/offset
        k = dict(kwargs)
        k.pop("limit", None)
        k.pop("offset", None)
        return len(self.list_jobs(limit=10**9, offset=0, **k))

    def get_logs(self, optimization_id: str, **_kwargs: Any) -> list:
        return list(self._logs.get(optimization_id, []))

    def get_log_count(self, optimization_id: str) -> int:
        return len(self._logs.get(optimization_id, []))

    def get_progress_events(self, optimization_id: str) -> list:
        return list(self._progress.get(optimization_id, []))

    def get_progress_count(self, optimization_id: str) -> int:
        return len(self._progress.get(optimization_id, []))

    def set_payload_overview(self, optimization_id: str, overview: dict) -> None:
        self._jobs[optimization_id]["payload_overview"] = dict(overview)

    def update_job(self, optimization_id: str, **fields: Any) -> None:
        self._jobs[optimization_id].update(fields)

    def delete_job(self, optimization_id: str) -> None:
        self._jobs.pop(optimization_id, None)
        self._logs.pop(optimization_id, None)
        self._progress.pop(optimization_id, None)


@pytest.fixture
def job_store() -> FakeJobStore:
    """Return a fresh fake job store for the test."""
    return FakeJobStore()


@pytest.fixture
def router_app(job_store: FakeJobStore) -> FastAPI:
    """Build a minimal FastAPI app wired up with a subset of routers that
    only depend on job_store. Used for fast router-level tests without the
    full create_app() machinery (which would require Postgres + worker).
    """
    from core.api.routers.analytics import create_analytics_router
    from core.api.routers.models import create_models_router
    from core.api.routers.optimizations_meta import create_optimizations_meta_router
    from core.api.routers.templates import create_templates_router

    app = FastAPI()
    app.include_router(create_models_router())
    app.include_router(create_analytics_router(job_store=job_store))
    app.include_router(create_optimizations_meta_router(job_store=job_store))

    # Templates needs a job_store.engine for SQLAlchemy. Skip it here —
    # covered by a separate integration test.
    return app


@pytest.fixture
def client(router_app: FastAPI) -> TestClient:
    """Return a FastAPI TestClient for the router_app fixture."""
    return TestClient(router_app)
