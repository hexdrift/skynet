"""Probe the service for real user pain points.

Each test represents a scenario a real user would encounter.
Tests that FAIL reveal gaps worth fixing.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from fastapi.testclient import TestClient

from core.api.app import create_app
from core.models import (
    GridSearchResponse,
    PairResult,
    RunResponse,
    SplitCounts,
)


# ---------------------------------------------------------------------------
# Mock services
# ---------------------------------------------------------------------------

class SuccessService:
    def validate_payload(self, payload) -> None:
        pass

    def validate_grid_search_payload(self, payload) -> None:
        pass

    def run(self, payload, *, artifact_id=None, progress_callback=None) -> RunResponse:
        time.sleep(0.05)
        return RunResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name="metric",
            split_counts=SplitCounts(train=1, val=0, test=0),
            baseline_test_metric=0.5,
            optimized_test_metric=0.8,
            metric_improvement=0.3,
            optimization_metadata={},
            details={},
            runtime_seconds=0.05,
        )

    def run_grid_search(self, payload, *, artifact_id=None, progress_callback=None) -> GridSearchResponse:
        pairs = [
            (gen, ref)
            for gen in payload.generation_models
            for ref in payload.reflection_models
        ]
        pair_results = [
            PairResult(
                pair_index=i,
                generation_model=gen.name,
                reflection_model=ref.name,
                baseline_test_metric=0.4,
                optimized_test_metric=0.7 + i * 0.05,
                metric_improvement=0.3 + i * 0.05,
                runtime_seconds=0.01,
            )
            for i, (gen, ref) in enumerate(pairs)
        ]
        successful = [p for p in pair_results if p.optimized_test_metric is not None]
        best = max(successful, key=lambda p: p.optimized_test_metric) if successful else None
        return GridSearchResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name="metric",
            split_counts=SplitCounts(train=1, val=0, test=0),
            total_pairs=len(pairs),
            completed_pairs=len(pairs),
            failed_pairs=0,
            pair_results=pair_results,
            best_pair=best,
            runtime_seconds=0.05,
        )


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------

RUN_PAYLOAD: Dict[str, Any] = {
    "username": "pain_user",
    "module_name": "demo_module",
    "module_kwargs": {},
    "signature_code": (
        "import dspy\n"
        "class Sig(dspy.Signature):\n"
        "    question: str = dspy.InputField()\n"
        "    answer: str = dspy.OutputField()\n"
    ),
    "metric_code": "def metric(example, pred, trace=None):\n    return 1.0\n",
    "optimizer_name": "demo_optimizer",
    "optimizer_kwargs": {},
    "compile_kwargs": {},
    "dataset": [{"question_col": "q1", "answer_col": "a1"}],
    "column_mapping": {
        "inputs": {"question": "question_col"},
        "outputs": {"answer": "answer_col"},
    },
    "split_fractions": {"train": 1.0, "val": 0.0, "test": 0.0},
    "shuffle": False,
    "seed": 42,
    "model_config": {"name": "dummy-model", "temperature": 0.1},
}

GRID_PAYLOAD: Dict[str, Any] = {
    k: v for k, v in RUN_PAYLOAD.items() if k != "model_config"
} | {
    "generation_models": [{"name": "model-a"}, {"name": "model-b"}],
    "reflection_models": [{"name": "model-c"}],
}


def _wait_terminal(client, job_id, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/jobs/{job_id}/summary")
        if resp.status_code == 200:
            status = resp.json()["status"]
            if status in ("success", "failed", "cancelled"):
                return status
        time.sleep(0.05)
    return None


# ---------------------------------------------------------------------------
# Pain point 1: Typo in status filter silently returns empty results
# ---------------------------------------------------------------------------

def test_invalid_status_filter_returns_error(configured_env) -> None:
    """GET /jobs?status=succcess (typo) should tell the user the value is invalid,
    not silently return an empty list that wastes their debugging time."""
    app = create_app(service=SuccessService())
    with TestClient(app) as client:
        # Submit a job so there's data
        submit = client.post("/run", json=RUN_PAYLOAD)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]
        _wait_terminal(client, job_id)

        # Correct filter works
        good = client.get("/jobs", params={"status": "success"})
        assert good.status_code == 200
        assert good.json()["total"] >= 1

        # Typo in status should NOT silently return empty
        bad = client.get("/jobs", params={"status": "succcess"})
        assert bad.status_code == 422, (
            f"Typo 'succcess' was silently accepted (got {bad.status_code}). "
            f"User would see empty results and not understand why."
        )


def test_invalid_job_type_filter_returns_error(configured_env) -> None:
    """GET /jobs?job_type=search (invalid) should tell the user the value is invalid."""
    app = create_app(service=SuccessService())
    with TestClient(app) as client:
        submit = client.post("/run", json=RUN_PAYLOAD)
        assert submit.status_code == 201
        _wait_terminal(client, submit.json()["job_id"])

        # Valid filter
        good = client.get("/jobs", params={"job_type": "run"})
        assert good.status_code == 200
        assert good.json()["total"] >= 1

        # Invalid filter should NOT silently return empty
        bad = client.get("/jobs", params={"job_type": "search"})
        assert bad.status_code == 422, (
            f"Invalid job_type 'search' was silently accepted (got {bad.status_code}). "
            f"User would see empty results. Valid values: 'run', 'grid_search'."
        )


# ---------------------------------------------------------------------------
# Pain point 2: Grid search payload roundtrip
# ---------------------------------------------------------------------------

def test_grid_search_payload_resubmit_roundtrip(configured_env) -> None:
    """A grid search payload should be retrievable and resubmittable."""
    app = create_app(service=SuccessService())
    with TestClient(app) as client:
        submit = client.post("/grid-search", json=GRID_PAYLOAD)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        status = _wait_terminal(client, job_id)
        assert status == "success"

        # Get stored payload
        payload_resp = client.get(f"/jobs/{job_id}/payload")
        assert payload_resp.status_code == 200
        stored = payload_resp.json()["payload"]

        # Resubmit to /grid-search should work without modification
        resubmit = client.post("/grid-search", json=stored)
        assert resubmit.status_code == 201, (
            f"Resubmitting stored grid search payload failed: {resubmit.text}"
        )


# ---------------------------------------------------------------------------
# Pain point 3: Payload endpoint should include job_type for resubmit workflow
# ---------------------------------------------------------------------------

def test_payload_response_includes_job_type(configured_env) -> None:
    """The payload response should tell the user which endpoint to resubmit to.

    Without job_type, the user must make a separate call to /jobs/{id}/summary
    to figure out if the payload goes to /run or /grid-search."""
    app = create_app(service=SuccessService())
    with TestClient(app) as client:
        # Run job
        run_submit = client.post("/run", json=RUN_PAYLOAD)
        assert run_submit.status_code == 201
        run_id = run_submit.json()["job_id"]
        _wait_terminal(client, run_id)

        run_payload = client.get(f"/jobs/{run_id}/payload").json()
        assert "job_type" in run_payload, (
            "Payload response should include job_type so user knows which "
            "endpoint to resubmit to (/run vs /grid-search)"
        )
        assert run_payload["job_type"] == "run"

        # Grid search job
        grid_submit = client.post("/grid-search", json=GRID_PAYLOAD)
        assert grid_submit.status_code == 201
        grid_id = grid_submit.json()["job_id"]
        _wait_terminal(client, grid_id)

        grid_payload = client.get(f"/jobs/{grid_id}/payload").json()
        assert "job_type" in grid_payload
        assert grid_payload["job_type"] == "grid_search"


# ---------------------------------------------------------------------------
# Pain point 4: 400 error shape consistency with 422
# ---------------------------------------------------------------------------

def test_service_validation_error_has_error_key(configured_env) -> None:
    """Service validation errors (400) should include an 'error' key
    matching the shape of Pydantic errors (422) for consistent client handling.

    Currently: 422 → {"error": "invalid_request", "detail": [...]}
               400 → {"detail": "string"}
    The missing 'error' key in 400 responses forces clients to handle two shapes."""
    app = create_app(service=SuccessService())
    with TestClient(app) as client:
        # Trigger a 422 (Pydantic validation)
        bad_422 = client.post("/run", json={"username": "test"})
        assert bad_422.status_code == 422
        body_422 = bad_422.json()
        assert "error" in body_422, "422 should have 'error' key"

        # Trigger a 400 (service validation - bad module_name through the real service)
        # We need to use a payload that passes Pydantic but fails service validation
        # Use a real service (not mock) to hit the validation code path
        from core.api.app import create_app as real_create_app
        real_app = real_create_app()
        with TestClient(real_app) as real_client:
            bad_payload = {**RUN_PAYLOAD, "module_name": "nonexistent_module_xyz"}
            bad_400 = real_client.post("/run", json=bad_payload)
            assert bad_400.status_code == 400
            body_400 = bad_400.json()
            assert "error" in body_400, (
                f"400 response missing 'error' key. Got: {body_400}. "
                f"Clients need a consistent error shape across 400 and 422."
            )
