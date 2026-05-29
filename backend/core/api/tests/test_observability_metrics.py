"""Tests for Prometheus observability helpers."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from .. import observability as obs


class _QueueMetricStore:
    """Fake store exposing cached queue metric inputs."""

    def get_queue_metrics(self) -> tuple[int, float]:
        """Return a stable pending count and queue age."""
        return 3, 42.5


def test_metrics_endpoint_exposes_cached_queue_gauges() -> None:
    """The Prometheus scrape includes queue-depth and queue-age gauges."""
    if obs._Instrumentator is None or obs._Gauge is None:
        pytest.skip("Prometheus metrics dependencies are not installed")
    app = FastAPI()
    obs.install_metrics(app)
    obs.QueueMetricsRefresher(_QueueMetricStore()).refresh_once()

    response = TestClient(app).get("/metrics")

    assert response.status_code == 200
    assert "skynet_jobs_pending 3.0" in response.text
    assert "skynet_queue_age_seconds 42.5" in response.text


class _OrphanStore:
    """Fake store recording orphan-recovery calls."""

    def __init__(self, recovered: int = 2, engine: Any | None = None) -> None:
        """Capture how many orphans the fake will report and the fake engine."""
        self.calls = 0
        self._recovered = recovered
        self.engine = engine

    def recover_orphaned_jobs(self) -> int:
        """Count invocations and return the configured recovery count."""
        self.calls += 1
        return self._recovered


def test_orphan_sweeper_runs_on_non_postgres_dialect() -> None:
    """SQLite / no-engine stores skip the lock check and run the sweep directly."""
    store = _OrphanStore(recovered=4, engine=None)
    sweeper = obs.OrphanRecoverySweeper(store, interval_seconds=5.0)

    assert sweeper.sweep_once() == 4
    assert store.calls == 1


def test_orphan_sweeper_swallows_recovery_exceptions() -> None:
    """A raising ``recover_orphaned_jobs`` must not propagate out of the loop."""

    class _Raises:
        engine = None

        def recover_orphaned_jobs(self) -> int:
            """Raise to verify the sweeper swallows recovery failures."""
            raise RuntimeError("boom")

    sweeper = obs.OrphanRecoverySweeper(_Raises(), interval_seconds=5.0)
    assert sweeper.sweep_once() == 0


def test_advisory_lock_yields_true_for_non_postgres_dialect() -> None:
    """SQLite / no-engine callers treat the lock as won so single-process tests run the work."""
    with obs.advisory_lock(None, 12345) as won:
        assert won is True


def test_orphan_sweeper_skips_when_advisory_lock_held() -> None:
    """On Postgres, a peer holding the advisory lock yields a no-op sweep."""

    class _PGDialect:
        name = "postgresql"

    class _Conn:
        def execute(self, _stmt: Any, _params: Any) -> Any:
            """Return a result whose ``scalar()`` reports the lock as not won."""
            class _Result:
                def scalar(self) -> bool:
                    """Report the advisory lock as held by a peer."""
                    return False

            return _Result()

    class _Begin:
        def __enter__(self) -> _Conn:
            """Enter a fake SQLAlchemy transaction context."""
            return _Conn()

        def __exit__(self, *_exc: Any) -> None:
            """Exit the fake transaction without committing."""
            return

    class _Engine:
        dialect = _PGDialect()

        def begin(self) -> _Begin:
            """Return a fake transaction context for advisory-lock checks."""
            return _Begin()

    store = _OrphanStore(recovered=7, engine=_Engine())
    sweeper = obs.OrphanRecoverySweeper(store, interval_seconds=5.0)

    assert sweeper.sweep_once() == 0
    assert store.calls == 0
