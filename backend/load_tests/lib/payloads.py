"""Canonical request payload builders for load-test scenarios.

All builders point at the mock LM server by default so the worker subprocess
never reaches a real provider. ``mock_lm_url`` is the OpenAI-compatible base
URL; the harness sets it to ``http://mock-lm:9000/v1`` inside Docker Compose
and to ``http://localhost:9000/v1`` for host-side smoke runs.
"""

from __future__ import annotations

from typing import Any

CANONICAL_SIGNATURE_CODE = (
    "import dspy\n"
    "class S(dspy.Signature):\n"
    "    q: str = dspy.InputField()\n"
    "    a: str = dspy.OutputField()\n"
)
CANONICAL_METRIC_CODE = "def metric(gold, pred, trace=None, pred_name=None, pred_trace=None): return 1.0\n"
CANONICAL_COLUMN_MAPPING = {"inputs": {"q": "q"}, "outputs": {"a": "a"}}
_DATASET = [{"q": f"question-{i}", "a": "yes"} for i in range(8)]


def run_payload(
    *,
    username: str,
    mock_lm_url: str,
    name: str | None = None,
    model: str = "openai/gpt-4o-mini",
) -> dict[str, Any]:
    """Build a minimal valid ``POST /run`` payload pointed at the mock LM.

    Args:
        username: Owner for the optimization; mirrored into the
            ``username`` field of the request body. The router overwrites
            this with the authenticated identity, so the only effect is
            documentation.
        mock_lm_url: Base URL of the mock LM (e.g. ``http://mock-lm:9000/v1``).
        name: Display name for the optimization. Auto-generated when omitted.
        model: LiteLLM model identifier. Any ``openai/*`` value works
            because the mock accepts every name.

    Returns:
        A dict ready to pass as ``json=`` to httpx.
    """
    return {
        "name": name or f"load-{username}",
        "username": username,
        "module_name": "predict",
        "module_kwargs": {},
        "signature_code": CANONICAL_SIGNATURE_CODE,
        "metric_code": CANONICAL_METRIC_CODE,
        "optimizer_name": "gepa",
        "optimizer_kwargs": {"auto": "light"},
        "compile_kwargs": {},
        "dataset": list(_DATASET),
        "column_mapping": CANONICAL_COLUMN_MAPPING,
        "model_config": {"name": model, "base_url": mock_lm_url},
        "reflection_model_config": {"name": model, "base_url": mock_lm_url},
    }


def grid_payload(
    *,
    username: str,
    mock_lm_url: str,
    name: str | None = None,
) -> dict[str, Any]:
    """Build a minimal valid ``POST /grid-search`` payload.

    Args:
        username: Submitter recorded on the request body.
        mock_lm_url: Base URL of the mock LM, propagated to every model.
        name: Display name; auto-generated when omitted.

    Returns:
        A dict shaped like :class:`GridSearchRequest` with a 2x1 grid.
    """
    return {
        "name": name or f"grid-{username}",
        "username": username,
        "module_name": "predict",
        "module_kwargs": {},
        "signature_code": CANONICAL_SIGNATURE_CODE,
        "metric_code": CANONICAL_METRIC_CODE,
        "optimizer_name": "gepa",
        "optimizer_kwargs": {"auto": "light"},
        "compile_kwargs": {},
        "dataset": list(_DATASET),
        "column_mapping": CANONICAL_COLUMN_MAPPING,
        "generation_models": [
            {"name": "openai/gpt-4o-mini", "base_url": mock_lm_url},
            {"name": "openai/gpt-4o", "base_url": mock_lm_url},
        ],
        "reflection_models": [
            {"name": "openai/gpt-4o", "base_url": mock_lm_url},
        ],
    }
