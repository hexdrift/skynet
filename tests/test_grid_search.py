"""Tests for grid search endpoints (POST /grid-search, GET /jobs/{id}/grid-result)."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict

from fastapi.testclient import TestClient

from core.api.app import create_app
from core.models import (
    GridSearchResponse,
    PairResult,
    RunResponse,
    SplitCounts,
)


class GridSearchService:
    """Mock service that returns a GridSearchResponse with 2 pair results."""

    def validate_payload(self, payload) -> None:
        pass

    def validate_grid_search_payload(self, payload) -> None:
        pass

    def run(self, payload, *, artifact_id=None, progress_callback=None) -> RunResponse:
        return RunResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name="metric",
            split_counts=SplitCounts(train=1, val=0, test=0),
            optimization_metadata={},
            details={},
            runtime_seconds=0.1,
        )

    def run_grid_search(self, payload, *, artifact_id=None, progress_callback=None) -> GridSearchResponse:
        return GridSearchResponse(
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
            metric_name="metric",
            split_counts=SplitCounts(train=1, val=0, test=0),
            total_pairs=2,
            completed_pairs=1,
            failed_pairs=1,
            pair_results=[
                PairResult(
                    pair_index=0,
                    generation_model="openai/gpt-4o-mini",
                    reflection_model="openai/gpt-4o",
                    baseline_test_metric=0.5,
                    optimized_test_metric=0.8,
                    metric_improvement=0.3,
                    runtime_seconds=1.0,
                ),
                PairResult(
                    pair_index=1,
                    generation_model="openai/gpt-4o",
                    reflection_model="openai/gpt-4o",
                    error="Connection timeout",
                ),
            ],
            best_pair=PairResult(
                pair_index=0,
                generation_model="openai/gpt-4o-mini",
                reflection_model="openai/gpt-4o",
                baseline_test_metric=0.5,
                optimized_test_metric=0.8,
                metric_improvement=0.3,
                runtime_seconds=1.0,
            ),
            runtime_seconds=2.0,
        )


def _make_grid_payload() -> Dict[str, Any]:
    return {
        "username": "grid_tester",
        "module_name": "cot",
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
        "generation_models": [
            {"name": "openai/gpt-4o-mini"},
            {"name": "openai/gpt-4o"},
        ],
        "reflection_models": [
            {"name": "openai/gpt-4o"},
        ],
    }


def _wait_terminal(client, job_id, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/jobs/{job_id}/summary")
        if resp.status_code == 200:
            status = resp.json()["status"]
            if status in ("success", "failed", "cancelled"):
                return status
        time.sleep(0.05)
    return None


def test_grid_search_submit_and_complete(configured_env) -> None:
    """POST /grid-search submits a job that completes with job_type=grid_search."""
    app = create_app(service=GridSearchService())
    with TestClient(app) as client:
        resp = client.post("/grid-search", json=_make_grid_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert body["job_type"] == "grid_search"
        job_id = body["job_id"]

        status = _wait_terminal(client, job_id)
        assert status == "success"


def test_grid_search_result_endpoint(configured_env) -> None:
    """GET /jobs/{id}/grid-result returns full GridSearchResponse."""
    app = create_app(service=GridSearchService())
    with TestClient(app) as client:
        resp = client.post("/grid-search", json=_make_grid_payload())
        job_id = resp.json()["job_id"]
        _wait_terminal(client, job_id)

        result = client.get(f"/jobs/{job_id}/grid-result")
        assert result.status_code == 200
        body = result.json()
        assert body["total_pairs"] == 2
        assert body["completed_pairs"] == 1
        assert body["failed_pairs"] == 1
        assert len(body["pair_results"]) == 2
        assert body["best_pair"]["generation_model"] == "openai/gpt-4o-mini"
        assert body["pair_results"][1]["error"] == "Connection timeout"


def test_grid_search_result_on_non_grid_job_404(configured_env) -> None:
    """GET /jobs/{id}/grid-result on a regular /run job returns 404."""
    from conftest import make_payload

    app = create_app(service=GridSearchService())
    with TestClient(app) as client:
        resp = client.post("/run", json=make_payload())
        job_id = resp.json()["job_id"]
        _wait_terminal(client, job_id)

        result = client.get(f"/jobs/{job_id}/grid-result")
        assert result.status_code == 404


def test_grid_search_result_before_completion_409(configured_env, monkeypatch) -> None:
    """GET /jobs/{id}/grid-result on a not-yet-complete job returns 409."""
    monkeypatch.setenv("WORKER_POLL_INTERVAL", "5.0")
    app = create_app(service=GridSearchService())
    with TestClient(app) as client:
        resp = client.post("/grid-search", json=_make_grid_payload())
        job_id = resp.json()["job_id"]

        result = client.get(f"/jobs/{job_id}/grid-result")
        assert result.status_code == 409


def test_grid_search_artifact_endpoint_404(configured_env) -> None:
    """GET /jobs/{id}/artifact on a grid search job returns 404."""
    app = create_app(service=GridSearchService())
    with TestClient(app) as client:
        resp = client.post("/grid-search", json=_make_grid_payload())
        job_id = resp.json()["job_id"]
        _wait_terminal(client, job_id)

        artifact = client.get(f"/jobs/{job_id}/artifact")
        assert artifact.status_code == 404


def test_grid_search_empty_models_422(configured_env) -> None:
    """POST /grid-search with empty model lists returns 422."""
    app = create_app(service=GridSearchService())
    with TestClient(app) as client:
        payload = _make_grid_payload()
        payload["generation_models"] = []
        resp = client.post("/grid-search", json=payload)
        assert resp.status_code == 422

        payload = _make_grid_payload()
        payload["reflection_models"] = []
        resp = client.post("/grid-search", json=payload)
        assert resp.status_code == 422
