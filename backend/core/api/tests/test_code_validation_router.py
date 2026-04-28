"""Tests for the ``/validate-code`` and ``/format-code`` endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ..routers.code_validation import create_code_validation_router


@pytest.fixture
def cv_client() -> TestClient:
    """Build a ``TestClient`` exposing only the code-validation router.

    Returns:
        A ``TestClient`` over a minimal FastAPI app.
    """
    app = FastAPI()
    app.include_router(create_code_validation_router())
    return TestClient(app, raise_server_exceptions=False)


def test_validate_code_returns_invalid_when_no_code_supplied(cv_client: TestClient) -> None:
    """An empty payload is reported as invalid with field-specific errors."""
    payload = {
        "column_mapping": {"inputs": {"q": "question"}, "outputs": {"a": "answer"}},
    }

    resp = cv_client.post("/validate-code", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert any("signature_code" in e or "metric_code" in e for e in body["errors"])


def test_validate_code_signature_parse_error_is_reported(cv_client: TestClient) -> None:
    """Syntactically invalid signature code surfaces as a validation error."""
    payload = {
        "signature_code": "this is not valid python ???",
        "column_mapping": {"inputs": {"q": "question"}, "outputs": {"a": "answer"}},
    }

    resp = cv_client.post("/validate-code", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert len(body["errors"]) > 0


def test_validate_code_valid_signature_returns_signature_fields(cv_client: TestClient) -> None:
    """A valid signature is reported as such with parsed input/output fields."""
    sig = (
        "import dspy\n"
        "class Sig(dspy.Signature):\n"
        "    question: str = dspy.InputField()\n"
        "    answer: str = dspy.OutputField()\n"
    )
    payload = {
        "signature_code": sig,
        "column_mapping": {"inputs": {"question": "question"}, "outputs": {"answer": "answer"}},
    }

    resp = cv_client.post("/validate-code", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["signature_fields"] is not None
    assert "question" in body["signature_fields"]["inputs"]
    assert "answer" in body["signature_fields"]["outputs"]


def test_validate_code_missing_input_column_mapping_reports_error(cv_client: TestClient) -> None:
    """A signature input not present in ``column_mapping.inputs`` is an error."""
    sig = (
        "import dspy\n"
        "class Sig(dspy.Signature):\n"
        "    question: str = dspy.InputField()\n"
        "    answer: str = dspy.OutputField()\n"
    )
    # 'question' field not in column_mapping.inputs
    payload = {
        "signature_code": sig,
        "column_mapping": {"inputs": {"q": "question"}, "outputs": {"answer": "answer"}},
    }

    resp = cv_client.post("/validate-code", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert any("question" in e for e in body["errors"])


def test_validate_code_extra_mapped_column_appears_in_warnings(cv_client: TestClient) -> None:
    """Extra mapped columns that aren't in the signature surface as warnings."""
    sig = (
        "import dspy\n"
        "class Sig(dspy.Signature):\n"
        "    question: str = dspy.InputField()\n"
        "    answer: str = dspy.OutputField()\n"
    )
    # map an extra 'topic' input that doesn't appear in the signature
    payload = {
        "signature_code": sig,
        "column_mapping": {
            "inputs": {"question": "question", "topic": "topic"},
            "outputs": {"answer": "answer"},
        },
    }

    resp = cv_client.post("/validate-code", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert any("topic" in w for w in body["warnings"])


def test_validate_code_metric_parse_error_is_reported(cv_client: TestClient) -> None:
    """Syntactically invalid metric code surfaces as a validation error."""
    payload = {
        "metric_code": "def metric(: this is garbage",
        "column_mapping": {"inputs": {"q": "question"}, "outputs": {"a": "answer"}},
    }

    resp = cv_client.post("/validate-code", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert len(body["errors"]) > 0


def test_validate_code_valid_metric_without_signature_returns_valid(cv_client: TestClient) -> None:
    """A valid metric without signature code passes validation cleanly."""
    metric = "def metric(example, pred, trace=None):\n    return float(example.answer == pred.answer)\n"
    payload = {
        "metric_code": metric,
        "column_mapping": {"inputs": {"q": "question"}, "outputs": {"a": "answer"}},
    }

    resp = cv_client.post("/validate-code", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["errors"] == []


def test_validate_code_gepa_rejects_metric_with_too_few_params(cv_client: TestClient) -> None:
    """GEPA optimizers require five-parameter metrics; fewer is rejected."""
    metric = "def metric(example, pred, trace=None): return 1.0"
    payload = {
        "metric_code": metric,
        "optimizer_name": "gepa",
        "column_mapping": {"inputs": {"q": "question"}, "outputs": {"a": "answer"}},
    }

    resp = cv_client.post("/validate-code", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert any("GEPA" in e for e in body["errors"])


def test_validate_code_gepa_accepts_metric_with_five_params(cv_client: TestClient) -> None:
    """GEPA accepts a metric with the full five-parameter signature."""
    metric = (
        "import dspy\n"
        "def metric(gold, pred, trace, pred_name, pred_trace):\n"
        "    return dspy.Prediction(score=1.0, feedback='ok')\n"
    )
    payload = {
        "metric_code": metric,
        "optimizer_name": "gepa",
        "column_mapping": {"inputs": {"q": "question"}, "outputs": {"a": "answer"}},
    }

    resp = cv_client.post("/validate-code", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    # 5-param signature is accepted; sample_row not supplied so no live run
    assert not any("GEPA" in e for e in body["errors"])


def test_validate_code_returns_422_on_missing_column_mapping(cv_client: TestClient) -> None:
    """``column_mapping`` is required; its absence is a 422."""
    resp = cv_client.post("/validate-code", json={"signature_code": "x = 1"})

    assert resp.status_code == 422


def test_validate_code_returns_422_on_invalid_column_mapping(cv_client: TestClient) -> None:
    """``column_mapping.inputs`` must be non-empty; an empty dict is a 422."""
    payload = {
        "signature_code": "x = 1",
        "column_mapping": {"inputs": {}, "outputs": {"a": "answer"}},
    }

    resp = cv_client.post("/validate-code", json=payload)

    assert resp.status_code == 422


def test_format_code_happy_path_returns_200_and_formatted_code(cv_client: TestClient) -> None:
    """Unformatted but valid Python is normalised by ruff."""
    payload = {"code": "x=1+2\ny  =  3\n"}

    resp = cv_client.post("/format-code", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert isinstance(body["code"], str)
    assert isinstance(body["changed"], bool)


def test_format_code_already_formatted_returns_changed_false(cv_client: TestClient) -> None:
    """Well-formatted code is reported as unchanged."""
    payload = {"code": "x = 1 + 2\ny = 3\n"}

    resp = cv_client.post("/format-code", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["changed"] is False
    assert body["code"] == payload["code"]


def test_format_code_invalid_python_returns_200_with_error_set(cv_client: TestClient) -> None:
    """Syntactically invalid input keeps the original code and reports an error."""
    payload = {"code": "def foo(:\n    pass\n"}

    resp = cv_client.post("/format-code", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    # Original code is preserved on failure
    assert body["code"] == payload["code"]
    assert body["changed"] is False
    assert body["error"] is not None
    assert len(body["error"]) > 0


def test_format_code_empty_payload_returns_422(cv_client: TestClient) -> None:
    """An empty body is rejected with a 422 since ``code`` is required."""
    resp = cv_client.post("/format-code", json={})

    assert resp.status_code == 422


def test_format_code_roundtrip_is_stable(cv_client: TestClient) -> None:
    """Formatting is idempotent: the second pass leaves the result unchanged."""
    payload = {"code": "x=1\ny=2\n"}

    first = cv_client.post("/format-code", json=payload)
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["error"] is None

    second = cv_client.post("/format-code", json={"code": first_body["code"]})
    assert second.status_code == 200
    second_body = second.json()

    assert second_body["changed"] is False
    assert second_body["code"] == first_body["code"]
