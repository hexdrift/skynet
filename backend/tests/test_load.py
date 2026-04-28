"""Load and stress tests for the Skynet API.

Tests API performance under concurrent load. Uses httpx for async
concurrency and measures latency percentiles + error rates.

Assumed environment:
    - Backend running on localhost:8000 (single Uvicorn worker is fine for smoke,
      use multiple workers for realistic load numbers)
    - PostgreSQL reachable from the backend
    - No OpenAI calls are made — validation/read paths only for deterministic latency

Latency thresholds assume a local dev machine with no network hop.
Scale them up proportionally for remote deployments.

Run:
    cd backend && ../.venv/bin/python -m pytest tests/test_load.py -v -s
"""

from __future__ import annotations

import asyncio
import contextlib
import statistics
import time

import httpx
import pytest
import requests  # type: ignore[import-untyped]

from .conftest import requires_server, wait_for_terminal

BASE_URL = "http://localhost:8000"


async def _hammer(
    method: str,
    url: str,
    n: int,
    concurrency: int,
    json_body: dict | None = None,
) -> dict:
    """Fire ``n`` concurrent requests at ``url`` and return latency/error stats.

    Args:
        method: HTTP verb (``"GET"``, ``"POST"`` or ``"DELETE"``).
        url: Full target URL.
        n: Total number of requests to issue.
        concurrency: Maximum in-flight requests at any time.
        json_body: JSON body for POST requests.

    Returns:
        Mapping with ``total``, ``errors``, ``status_codes``, ``latencies``,
        ``p50``/``p95``/``p99``, ``mean``, ``total_time`` and ``rps`` fields.
    """
    sem = asyncio.Semaphore(concurrency)
    results: list[tuple[int, float]] = []

    async def req(client: httpx.AsyncClient) -> None:
        """Issue a single request honouring the concurrency semaphore."""
        async with sem:
            t0 = time.monotonic()
            try:
                if method == "POST":
                    r = await client.post(url, json=json_body, timeout=30)
                elif method == "DELETE":
                    r = await client.delete(url, timeout=30)
                else:
                    r = await client.get(url, timeout=30)
                results.append((r.status_code, time.monotonic() - t0))
            except Exception:
                results.append((0, time.monotonic() - t0))

    t_start = time.monotonic()
    async with httpx.AsyncClient() as client:
        await asyncio.gather(*(req(client) for _ in range(n)))
    total_time = time.monotonic() - t_start

    latencies = sorted(dt for _, dt in results)
    status_codes: dict[int, int] = {}
    for code, _ in results:
        status_codes[code] = status_codes.get(code, 0) + 1

    def _pct(p: float) -> float:
        """Return the ``p``-th percentile latency in seconds."""
        idx = int(len(latencies) * p)
        return latencies[min(idx, len(latencies) - 1)] if latencies else 0.0

    return {
        "total": n,
        "errors": sum(1 for code, _ in results if code >= 400 or code == 0),
        "status_codes": status_codes,
        "latencies": latencies,
        "p50": _pct(0.50),
        "p95": _pct(0.95),
        "p99": _pct(0.99),
        "mean": statistics.mean(latencies) if latencies else 0.0,
        "total_time": total_time,
        "rps": n / total_time if total_time > 0 else 0.0,
    }


def _print_results(name: str, r: dict) -> None:
    """Pretty-print the latency/error summary returned by ``_hammer``."""
    print(f"\n{'=' * 50}")
    print(f"  {name}")
    print(f"{'=' * 50}")
    print(f"  Requests:  {r['total']}")
    print(f"  Errors:    {r['errors']} ({r['errors'] / r['total'] * 100:.1f}%)")
    print(f"  RPS:       {r['rps']:.1f}")
    print(
        f"  Latency:   p50={r['p50'] * 1000:.0f}ms  "
        f"p95={r['p95'] * 1000:.0f}ms  "
        f"p99={r['p99'] * 1000:.0f}ms  "
        f"mean={r['mean'] * 1000:.0f}ms"
    )
    print(f"  Codes:     {r['status_codes']}")
    print(f"  Total:     {r['total_time']:.1f}s")


@pytest.mark.load
@requires_server
class TestReadEndpointLoad:
    """Concurrency tests for the cheap read endpoints."""

    def test_health_endpoint_handles_100_concurrent(self):
        """Verify ``/health`` stays under p50 200 ms / p99 2 s with 50-way concurrency."""
        r = asyncio.run(_hammer("GET", f"{BASE_URL}/health", n=100, concurrency=50))
        _print_results("GET /health (100 reqs, 50 concurrent)", r)
        assert r["errors"] == 0, f"Errors: {r['errors']} — status codes: {r['status_codes']}"
        assert r["p50"] < 0.2, f"p50 too high: {r['p50'] * 1000:.0f}ms (threshold 200ms)"
        assert r["p99"] < 2.0, f"p99 too high: {r['p99'] * 1000:.0f}ms (threshold 2000ms)"

    def test_queue_endpoint_handles_100_concurrent(self):
        """Verify ``/queue`` stays under p50 500 ms / p99 2 s under load."""
        r = asyncio.run(_hammer("GET", f"{BASE_URL}/queue", n=100, concurrency=50))
        _print_results("GET /queue (100 reqs, 50 concurrent)", r)
        assert r["errors"] == 0, f"Errors: {r['errors']} — status codes: {r['status_codes']}"
        assert r["p50"] < 0.5, f"p50 too high: {r['p50'] * 1000:.0f}ms (threshold 500ms)"
        assert r["p99"] < 2.0, f"p99 too high: {r['p99'] * 1000:.0f}ms (threshold 2000ms)"

    def test_jobs_listing_handles_100_concurrent(self):
        """Verify ``GET /optimizations?limit=10`` stays under p50 500 ms / p99 3 s."""
        r = asyncio.run(_hammer("GET", f"{BASE_URL}/optimizations?limit=10", n=100, concurrency=50))
        _print_results("GET /optimizations (100 reqs, 50 concurrent)", r)
        assert r["errors"] == 0, f"Errors: {r['errors']} — status codes: {r['status_codes']}"
        assert r["p50"] < 0.5, f"p50 too high: {r['p50'] * 1000:.0f}ms (threshold 500ms)"
        assert r["p99"] < 3.0, f"p99 too high: {r['p99'] * 1000:.0f}ms (threshold 3000ms)"

    def test_health_endpoint_sustains_500_rapid_fire(self):
        """Verify ``/health`` sustains >50 RPS over 500 rapid-fire requests."""
        r = asyncio.run(_hammer("GET", f"{BASE_URL}/health", n=500, concurrency=100))
        _print_results("GET /health (500 rapid fire, 100 concurrent)", r)
        assert r["errors"] == 0, f"Errors: {r['errors']} — status codes: {r['status_codes']}"
        assert r["rps"] > 50, f"RPS too low: {r['rps']:.1f} (threshold 50)"
        assert r["p50"] < 0.5, f"p50 too high under rapid fire: {r['p50'] * 1000:.0f}ms"


@pytest.mark.load
@requires_server
class TestWriteEndpointLoad:
    """Concurrency tests for the mutating endpoints."""

    def test_10_rapid_submissions_all_accepted(self):
        """Verify 10 rapid valid submissions are all accepted with 201."""
        payload = {
            "username": "load-test-submit",
            "module_name": "predict",
            "signature_code": (
                "import dspy\nclass S(dspy.Signature):\n    q: str = dspy.InputField()\n    a: str = dspy.OutputField()"
            ),
            "metric_code": "def metric(e, p, t=None): return 1.0",
            "optimizer_name": "gepa",
            "dataset": [{"q": "hi", "a": "bye"}],
            "column_mapping": {"inputs": {"q": "q"}, "outputs": {"a": "a"}},
            "model_config": {"name": "openai/gpt-5.4-nano"},
        }
        r = asyncio.run(_hammer("POST", f"{BASE_URL}/run", n=10, concurrency=5, json_body=payload))
        _print_results("POST /run (10 rapid submissions)", r)
        assert r["status_codes"].get(201, 0) == 10, f"Expected all 10 accepted (201), got: {r['status_codes']}"

        jobs = requests.get(f"{BASE_URL}/optimizations?username=load-test-submit&limit=50", timeout=10).json()
        for job in jobs.get("items", []):
            with contextlib.suppress(Exception):
                requests.post(f"{BASE_URL}/optimizations/{job['optimization_id']}/cancel", timeout=5)
                wait_for_terminal(job["optimization_id"], timeout=30)
                requests.delete(f"{BASE_URL}/optimizations/{job['optimization_id']}", timeout=5)

    def test_50_invalid_submissions_all_rejected_as_422(self):
        """Verify 50 malformed submissions are uniformly rejected with 422."""
        bad_payload = {"username": "load-test-bad"}  # missing required fields
        r = asyncio.run(_hammer("POST", f"{BASE_URL}/run", n=50, concurrency=20, json_body=bad_payload))
        _print_results("POST /run invalid (50 reqs, 20 concurrent)", r)
        assert r["status_codes"].get(422, 0) == 50, f"Expected all 50 to be 422, got: {r['status_codes']}"
        assert r["p50"] < 0.5, f"p50 too high for validation path: {r['p50'] * 1000:.0f}ms"
        assert r["p99"] < 2.0, f"p99 too high for validation path: {r['p99'] * 1000:.0f}ms"


@pytest.mark.load
@requires_server
class TestMixedWorkload:
    """Mixed read/write load while a real background job is in flight."""

    def test_read_endpoints_stay_healthy_while_job_runs(self):
        """Verify read endpoints remain error-free while a real job is running."""
        payload = {
            "username": "load-test-mixed",
            "module_name": "predict",
            "signature_code": (
                "import dspy\nclass S(dspy.Signature):\n    q: str = dspy.InputField()\n    a: str = dspy.OutputField()"
            ),
            "metric_code": "def metric(e, p, t=None): return 1.0",
            "optimizer_name": "gepa",
            "dataset": [{"q": "hi", "a": "bye"}],
            "column_mapping": {"inputs": {"q": "q"}, "outputs": {"a": "a"}},
            "model_config": {"name": "openai/gpt-5.4-nano"},
        }
        r = requests.post(f"{BASE_URL}/run", json=payload, timeout=10)
        assert r.status_code == 201, f"Background job submit failed: {r.status_code}"
        job_id = r.json()["optimization_id"]

        try:

            async def mixed_load() -> dict:
                """Hammer the read endpoints in parallel and return the per-route stats."""
                return {
                    "health": await _hammer("GET", f"{BASE_URL}/health", n=50, concurrency=20),
                    "queue": await _hammer("GET", f"{BASE_URL}/queue", n=50, concurrency=20),
                    "jobs": await _hammer("GET", f"{BASE_URL}/optimizations?limit=5", n=50, concurrency=20),
                    "detail": await _hammer("GET", f"{BASE_URL}/optimizations/{job_id}", n=30, concurrency=10),
                    "summary": await _hammer("GET", f"{BASE_URL}/optimizations/{job_id}/summary", n=30, concurrency=10),
                }

            results = asyncio.run(mixed_load())
            for name, result in results.items():
                _print_results(f"Mixed: {name}", result)
                assert result["errors"] == 0, f"{name} had {result['errors']} errors — codes: {result['status_codes']}"
        finally:
            with contextlib.suppress(Exception):
                requests.post(f"{BASE_URL}/optimizations/{job_id}/cancel", timeout=5)
                wait_for_terminal(job_id, timeout=30)
                requests.delete(f"{BASE_URL}/optimizations/{job_id}", timeout=5)


@pytest.mark.load
@requires_server
class TestDatabaseStress:
    """Database-heavy load tests (404 lookups, filtered listings)."""

    def test_200_concurrent_404_lookups_no_deadlocks(self):
        """Verify 200 concurrent 404 lookups complete without deadlocks."""
        r = asyncio.run(_hammer("GET", f"{BASE_URL}/optimizations/nonexistent-load-test", n=200, concurrency=50))
        _print_results("GET /optimizations/nonexistent (200 reqs, 50 concurrent)", r)
        assert r["status_codes"].get(404, 0) == 200, f"Expected all 200 to be 404, got: {r['status_codes']}"
        assert r["p50"] < 0.5, f"p50 too high for 404 path: {r['p50'] * 1000:.0f}ms"
        assert r["p99"] < 2.0, f"p99 too high for 404 path: {r['p99'] * 1000:.0f}ms"

    def test_100_concurrent_filtered_listings_stay_fast(self):
        """Verify status-filtered listings stay under p50 1 s / p99 3 s."""
        r = asyncio.run(_hammer("GET", f"{BASE_URL}/optimizations?status=success&limit=10", n=100, concurrency=30))
        _print_results("GET /optimizations?status=success (100 reqs, 30 concurrent)", r)
        assert r["errors"] == 0, f"Errors: {r['errors']} — status codes: {r['status_codes']}"
        assert r["p50"] < 1.0, f"p50 too high for filtered listing: {r['p50'] * 1000:.0f}ms"
        assert r["p99"] < 3.0, f"p99 too high for filtered listing: {r['p99'] * 1000:.0f}ms"
