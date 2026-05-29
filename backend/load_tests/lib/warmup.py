"""Validation-cache pre-warming for the load-test harness.

The submit-time validators (``validate_signature_code`` /
``validate_metric_code``) spawn a fresh Python interpreter and import
dspy in a subprocess. A clean cold start is ~5 s; under 32-concurrent
burst load it balloons past the 30 s parse timeout and the first
request from each uvicorn worker fails — taking the dogpile-protected
cache with it, since the cache only populates on success.

Hitting ``/validate-code`` serially before the burst gives each
replica's per-process cache one uncontested cold start. After warmup,
every burst request is a cache hit, and the scenario actually exercises
the queue path rather than the validation cold-start path.

The number of warm-up calls (``WARMUP_CALLS``) is intentionally a
small multiple of the replica count so that nginx round-robin reaches
every replica even if a few calls land on the same one.
"""

from __future__ import annotations

import time

import httpx

from .auth import auth_headers
from .payloads import (
    CANONICAL_COLUMN_MAPPING,
    CANONICAL_METRIC_CODE,
    CANONICAL_SIGNATURE_CODE,
)

WARMUP_CALLS = 6
WARMUP_USERNAME = "load-user-warmup"
WARMUP_TIMEOUT_SECONDS = 90.0


def _warmup_payload() -> dict[str, object]:
    """Build the ``/validate-code`` body used to warm each replica.

    Returns:
        A request body with the same signature/metric strings the
        scenario payloads use, so the cache keys line up.
    """
    return {
        "signature_code": CANONICAL_SIGNATURE_CODE,
        "metric_code": CANONICAL_METRIC_CODE,
        "column_mapping": CANONICAL_COLUMN_MAPPING,
        "optimizer_name": "gepa",
    }


async def warm_validation_cache(api_base_url: str) -> dict[str, float | int]:
    """Send ``WARMUP_CALLS`` serial ``/validate-code`` POSTs through the LB.

    Serial — never concurrent — so each replica's first cold spawn
    completes uncontested. Returns timing data so the orchestrator can
    log how long the warm-up took.

    Args:
        api_base_url: Base URL of the load-balancer (e.g.
            ``http://localhost:58000``).

    Returns:
        A dict with ``calls``, ``failures``, ``elapsed_seconds`` and the
        per-call latencies in ``latencies_ms`` so a regression in cache
        behaviour is visible in the suite log.
    """
    body = _warmup_payload()
    headers = auth_headers(WARMUP_USERNAME)
    latencies_ms: list[float] = []
    failures = 0
    t_start = time.monotonic()
    async with httpx.AsyncClient(http2=False) as client:
        for _ in range(WARMUP_CALLS):
            t0 = time.monotonic()
            try:
                response = await client.post(
                    f"{api_base_url}/validate-code",
                    json=body,
                    headers=headers,
                    timeout=WARMUP_TIMEOUT_SECONDS,
                )
                latencies_ms.append((time.monotonic() - t0) * 1000.0)
                if response.status_code != 200:
                    failures += 1
            except (httpx.HTTPError, OSError):
                latencies_ms.append((time.monotonic() - t0) * 1000.0)
                failures += 1
    elapsed = time.monotonic() - t_start
    return {
        "calls": WARMUP_CALLS,
        "failures": failures,
        "elapsed_seconds": elapsed,
        "latencies_ms": latencies_ms,
    }
