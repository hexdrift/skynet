"""Load and stress tests for the Skynet API.

Tests API performance under concurrent load. Uses httpx for async
concurrency and measures latency percentiles + error rates.

Requires backend server running on localhost:8000.

Run:
    cd backend && ../.venv/bin/python -m pytest tests/test_load.py -v -s
"""
from __future__ import annotations

import asyncio
import statistics
import time

import httpx
import pytest
import requests

BASE_URL = "http://localhost:8000"


def _server_available() -> bool:
    try:
        return requests.get(f"{BASE_URL}/health", timeout=2).status_code == 200
    except Exception:
        return False


requires_server = pytest.mark.skipif(
    not _server_available(),
    reason="Backend server not running on localhost:8000",
)


async def _hammer(
    method: str,
    url: str,
    n: int,
    concurrency: int,
    json_body: dict | None = None,
) -> dict:
    """Fire n concurrent requests and collect metrics.

    Args:
        method: HTTP method (GET, POST, DELETE).
        url: Full URL to hit.
        n: Total number of requests.
        concurrency: Max simultaneous in-flight requests.
        json_body: JSON body for POST requests.

    Returns:
        Dict with keys: total, errors, status_codes, latencies,
        p50, p95, p99, mean, rps.
    """
    sem = asyncio.Semaphore(concurrency)
    results: list[tuple[int, float]] = []

    async def req(client: httpx.AsyncClient) -> None:
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
    status_codes = {}
    for code, _ in results:
        status_codes[code] = status_codes.get(code, 0) + 1

    return {
        "total": n,
        "errors": sum(1 for code, _ in results if code >= 400 or code == 0),
        "status_codes": status_codes,
        "latencies": latencies,
        "p50": latencies[len(latencies) // 2] if latencies else 0,
        "p95": latencies[int(len(latencies) * 0.95)] if latencies else 0,
        "p99": latencies[int(len(latencies) * 0.99)] if latencies else 0,
        "mean": statistics.mean(latencies) if latencies else 0,
        "total_time": total_time,
        "rps": n / total_time if total_time > 0 else 0,
    }


def _print_results(name: str, r: dict) -> None:
    """Print formatted load test results."""
    print(f"\n{'=' * 50}")
    print(f"  {name}")
    print(f"{'=' * 50}")
    print(f"  Requests:  {r['total']}")
    print(f"  Errors:    {r['errors']} ({r['errors']/r['total']*100:.1f}%)")
    print(f"  RPS:       {r['rps']:.1f}")
    print(f"  Latency:   p50={r['p50']*1000:.0f}ms  p95={r['p95']*1000:.0f}ms  p99={r['p99']*1000:.0f}ms  mean={r['mean']*1000:.0f}ms")
    print(f"  Codes:     {r['status_codes']}")
    print(f"  Total:     {r['total_time']:.1f}s")



@requires_server
class TestReadEndpointLoad:
    """Stress test read-only endpoints."""

    def test_health_100_concurrent(self):
        """100 concurrent GET /health requests."""
        r = asyncio.run(_hammer("GET", f"{BASE_URL}/health", n=100, concurrency=50))
        _print_results("GET /health (100 reqs, 50 concurrent)", r)
        assert r["errors"] == 0, f"Errors: {r['errors']}"
        assert r["p99"] < 2.0, f"p99 latency too high: {r['p99']:.2f}s"

    def test_queue_100_concurrent(self):
        """100 concurrent GET /queue requests."""
        r = asyncio.run(_hammer("GET", f"{BASE_URL}/queue", n=100, concurrency=50))
        _print_results("GET /queue (100 reqs, 50 concurrent)", r)
        assert r["errors"] == 0
        assert r["p99"] < 2.0

    def test_jobs_listing_100_concurrent(self):
        """100 concurrent GET /jobs requests."""
        r = asyncio.run(_hammer("GET", f"{BASE_URL}/jobs?limit=10", n=100, concurrency=50))
        _print_results("GET /jobs (100 reqs, 50 concurrent)", r)
        assert r["errors"] == 0
        assert r["p99"] < 3.0

    def test_health_500_rapid_fire(self):
        """500 requests as fast as possible to /health."""
        r = asyncio.run(_hammer("GET", f"{BASE_URL}/health", n=500, concurrency=100))
        _print_results("GET /health (500 rapid fire, 100 concurrent)", r)
        assert r["errors"] == 0
        assert r["rps"] > 50, f"RPS too low: {r['rps']:.1f}"



@requires_server
class TestWriteEndpointLoad:
    """Stress test write endpoints."""

    def test_rapid_job_submission_10(self):
        """Submit 10 jobs rapidly and verify all are accepted."""
        payload = {
            "username": "load-test-submit",
            "module_name": "predict",
            "signature_code": "import dspy\nclass S(dspy.Signature):\n    q: str = dspy.InputField()\n    a: str = dspy.OutputField()",
            "metric_code": "def metric(e, p, t=None): return 1.0",
            "optimizer_name": "miprov2",
            "dataset": [{"q": "hi", "a": "bye"}],
            "column_mapping": {"inputs": {"q": "q"}, "outputs": {"a": "a"}},
            "model_config": {"name": "gpt-4o-mini"},
        }
        r = asyncio.run(_hammer("POST", f"{BASE_URL}/run", n=10, concurrency=5, json_body=payload))
        _print_results("POST /run (10 rapid submissions)", r)

        assert r["status_codes"].get(201, 0) == 10, f"Not all accepted: {r['status_codes']}"

        jobs = requests.get(f"{BASE_URL}/jobs?username=load-test-submit&limit=50", timeout=10).json()
        for job in jobs["items"]:
            try:
                requests.post(f"{BASE_URL}/jobs/{job['job_id']}/cancel", timeout=5)
                time.sleep(0.5)
                requests.delete(f"{BASE_URL}/jobs/{job['job_id']}", timeout=5)
            except Exception:
                pass

    def test_validation_rejection_under_load(self):
        """50 invalid requests don't crash the server."""
        bad_payload = {"username": "load-test-bad"}  # missing required fields
        r = asyncio.run(_hammer("POST", f"{BASE_URL}/run", n=50, concurrency=20, json_body=bad_payload))
        _print_results("POST /run invalid (50 reqs, 20 concurrent)", r)

        assert r["status_codes"].get(422, 0) == 50, f"Not all 422: {r['status_codes']}"
        assert r["p99"] < 2.0



@requires_server
class TestMixedWorkload:
    """Simulate realistic mixed read/write traffic."""

    def test_mixed_reads_during_job(self):
        """While a job is running, hammer read endpoints concurrently."""
        payload = {
            "username": "load-test-mixed",
            "module_name": "predict",
            "signature_code": "import dspy\nclass S(dspy.Signature):\n    q: str = dspy.InputField()\n    a: str = dspy.OutputField()",
            "metric_code": "def metric(e, p, t=None): return 1.0",
            "optimizer_name": "miprov2",
            "dataset": [{"q": "hi", "a": "bye"}],
            "column_mapping": {"inputs": {"q": "q"}, "outputs": {"a": "a"}},
            "model_config": {"name": "gpt-4o-mini"},
        }
        r = requests.post(f"{BASE_URL}/run", json=payload, timeout=10)
        job_id = r.json()["job_id"]

        async def mixed_load():
            results = {}
            results["health"] = await _hammer("GET", f"{BASE_URL}/health", n=50, concurrency=20)
            results["queue"] = await _hammer("GET", f"{BASE_URL}/queue", n=50, concurrency=20)
            results["jobs"] = await _hammer("GET", f"{BASE_URL}/jobs?limit=5", n=50, concurrency=20)
            results["detail"] = await _hammer("GET", f"{BASE_URL}/jobs/{job_id}", n=30, concurrency=10)
            results["summary"] = await _hammer("GET", f"{BASE_URL}/jobs/{job_id}/summary", n=30, concurrency=10)
            return results

        results = asyncio.run(mixed_load())

        for name, r in results.items():
            _print_results(f"Mixed: {name}", r)
            assert r["errors"] == 0, f"{name} had {r['errors']} errors"

        try:
            requests.post(f"{BASE_URL}/jobs/{job_id}/cancel", timeout=5)
            time.sleep(1)
            requests.delete(f"{BASE_URL}/jobs/{job_id}", timeout=5)
        except Exception:
            pass



@requires_server
class TestDatabaseStress:
    """PostgreSQL under concurrent query load."""

    def test_concurrent_404_lookups(self):
        """200 concurrent lookups for nonexistent jobs — no DB deadlocks."""
        r = asyncio.run(_hammer("GET", f"{BASE_URL}/jobs/nonexistent-load-test", n=200, concurrency=50))
        _print_results("GET /jobs/nonexistent (200 reqs, 50 concurrent)", r)
        assert r["status_codes"].get(404, 0) == 200
        assert r["p99"] < 2.0

    def test_concurrent_listing_with_filters(self):
        """100 concurrent filtered listings."""
        r = asyncio.run(_hammer("GET", f"{BASE_URL}/jobs?status=success&limit=10", n=100, concurrency=30))
        _print_results("GET /jobs?status=success (100 reqs, 30 concurrent)", r)
        assert r["errors"] == 0
        assert r["p99"] < 3.0
