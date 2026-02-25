"""Probe the service from a real user's perspective to surface UX gaps.

Each test simulates a concrete user scenario and asserts on what the user
would expect to see.  Failures here indicate real pain points.
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
from core.worker import reset_worker_for_tests


# ---------------------------------------------------------------------------
# Mock services
# ---------------------------------------------------------------------------

class SuccessService:
    def validate_payload(self, payload) -> None:
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


class FailingService:
    """Service that fails during execution with a realistic error."""

    def validate_payload(self, payload) -> None:
        pass

    def run(self, payload, *, artifact_id=None, progress_callback=None) -> RunResponse:
        if progress_callback:
            progress_callback("dataset_splits_ready", {"train": 1, "val": 0, "test": 0})
        raise RuntimeError(
            "litellm.APIError: OpenAI API rate limit exceeded. "
            "Retry after 60 seconds."
        )


class MixedGridService:
    """Grid search where some pairs succeed and some fail."""

    def validate_payload(self, payload) -> None:
        pass

    def validate_grid_search_payload(self, payload) -> None:
        pass

    def run_grid_search(self, payload, *, artifact_id=None, progress_callback=None) -> GridSearchResponse:
        pairs = [
            (gen, ref)
            for gen in payload.generation_models
            for ref in payload.reflection_models
        ]
        pair_results = []
        for i, (gen, ref) in enumerate(pairs):
            if i % 2 == 0:
                # Success
                pair_results.append(PairResult(
                    pair_index=i,
                    generation_model=gen.name,
                    reflection_model=ref.name,
                    baseline_test_metric=0.4,
                    optimized_test_metric=0.8,
                    metric_improvement=0.4,
                    runtime_seconds=0.01,
                ))
            else:
                # Failure
                pair_results.append(PairResult(
                    pair_index=i,
                    generation_model=gen.name,
                    reflection_model=ref.name,
                    error="API rate limit exceeded",
                    runtime_seconds=0.01,
                ))

        completed = len([p for p in pair_results if p.error is None])
        failed = len([p for p in pair_results if p.error is not None])
        successful = [p for p in pair_results if p.error is None and p.optimized_test_metric is not None]
        best = max(successful, key=lambda p: p.optimized_test_metric) if successful else None

        return GridSearchResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name="metric",
            split_counts=SplitCounts(train=1, val=0, test=0),
            total_pairs=len(pairs),
            completed_pairs=completed,
            failed_pairs=failed,
            pair_results=pair_results,
            best_pair=best,
            runtime_seconds=0.05,
        )


class AllFailGridService:
    """Grid search where every pair fails."""

    def validate_payload(self, payload) -> None:
        pass

    def validate_grid_search_payload(self, payload) -> None:
        pass

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
                error="Connection refused",
                runtime_seconds=0.01,
            )
            for i, (gen, ref) in enumerate(pairs)
        ]
        return GridSearchResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name="metric",
            split_counts=SplitCounts(train=1, val=0, test=0),
            total_pairs=len(pairs),
            completed_pairs=0,
            failed_pairs=len(pairs),
            pair_results=pair_results,
            best_pair=None,
            runtime_seconds=0.03,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_PAYLOAD: Dict[str, Any] = {
    "username": "probe_user",
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
    "reflection_models": [{"name": "model-c"}, {"name": "model-d"}],
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
# Probe 1: Failed job — is the error accessible and useful?
# ---------------------------------------------------------------------------

def test_failed_job_error_is_accessible(configured_env) -> None:
    """When a job fails, the user should see a useful error in the job detail
    and the traceback should be accessible in logs."""
    app = create_app(service=FailingService())
    with TestClient(app) as client:
        submit = client.post("/run", json=RUN_PAYLOAD)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        status = _wait_terminal(client, job_id)
        assert status == "failed", f"Expected failed, got {status}"

        # Full detail should have a useful error message
        detail = client.get(f"/jobs/{job_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["status"] == "failed"
        assert body["message"] is not None
        assert len(body["message"]) > 10, (
            f"Error message too short to be useful: '{body['message']}'"
        )

        # The error should mention the actual problem
        assert "rate limit" in body["message"].lower() or "api" in body["message"].lower(), (
            f"Error message doesn't mention the actual problem: '{body['message']}'"
        )

        # completed_at should be set for failed jobs
        assert body["completed_at"] is not None, "Failed job should have completed_at set"

        # elapsed should be computable
        assert body["elapsed"] is not None, "Failed job should have elapsed time"
        assert body["elapsed_seconds"] is not None


# ---------------------------------------------------------------------------
# Probe 2: Failed/cancelled job — payload retrieval for resubmit
# ---------------------------------------------------------------------------

def test_cancelled_job_payload_retrievable_for_resubmit(configured_env) -> None:
    """A user should be able to retrieve the payload from a cancelled job
    and resubmit it directly."""
    app = create_app(service=SuccessService())
    with TestClient(app) as client:
        submit = client.post("/run", json=RUN_PAYLOAD)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        # Cancel immediately
        cancel = client.post(f"/jobs/{job_id}/cancel")
        assert cancel.status_code == 200

        # Payload should still be accessible
        payload_resp = client.get(f"/jobs/{job_id}/payload")
        assert payload_resp.status_code == 200, (
            f"Payload should be accessible for cancelled jobs: {payload_resp.text}"
        )
        stored = payload_resp.json()["payload"]

        # Resubmit should work
        resubmit = client.post("/run", json=stored)
        assert resubmit.status_code == 201, (
            f"Resubmitting cancelled job payload should work: {resubmit.text}"
        )


def test_failed_job_payload_retrievable_for_resubmit(configured_env) -> None:
    """A user should be able to retrieve the payload from a failed job
    and resubmit it."""
    app = create_app(service=FailingService())
    with TestClient(app) as client:
        submit = client.post("/run", json=RUN_PAYLOAD)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        status = _wait_terminal(client, job_id)
        assert status == "failed"

        # Payload should still be accessible
        payload_resp = client.get(f"/jobs/{job_id}/payload")
        assert payload_resp.status_code == 200
        stored = payload_resp.json()["payload"]

        # Resubmit should be accepted (will fail again, but that's OK)
        resubmit = client.post("/run", json=stored)
        assert resubmit.status_code == 201


# ---------------------------------------------------------------------------
# Probe 3: Grid search full detail — per-pair results for failed grid search
# ---------------------------------------------------------------------------

def test_failed_grid_search_detail_includes_per_pair_results(configured_env) -> None:
    """When a grid search fails (all pairs failed), the full job detail
    should include the grid_result so users can see per-pair errors
    without making a separate API call."""
    app = create_app(service=AllFailGridService())
    with TestClient(app) as client:
        submit = client.post("/grid-search", json=GRID_PAYLOAD)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        status = _wait_terminal(client, job_id)
        assert status == "failed"

        # The dedicated grid-result endpoint works (already tested)
        grid_resp = client.get(f"/jobs/{job_id}/grid-result")
        assert grid_resp.status_code == 200
        grid_data = grid_resp.json()
        assert grid_data["failed_pairs"] > 0

        # The FULL DETAIL endpoint should ALSO include grid_result
        detail = client.get(f"/jobs/{job_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["grid_result"] is not None, (
            "Full job detail for a failed grid search should include grid_result "
            "with per-pair error details. Currently the user must make a separate "
            "GET /jobs/{id}/grid-result call to see what went wrong."
        )
        assert body["grid_result"]["failed_pairs"] == grid_data["failed_pairs"]


def test_mixed_grid_search_detail_includes_grid_result(configured_env) -> None:
    """Grid search with mixed results (some succeed, some fail) should
    include grid_result in the full detail."""
    app = create_app(service=MixedGridService())
    with TestClient(app) as client:
        submit = client.post("/grid-search", json=GRID_PAYLOAD)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        status = _wait_terminal(client, job_id)
        assert status == "success"

        detail = client.get(f"/jobs/{job_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["grid_result"] is not None, (
            "Full detail for successful grid search should include grid_result"
        )
        assert body["grid_result"]["completed_pairs"] > 0
        assert body["grid_result"]["failed_pairs"] > 0


# ---------------------------------------------------------------------------
# Probe 4: Job type filtering on /jobs endpoint
# ---------------------------------------------------------------------------

def test_job_type_filtering_works(configured_env) -> None:
    """GET /jobs?job_type=run and job_type=grid_search should filter correctly."""
    app = create_app(service=MixedGridService())
    with TestClient(app) as client:
        # Submit a run job
        run_resp = client.post("/run", json=RUN_PAYLOAD)
        assert run_resp.status_code == 201
        run_id = run_resp.json()["job_id"]

        # Submit a grid search job
        grid_resp = client.post("/grid-search", json=GRID_PAYLOAD)
        assert grid_resp.status_code == 201
        grid_id = grid_resp.json()["job_id"]

        # Wait for both to finish
        _wait_terminal(client, run_id)
        _wait_terminal(client, grid_id)

        # Filter by run type
        run_listing = client.get("/jobs", params={"job_type": "run"})
        assert run_listing.status_code == 200
        run_items = run_listing.json()["items"]
        assert len(run_items) >= 1
        assert all(j["job_type"] == "run" for j in run_items), (
            f"job_type filter broken: got types {[j['job_type'] for j in run_items]}"
        )

        # Filter by grid_search type
        grid_listing = client.get("/jobs", params={"job_type": "grid_search"})
        assert grid_listing.status_code == 200
        grid_items = grid_listing.json()["items"]
        assert len(grid_items) >= 1
        assert all(j["job_type"] == "grid_search" for j in grid_items), (
            f"job_type filter broken: got types {[j['job_type'] for j in grid_items]}"
        )

        # No cross-contamination
        run_ids = {j["job_id"] for j in run_items}
        grid_ids = {j["job_id"] for j in grid_items}
        assert grid_id not in run_ids, "Grid search job appeared in run-type listing"
        assert run_id not in grid_ids, "Run job appeared in grid-search-type listing"


# ---------------------------------------------------------------------------
# Probe 5: Summary response consistency between run and grid search jobs
# ---------------------------------------------------------------------------

def test_summary_fields_consistent_across_job_types(configured_env) -> None:
    """Both run and grid search summaries should have the core fields populated."""
    app = create_app(service=MixedGridService())
    with TestClient(app) as client:
        # Submit run
        run_resp = client.post("/run", json=RUN_PAYLOAD)
        run_id = run_resp.json()["job_id"]
        _wait_terminal(client, run_id)

        # Submit grid search
        grid_resp = client.post("/grid-search", json=GRID_PAYLOAD)
        grid_id = grid_resp.json()["job_id"]
        _wait_terminal(client, grid_id)

        # Get both summaries
        run_summary = client.get(f"/jobs/{run_id}/summary").json()
        grid_summary = client.get(f"/jobs/{grid_id}/summary").json()

        # Core fields should be populated for both
        for summary, label in [(run_summary, "run"), (grid_summary, "grid")]:
            assert summary["job_id"] is not None, f"{label}: missing job_id"
            assert summary["job_type"] is not None, f"{label}: missing job_type"
            assert summary["status"] is not None, f"{label}: missing status"
            assert summary["username"] is not None, f"{label}: missing username"
            assert summary["module_name"] is not None, f"{label}: missing module_name"
            assert summary["optimizer_name"] is not None, f"{label}: missing optimizer_name"
            assert summary["dataset_rows"] is not None, f"{label}: missing dataset_rows"
            assert summary["elapsed"] is not None, f"{label}: missing elapsed"
            assert summary["elapsed_seconds"] is not None, f"{label}: missing elapsed_seconds"

        # Run-specific fields
        assert run_summary["model_name"] is not None, "run: missing model_name"
        assert run_summary["job_type"] == "run"

        # Grid-specific fields
        assert grid_summary["job_type"] == "grid_search"
        assert grid_summary["total_pairs"] is not None, "grid: missing total_pairs"
        assert grid_summary["total_pairs"] == 4  # 2 gen × 2 ref
