"""Tests for the ``/wizard/update`` field-validation surface."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ..routers.wizard import create_wizard_router


@pytest.fixture
def wizard_client() -> TestClient:
    """Build a ``TestClient`` exposing only the wizard router.

    Returns:
        A ``TestClient`` over a minimal FastAPI app.
    """
    app = FastAPI()
    app.include_router(create_wizard_router())
    return TestClient(app, raise_server_exceptions=False)


def test_optimizer_name_alias_accepted(wizard_client: TestClient) -> None:
    """A registered alias like ``gepa`` resolves and is echoed back unchanged."""
    resp = wizard_client.post("/wizard/update", json={"optimizer_name": "gepa"})

    assert resp.status_code == 200
    assert resp.json()["wizard_state"]["optimizer_name"] == "gepa"


def test_optimizer_name_dotted_path_accepted(wizard_client: TestClient) -> None:
    """A fully qualified ``dspy.*`` optimizer path is accepted."""
    resp = wizard_client.post(
        "/wizard/update", json={"optimizer_name": "dspy.teleprompt.GEPA"}
    )

    assert resp.status_code == 200
    assert resp.json()["wizard_state"]["optimizer_name"] == "dspy.teleprompt.GEPA"


def test_optimizer_name_unknown_rejected(wizard_client: TestClient) -> None:
    """An unknown optimizer name produces 422 and surfaces the value in detail."""
    resp = wizard_client.post(
        "/wizard/update", json={"optimizer_name": "not_a_real_optimizer"}
    )

    assert resp.status_code == 422
    assert "not_a_real_optimizer" in resp.json()["detail"]


def test_module_name_alias_accepted(wizard_client: TestClient) -> None:
    """A registered alias like ``predict`` resolves and is echoed back."""
    resp = wizard_client.post("/wizard/update", json={"module_name": "predict"})

    assert resp.status_code == 200
    assert resp.json()["wizard_state"]["module_name"] == "predict"


def test_is_private_accepted_and_echoed(wizard_client: TestClient) -> None:
    """The privacy toggle round-trips so the agent can make a run public."""
    resp = wizard_client.post("/wizard/update", json={"is_private": False})

    assert resp.status_code == 200
    assert resp.json()["wizard_state"]["is_private"] is False


def test_module_name_unknown_rejected(wizard_client: TestClient) -> None:
    """An unknown module name produces 422 and surfaces the value in detail."""
    resp = wizard_client.post(
        "/wizard/update", json={"module_name": "not_a_real_module"}
    )

    assert resp.status_code == 422
    assert "not_a_real_module" in resp.json()["detail"]


def test_model_config_missing_prefix_rejected(wizard_client: TestClient) -> None:
    """A bare model name with no provider prefix is rejected by the prefix guard."""
    resp = wizard_client.post(
        "/wizard/update", json={"model_config": {"name": "gpt-4o-mini"}}
    )

    assert resp.status_code == 422
    assert "gpt-4o-mini" in resp.json()["detail"]
    assert "prefix" in resp.json()["detail"].lower()


def test_model_config_prefixed_accepted(wizard_client: TestClient) -> None:
    """A provider-prefixed model name is accepted and echoed back trimmed."""
    resp = wizard_client.post(
        "/wizard/update", json={"model_config": {"name": "  openai/gpt-4o-mini  "}}
    )

    assert resp.status_code == 200
    patch = resp.json()["wizard_state"]
    assert patch["model_config"]["name"] == "openai/gpt-4o-mini"
    assert patch["model_configured"] is True


def test_optimizer_name_blank_rejected(wizard_client: TestClient) -> None:
    """A blank ``optimizer_name`` falls through to the empty-string guard."""
    resp = wizard_client.post("/wizard/update", json={"optimizer_name": "   "})

    assert resp.status_code == 422


def test_signature_code_rejected(wizard_client: TestClient) -> None:
    """``signature_code`` cannot be hand-patched — it must go through the card."""
    resp = wizard_client.post(
        "/wizard/update",
        json={"signature_code": "class S(dspy.Signature): ..."},
    )

    assert resp.status_code == 422
    assert "request_code_authoring" in resp.json()["detail"]


def test_metric_code_rejected(wizard_client: TestClient) -> None:
    """``metric_code`` cannot be hand-patched — it must go through the card."""
    resp = wizard_client.post(
        "/wizard/update",
        json={"metric_code": "def metric(example, pred, trace=None): return 1.0"},
    )

    assert resp.status_code == 422
    assert "request_code_authoring" in resp.json()["detail"]


@pytest.mark.parametrize(
    "react_config",
    [
        {"mcpUrl": "https://mcp.example/mcp", "toolFilter": ["search"]},
        {"mcp_url": "https://mcp.example/mcp", "tool_filter": ["search"]},
    ],
)
def test_react_config_accepts_both_spellings(wizard_client: TestClient, react_config: dict) -> None:
    """Either spelling lands in the patch under the wizard's camelCase keys."""
    resp = wizard_client.post("/wizard/update", json={"react_config": react_config})

    assert resp.status_code == 200
    echoed = resp.json()["wizard_state"]["react_config"]
    assert echoed["mcpUrl"] == "https://mcp.example/mcp"
    assert echoed["toolFilter"] == ["search"]


def test_react_config_rejects_non_http_url(wizard_client: TestClient) -> None:
    """A tool source that is not an http(s) URL is refused before it reaches the wizard."""
    resp = wizard_client.post("/wizard/update", json={"react_config": {"mcpUrl": "file:///etc/passwd"}})

    assert resp.status_code == 422


def test_target_score_is_a_percentage(wizard_client: TestClient) -> None:
    """A percentage is echoed as a float; values outside 0-100 are refused."""
    ok = wizard_client.post("/wizard/update", json={"target_score": 90})
    too_high = wizard_client.post("/wizard/update", json={"target_score": 101})

    assert ok.status_code == 200
    assert ok.json()["wizard_state"]["target_score"] == 90.0
    assert too_high.status_code == 422
