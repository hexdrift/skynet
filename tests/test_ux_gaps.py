"""Challenge the service from a real user's perspective to find UX gaps.

Exercises resubmit flows, edge cases, and response consistency.
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
        time.sleep(0.05)

    def run(self, payload, *, artifact_id=None, progress_callback=None) -> RunResponse:
        time.sleep(0.1)
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
            runtime_seconds=0.1,
        )


class AllPairsFailGridService:
    """Grid search service where every pair fails."""

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
            optimization_metadata={},
            details={},
            runtime_seconds=0.05,
        )

    def run_grid_search(
        self,
        payload,
        *,
        artifact_id=None,
        progress_callback=None,
    ) -> GridSearchResponse:
        """Every pair throws an exception."""
        pairs = [
            (gen, ref)
            for gen in payload.generation_models
            for ref in payload.reflection_models
        ]
        pair_results = []
        for i, (gen, ref) in enumerate(pairs):
            if progress_callback:
                progress_callback("grid_pair_started", {
                    "pair_index": i,
                    "generation_model": gen.name,
                    "reflection_model": ref.name,
                })
            pair_results.append(PairResult(
                pair_index=i,
                generation_model=gen.name,
                reflection_model=ref.name,
                error="API rate limit exceeded",
                runtime_seconds=0.01,
            ))
            if progress_callback:
                progress_callback("grid_pair_failed", {
                    "pair_index": i,
                    "error": "API rate limit exceeded",
                    "completed_so_far": 0,
                    "failed_so_far": i + 1,
                })

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
            runtime_seconds=0.05,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_PAYLOAD: Dict[str, Any] = {
    "username": "tester",
    "module_name": "demo_module",
    "module_kwargs": {},
    "signature_code": (
        "import dspy\n"
        "class Sig(dspy.Signature):\n"
        "    question: str = dspy.InputField()\n"
        "    answer: str = dspy.OutputField()\n"
    ),
    "metric_code": (
        "def metric(example, pred, trace=None):\n"
        "    return 1.0\n"
    ),
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


def _wait_for_status(client, job_id, target, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/jobs/{job_id}/summary")
        if resp.status_code == 200 and resp.json()["status"] == target:
            return True
        time.sleep(0.05)
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_payload_resubmit_field_names_match_api_contract(configured_env) -> None:
    """GET /jobs/{id}/payload should return field names matching the API contract.

    The API contract uses `model_config` (alias), not `model_settings` (internal).
    If stored with internal names, resubmit works but the payload looks different
    from what the user originally sent.
    """
    app = create_app(service=SuccessService())
    with TestClient(app) as client:
        submit = client.post("/run", json=BASE_PAYLOAD)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        assert _wait_for_status(client, job_id, "success")

        # Get the stored payload
        resp = client.get(f"/jobs/{job_id}/payload")
        assert resp.status_code == 200
        stored = resp.json()["payload"]

        # The user sent "model_config" -- the stored payload should use the
        # same key so resubmit is seamless.
        assert "model_config" in stored, (
            f"Stored payload uses internal field name 'model_settings' "
            f"instead of API alias 'model_config'. Keys: {sorted(stored.keys())}"
        )

        # Resubmit should work directly
        resubmit = client.post("/run", json=stored)
        assert resubmit.status_code == 201, (
            f"Resubmitting stored payload failed: {resubmit.text}"
        )


def test_grid_search_all_pairs_failed_status_is_not_success(configured_env) -> None:
    """When every pair in a grid search fails, the job status should NOT be 'success'.

    A user seeing status='success' when all pairs failed is misleading.
    """
    app = create_app(service=AllPairsFailGridService())
    grid_payload = {
        **{k: v for k, v in BASE_PAYLOAD.items() if k != "model_config"},
        "generation_models": [{"name": "model-a"}, {"name": "model-b"}],
        "reflection_models": [{"name": "model-c"}],
    }
    with TestClient(app) as client:
        submit = client.post("/grid-search", json=grid_payload)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        # Wait for terminal state
        deadline = time.time() + 8
        final_status = None
        while time.time() < deadline:
            resp = client.get(f"/jobs/{job_id}/summary")
            if resp.status_code == 200:
                final_status = resp.json()["status"]
                if final_status in ("success", "failed", "cancelled"):
                    break
            time.sleep(0.05)

        assert final_status == "failed", (
            f"Grid search where ALL pairs failed should have status='failed', "
            f"got status='{final_status}'"
        )

        # The error message should explain what happened
        detail = client.get(f"/jobs/{job_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert "all" in (body.get("message") or "").lower() or \
               "pair" in (body.get("message") or "").lower(), \
            f"Error message should mention that all pairs failed: {body.get('message')}"

        # Grid result should still be accessible so user can see per-pair errors
        grid_resp = client.get(f"/jobs/{job_id}/grid-result")
        assert grid_resp.status_code == 200, (
            f"Grid result should be accessible even when all pairs failed "
            f"(status {grid_resp.status_code}): {grid_resp.text}"
        )
        grid_data = grid_resp.json()
        assert grid_data["completed_pairs"] == 0
        assert grid_data["failed_pairs"] == 2
        assert all(p["error"] is not None for p in grid_data["pair_results"])


def test_elapsed_seconds_numeric_field_available(configured_env) -> None:
    """Job responses should include a numeric elapsed_seconds alongside the HH:MM:SS string.

    Clients building dashboards need numeric values for sorting and calculations.
    """
    app = create_app(service=SuccessService())
    with TestClient(app) as client:
        submit = client.post("/run", json=BASE_PAYLOAD)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]

        assert _wait_for_status(client, job_id, "success")

        # Check summary
        summary = client.get(f"/jobs/{job_id}/summary")
        assert summary.status_code == 200
        sbody = summary.json()
        assert "elapsed_seconds" in sbody, (
            "Summary response should include numeric elapsed_seconds field"
        )
        assert isinstance(sbody["elapsed_seconds"], (int, float))
        assert sbody["elapsed_seconds"] >= 0

        # Check full detail
        detail = client.get(f"/jobs/{job_id}")
        assert detail.status_code == 200
        dbody = detail.json()
        assert "elapsed_seconds" in dbody, (
            "Detail response should include numeric elapsed_seconds field"
        )
        assert isinstance(dbody["elapsed_seconds"], (int, float))

        # Check listing
        listing = client.get("/jobs", params={"username": "tester"})
        assert listing.status_code == 200
        items = listing.json()["items"]
        assert items
        assert "elapsed_seconds" in items[0], (
            "Listing response should include numeric elapsed_seconds field"
        )

        # elapsed_seconds should match elapsed (HH:MM:SS) within a reasonable tolerance
        # Convert HH:MM:SS to seconds for comparison
        elapsed_str = sbody["elapsed"]
        parts = elapsed_str.split(":")
        elapsed_from_str = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        # They should agree within 1 second (int truncation)
        assert abs(sbody["elapsed_seconds"] - elapsed_from_str) <= 1.0


def test_payload_resubmit_roundtrip(configured_env) -> None:
    """A stored payload can be resubmitted to POST /run without modification."""
    app = create_app(service=SuccessService())
    with TestClient(app) as client:
        submit = client.post("/run", json=BASE_PAYLOAD)
        assert submit.status_code == 201
        job_id = submit.json()["job_id"]
        assert _wait_for_status(client, job_id, "success")

        # Get stored payload and resubmit it directly
        stored = client.get(f"/jobs/{job_id}/payload").json()["payload"]
        resubmit = client.post("/run", json=stored)
        assert resubmit.status_code == 201
        job_id_2 = resubmit.json()["job_id"]
        assert _wait_for_status(client, job_id_2, "success")

        # Verify the resubmitted job has the same config
        s1 = client.get(f"/jobs/{job_id}/summary").json()
        s2 = client.get(f"/jobs/{job_id_2}/summary").json()
        assert s1["module_name"] == s2["module_name"]
        assert s1["optimizer_name"] == s2["optimizer_name"]
        assert s1["model_name"] == s2["model_name"]
