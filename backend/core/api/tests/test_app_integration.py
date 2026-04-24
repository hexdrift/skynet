"""Integration tests for create_app() — lifespan, /health, /queue,
cache-headers middleware, SIGTERM handler, and /openapi.public.json.

These tests use the *real* create_app() factory but stub out every
external dependency (Postgres, background worker, DSPy service) so
the suite runs without any I/O.
"""

from __future__ import annotations

import signal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ..app import _SCALAR_HIDDEN_PATHS, create_app
from ...models.common import HEALTH_STATUS_OK
from ...registry.core import ServiceRegistry


def _make_mock_worker(*, threads_alive: bool = True, stale_seconds: float | None = 0.0):
    """Build a MagicMock configured with realistic BackgroundWorker defaults."""
    w = MagicMock()
    w.threads_alive.return_value = threads_alive
    w.seconds_since_last_activity.return_value = stale_seconds
    w.queue_size.return_value = 2
    w.active_jobs.return_value = 1
    w.thread_count.return_value = 2
    return w


def _make_mock_job_store(*, pending_ids: list[str] | None = None):
    """Build a MagicMock configured with realistic JobStore defaults."""
    js = MagicMock()
    js.recover_orphaned_jobs.return_value = 0
    js.recover_pending_jobs.return_value = pending_ids or []
    return js




@pytest.fixture()
def mock_worker():
    return _make_mock_worker()


@pytest.fixture()
def mock_job_store():
    return _make_mock_job_store()


@pytest.fixture()
def app_client(mock_worker, mock_job_store):
    """Return a TestClient backed by the real create_app().

    Patches are held open across the entire TestClient lifetime so that the
    lifespan coroutine (which calls get_job_store / get_worker) runs under
    the mocks.
    """
    registry = ServiceRegistry()

    with (
        patch("core.api.app.get_job_store", return_value=mock_job_store),
        patch("core.api.app.get_worker", return_value=mock_worker),
        patch("core.api.app.DspyService"),  # prevent real DSPy init
    ):
        application = create_app(registry=registry)
        with TestClient(application, raise_server_exceptions=False) as client:
            yield client, mock_worker, mock_job_store




def test_lifespan_calls_recover_orphaned_jobs(mock_worker, mock_job_store):
    """Lifespan startup calls ``recover_orphaned_jobs`` exactly once."""
    registry = ServiceRegistry()
    with (
        patch("core.api.app.get_job_store", return_value=mock_job_store),
        patch("core.api.app.get_worker", return_value=mock_worker),
        patch("core.api.app.DspyService"),
    ):
        application = create_app(registry=registry)
        with TestClient(application, raise_server_exceptions=False):
            mock_job_store.recover_orphaned_jobs.assert_called_once()


def test_lifespan_calls_get_worker(mock_worker, mock_job_store):
    """Lifespan startup calls ``get_worker`` at least once."""
    registry = ServiceRegistry()
    with (
        patch("core.api.app.get_job_store", return_value=mock_job_store),
        patch("core.api.app.get_worker", return_value=mock_worker) as gw_mock,
        patch("core.api.app.DspyService"),
    ):
        application = create_app(registry=registry)
        with TestClient(application, raise_server_exceptions=False):
            gw_mock.assert_called_once()


def test_lifespan_requeues_pending_jobs(mock_worker):
    """IDs from ``recover_pending_jobs`` are forwarded to ``get_worker`` as ``pending_optimization_ids``."""
    pending = ["job-aaa", "job-bbb"]
    mock_js = _make_mock_job_store(pending_ids=pending)
    registry = ServiceRegistry()
    with (
        patch("core.api.app.get_job_store", return_value=mock_js),
        patch("core.api.app.get_worker", return_value=mock_worker) as gw_mock,
        patch("core.api.app.DspyService"),
    ):
        application = create_app(registry=registry)
        with TestClient(application, raise_server_exceptions=False):
            _, kwargs = gw_mock.call_args
            assert kwargs.get("pending_optimization_ids") == pending




def test_health_live_worker_returns_200(app_client):
    """GET /health returns 200 when worker threads are alive and not stale."""
    client, mock_worker, _ = app_client
    mock_worker.threads_alive.return_value = True
    mock_worker.seconds_since_last_activity.return_value = 0.0

    resp = client.get("/health")

    assert resp.status_code == 200


def test_health_live_worker_returns_expected_shape(app_client):
    """GET /health response includes ``status`` and ``registered_assets`` fields."""
    client, mock_worker, _ = app_client
    mock_worker.threads_alive.return_value = True
    mock_worker.seconds_since_last_activity.return_value = 0.0

    body = client.get("/health").json()

    assert body["status"] == HEALTH_STATUS_OK
    assert "registered_assets" in body


def test_health_stale_worker_returns_503(app_client):
    """Worker threads alive but idle beyond WORKER_STALE_THRESHOLD → 503."""
    client, mock_worker, _ = app_client
    mock_worker.threads_alive.return_value = True
    # 601 s > default threshold of 600 s
    mock_worker.seconds_since_last_activity.return_value = 601.0

    resp = client.get("/health")

    assert resp.status_code == 503


def test_health_dead_worker_returns_503(app_client):
    """Worker threads not alive → 503."""
    client, mock_worker, _ = app_client
    mock_worker.threads_alive.return_value = False

    resp = client.get("/health")

    assert resp.status_code == 503


def test_health_no_worker_returns_503():
    """GET /health returns 503 when worker threads report ``threads_alive=False``."""
    registry = ServiceRegistry()
    mock_js = _make_mock_job_store()
    null_worker = MagicMock()
    null_worker.threads_alive.return_value = False
    null_worker.seconds_since_last_activity.return_value = None

    with (
        patch("core.api.app.get_job_store", return_value=mock_js),
        patch("core.api.app.get_worker", return_value=null_worker),
        patch("core.api.app.DspyService"),
    ):
        application = create_app(registry=registry)
        with TestClient(application, raise_server_exceptions=False) as client:
            resp = client.get("/health")
    assert resp.status_code == 503




def test_queue_with_worker_returns_200(app_client):
    """GET /queue returns 200 when a worker is running."""
    client, _, _ = app_client
    resp = client.get("/queue")
    assert resp.status_code == 200


def test_queue_with_worker_returns_correct_shape(app_client):
    """GET /queue response reflects the worker's live pending/active/thread counts."""
    client, mock_worker, _ = app_client
    mock_worker.queue_size.return_value = 3
    mock_worker.active_jobs.return_value = 1
    mock_worker.thread_count.return_value = 2
    mock_worker.threads_alive.return_value = True

    body = client.get("/queue").json()

    assert body["pending_jobs"] == 3
    assert body["active_jobs"] == 1
    assert body["worker_threads"] == 2
    assert body["workers_alive"] is True


def test_queue_without_worker_returns_zeros():
    """If get_worker returns None the queue endpoint returns all-zeros shape."""
    registry = ServiceRegistry()
    mock_js = _make_mock_job_store()

    with (
        patch("core.api.app.get_job_store", return_value=mock_js),
        patch("core.api.app.get_worker", return_value=None),
        patch("core.api.app.DspyService"),
    ):
        application = create_app(registry=registry)
        with TestClient(application, raise_server_exceptions=False) as client:
            resp = client.get("/queue")

    assert resp.status_code == 200
    body = resp.json()
    assert body["pending_jobs"] == 0
    assert body["workers_alive"] is False




def test_cache_headers_health_no_cache(app_client):
    """GET /health response carries ``no-cache`` Cache-Control."""
    client, _, _ = app_client
    resp = client.get("/health")
    cc = resp.headers.get("cache-control", "")
    assert "no-cache" in cc


def test_cache_headers_queue_private(app_client):
    """GET /queue response carries a short private Cache-Control (max-age=5)."""
    client, _, _ = app_client
    resp = client.get("/queue")
    cc = resp.headers.get("cache-control", "")
    assert "private" in cc
    assert "max-age=5" in cc


def test_cache_headers_models_public(app_client):
    """GET /models response carries a public Cache-Control (max-age=300)."""
    client, _, _ = app_client
    resp = client.get("/models")
    cc = resp.headers.get("cache-control", "")
    assert "public" in cc
    assert "max-age=300" in cc


def test_cache_headers_health_differs_from_models(app_client):
    """Health and models must carry different Cache-Control policies."""
    client, mock_worker, _ = app_client
    mock_worker.threads_alive.return_value = True
    mock_worker.seconds_since_last_activity.return_value = 0.0

    health_cc = client.get("/health").headers.get("cache-control", "")
    models_cc = client.get("/models").headers.get("cache-control", "")

    assert health_cc != models_cc




def test_sigterm_handler_calls_worker_stop():
    """The _graceful_shutdown closure must call worker.stop() on SIGTERM."""
    registry = ServiceRegistry()
    mock_js = _make_mock_job_store()
    mock_w = _make_mock_worker()

    captured_handler = {}

    def fake_signal(signum, handler):
        if signum == signal.SIGTERM:
            captured_handler["fn"] = handler

    with (
        patch("core.api.app.get_job_store", return_value=mock_js),
        patch("core.api.app.get_worker", return_value=mock_w),
        patch("core.api.app.DspyService"),
        patch("core.api.app.signal.signal", side_effect=fake_signal),
        patch("core.api.app.threading.current_thread", return_value=__import__("threading").main_thread()),
    ):
        application = create_app(registry=registry)
        with TestClient(application, raise_server_exceptions=False):
            # Handler is registered during lifespan startup
            assert "fn" in captured_handler, "SIGTERM handler was never registered"
            # Invoke it directly as if the OS sent SIGTERM
            captured_handler["fn"](signal.SIGTERM, None)
            mock_w.stop.assert_called()




def test_openapi_public_returns_200(app_client):
    """GET /openapi.public.json returns 200."""
    client, _, _ = app_client
    resp = client.get("/openapi.public.json")
    assert resp.status_code == 200


def test_openapi_public_returns_valid_json(app_client):
    """GET /openapi.public.json body is a valid OpenAPI dict with a ``paths`` key."""
    client, _, _ = app_client
    resp = client.get("/openapi.public.json")
    body = resp.json()
    assert isinstance(body, dict)
    assert "paths" in body


def test_openapi_public_hides_hidden_paths(app_client):
    """Every path in _SCALAR_HIDDEN_PATHS must be absent from the public spec."""
    client, _, _ = app_client
    paths = client.get("/openapi.public.json").json().get("paths", {})
    for hidden in _SCALAR_HIDDEN_PATHS:
        assert hidden not in paths, f"Hidden path {hidden!r} leaked into public spec"


def test_openapi_public_removes_empty_tag_groups(app_client):
    """Tags that have no remaining operations after filtering must be pruned."""
    client, _, _ = app_client
    body = client.get("/openapi.public.json").json()
    paths = body.get("paths", {})
    tags_in_paths: set[str] = set()
    for methods in paths.values():
        if not isinstance(methods, dict):
            continue
        for op in methods.values():
            if isinstance(op, dict):
                for tag in op.get("tags", []):
                    tags_in_paths.add(tag)

    for tag_obj in body.get("tags", []):
        tag_name = tag_obj.get("name")
        assert tag_name in tags_in_paths, (
            f"Tag {tag_name!r} is still in spec['tags'] but has no operations"
        )


def test_openapi_public_retains_public_paths(app_client):
    """System endpoints ``/health`` and ``/queue`` are present in the public spec."""
    client, _, _ = app_client
    paths = client.get("/openapi.public.json").json().get("paths", {})
    assert "/health" in paths
    assert "/queue" in paths
