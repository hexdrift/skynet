"""Live golden-path smoke tests for the Skynet backend.

Two tests. Both hit real OpenAI, a real PostgreSQL, and a real running
backend. They exist to answer one question: is the product alive?

Everything else that used to live in this file has been migrated to the
fixture-backed unit tier under `backend/core/**/tests/` — those tests run
in < 20 seconds with zero network dependencies and cover every branch,
error path, and integration boundary that used to be retested here.

What the two tests cover:
    - test_single_run_golden_path  — POST /run → worker subprocess →
      optimizer → artifact persisted → GET /optimizations/{id} reaches
      `success` → POST /serve/{id} returns a real inference.
    - test_grid_search_golden_path — POST /grid-search → fan-out →
      all pairs complete → best_pair selected → POST /serve/{id}/pair/{i}
      returns a real inference.

Together they exercise every layer end-to-end. If both pass against a
deployed environment, the service is functional.

Requires:
    - OPENAI_API_KEY in backend/.env (charged for real LLM calls)
    - Backend server running on localhost:8000
    - PostgreSQL running with skynet database

Run:
    cd backend && ../.venv/bin/python -m pytest tests/test_llm_integration.py -v
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest
import requests
from .conftest import requires_llm, requires_server, wait_for_terminal

BASE_URL = "http://localhost:8000"
DATASET_PATH = Path(__file__).resolve().parents[2] / "data" / "gsm8k.json"

SIGNATURE_CODE = (
    "import dspy\n"
    "class MathReasoning(dspy.Signature):\n"
    '    """Solve grade school math word problems step by step."""\n'
    '    question: str = dspy.InputField(desc="A math word problem")\n'
    '    answer: str = dspy.OutputField(desc="The final numeric answer")\n'
)

METRIC_CODE = """
def gsm8k_metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
    import dspy, re
    def extract(text):
        nums = re.findall(r'-?[\\d,]+\\.?\\d*', (text or '').replace(',', ''))
        return nums[-1] if nums else (text or '').strip()
    if extract(gold.answer or '') == extract(pred.answer or ''):
        return dspy.Prediction(score=1.0, feedback='Correct.')
    return dspy.Prediction(score=0.0, feedback='Wrong.')
"""

MODEL = {
    "name": "openai/gpt-4o-mini",
    "temperature": 1.0,
    "max_tokens": 16000,
}


def _load_dataset(rows: int = 12) -> list[dict]:
    """Load the first *rows* rows from the GSM8K JSON fixture.

    Args:
        rows: Number of rows to return from the head of the dataset.

    Returns:
        A list of dataset row dicts.
    """
    with DATASET_PATH.open() as f:
        return json.load(f)[:rows]


def _common_payload(username: str) -> dict:
    """Build a minimal valid /run request payload for the given username.

    Args:
        username: The username field to embed in the payload.

    Returns:
        A dict suitable for POSTing to /run or /grid-search.
    """
    return {
        "username": username,
        "module_name": "dspy.ChainOfThought",
        "signature_code": SIGNATURE_CODE,
        "metric_code": METRIC_CODE,
        "optimizer_name": "gepa",
        "optimizer_kwargs": {"auto": "light", "num_threads": 2},
        "dataset": _load_dataset(),
        "column_mapping": {
            "inputs": {"question": "question"},
            "outputs": {"answer": "answer"},
        },
        "split_fractions": {"train": 0.5, "val": 0.25, "test": 0.25},
        "shuffle": True,
        "seed": 42,
    }


def _cleanup(job_id: str) -> None:
    """Delete the optimization job, suppressing any errors.

    Args:
        job_id: The optimization ID to delete.
    """
    with contextlib.suppress(Exception):
        requests.delete(f"{BASE_URL}/optimizations/{job_id}", timeout=10)


@pytest.mark.e2e
@pytest.mark.slow
@requires_llm
@requires_server
def test_single_run_golden_path() -> None:
    """Submit a real optimization, wait for success, serve an inference."""
    payload = _common_payload("e2e-golden-single")
    payload["name"] = "golden path single-run smoke"
    payload["model_config"] = MODEL
    payload["reflection_model_config"] = MODEL

    r = requests.post(f"{BASE_URL}/run", json=payload, timeout=30)
    assert r.status_code == 201, f"submit failed ({r.status_code}): {r.text}"
    job_id = r.json()["optimization_id"]

    try:
        final = wait_for_terminal(job_id, timeout=900)
        assert final["status"] == "success", (
            f"expected success, got {final['status']}: {final.get('message')}"
        )

        result = final["result"]
        assert result is not None, "completed job missing result payload"
        assert isinstance(result["baseline_test_metric"], (int, float))
        assert isinstance(result["optimized_test_metric"], (int, float))
        assert result["num_lm_calls"] > 0, "optimizer should have called the LM"
        artifact = result["program_artifact"]
        assert artifact["program_pickle_base64"], "artifact missing pickled program"

        inference = requests.post(
            f"{BASE_URL}/serve/{job_id}",
            json={"inputs": {"question": "What is 12 + 7?"}},
            timeout=60,
        )
        assert inference.status_code == 200, (
            f"serve returned {inference.status_code}: {inference.text}"
        )
        body = inference.json()
        assert "answer" in body["outputs"], f"missing answer in outputs: {body}"
        assert body["outputs"]["answer"], "answer should not be empty"
    finally:
        _cleanup(job_id)


@pytest.mark.e2e
@pytest.mark.slow
@requires_llm
@requires_server
def test_grid_search_golden_path() -> None:
    """Submit a real 2-pair grid-search, wait for success, serve best-pair inference."""
    payload = _common_payload("e2e-golden-grid")
    payload["name"] = "golden path grid-search smoke"
    payload["model_config"] = MODEL
    payload["generation_models"] = [MODEL]
    payload["reflection_models"] = [MODEL, MODEL]

    r = requests.post(f"{BASE_URL}/grid-search", json=payload, timeout=30)
    assert r.status_code == 201, f"submit failed ({r.status_code}): {r.text}"
    job_id = r.json()["optimization_id"]

    try:
        final = wait_for_terminal(job_id, timeout=1500)
        assert final["status"] == "success", (
            f"expected success, got {final['status']}: {final.get('message')}"
        )

        grid = final["grid_result"]
        assert grid is not None, "grid-search job missing grid_result"
        assert grid["total_pairs"] == 2
        assert grid["completed_pairs"] == 2
        assert grid["failed_pairs"] == 0

        best = grid["best_pair"]
        assert best is not None, "grid-search missing best_pair"
        assert best["program_artifact"]["program_pickle_base64"]

        pair_index = best["pair_index"]
        inference = requests.post(
            f"{BASE_URL}/serve/{job_id}/pair/{pair_index}",
            json={"inputs": {"question": "What is 8 + 5?"}},
            timeout=60,
        )
        assert inference.status_code == 200, (
            f"pair serve returned {inference.status_code}: {inference.text}"
        )
        body = inference.json()
        assert "answer" in body["outputs"], f"missing answer in outputs: {body}"
        assert body["outputs"]["answer"], "answer should not be empty"
    finally:
        _cleanup(job_id)
