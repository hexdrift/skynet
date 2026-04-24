from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from core.models.submissions import GridSearchRequest, OptimizationSubmissionResponse, RunRequest
from core.models.common import OptimizationStatus


def _base_payload(**overrides) -> dict:
    """Return a minimal valid RunRequest payload dict with optional overrides."""
    base = dict(
        username="alice",
        module_name="predict",
        signature_code="class S: pass",
        metric_code="def m(e, p): return 1.0",
        optimizer_name="gepa",
        dataset=[{"q": "1+1", "a": "2"}],
        column_mapping={"inputs": {"q": "q"}, "outputs": {"a": "a"}},
        model_config={"name": "gpt-4o-mini"},
    )
    base.update(overrides)
    return base



def test_run_request_accepts_minimal_payload() -> None:
    """Verify RunRequest parses a minimal valid payload."""
    req = RunRequest.model_validate(_base_payload())

    assert req.model_settings.name == "gpt-4o-mini"
    assert req.dataset == [{"q": "1+1", "a": "2"}]


def test_run_request_model_settings_via_alias() -> None:
    """Verify RunRequest exposes model_config as model_settings via alias."""
    req = RunRequest.model_validate(_base_payload())

    assert req.model_settings.name == "gpt-4o-mini"


def test_run_request_rejects_empty_dataset() -> None:
    """Verify RunRequest rejects a payload with an empty dataset."""
    with pytest.raises(ValidationError, match="at least one row"):
        RunRequest.model_validate(_base_payload(dataset=[]))


@pytest.mark.parametrize("length,valid", [
    (0, True),
    (280, True),
    (281, False),
], ids=["empty_description", "max", "over_max"])
def test_run_request_description_length_boundary(length: int, valid: bool) -> None:
    """Verify RunRequest accepts description up to 280 chars and rejects longer."""
    kwargs = _base_payload()
    if length == 0:
        kwargs.pop("description", None)
    else:
        kwargs["description"] = "x" * length

    if valid:
        req = RunRequest.model_validate(kwargs)
        if length > 0:
            assert len(req.description) == length
    else:
        with pytest.raises(ValidationError):
            RunRequest.model_validate(kwargs)


def test_run_request_split_fractions_default() -> None:
    """Verify RunRequest defaults split_fractions to values summing to 1.0."""
    req = RunRequest.model_validate(_base_payload())

    assert abs(req.split_fractions.train + req.split_fractions.val + req.split_fractions.test - 1.0) < 1e-6


def test_run_request_shuffle_default_true() -> None:
    """Verify RunRequest defaults shuffle to True."""
    req = RunRequest.model_validate(_base_payload())

    assert req.shuffle is True


def test_run_request_optional_reflection_model_absent() -> None:
    """Verify RunRequest optional model fields default to None."""
    req = RunRequest.model_validate(_base_payload())

    assert req.reflection_model_settings is None
    assert req.task_model_settings is None


def test_run_request_optional_reflection_model_present() -> None:
    """Verify RunRequest stores reflection_model_settings when provided via alias."""
    payload = _base_payload(reflection_model_config={"name": "ref-model"})
    req = RunRequest.model_validate(payload)

    assert req.reflection_model_settings is not None
    assert req.reflection_model_settings.name == "ref-model"


def test_run_request_module_kwargs_default_empty() -> None:
    """Verify RunRequest defaults module_kwargs to an empty dict."""
    req = RunRequest.model_validate(_base_payload())

    assert req.module_kwargs == {}



def _grid_base(**overrides) -> dict:
    """Return a minimal valid GridSearchRequest payload dict with optional overrides."""
    base = _base_payload()
    base.pop("model_config")
    base["generation_models"] = [{"name": "g"}]
    base["reflection_models"] = [{"name": "r"}]
    base.update(overrides)
    return base


def test_grid_search_accepts_both_model_lists() -> None:
    """Verify GridSearchRequest accepts valid generation and reflection model lists."""
    req = GridSearchRequest.model_validate(_grid_base())

    assert len(req.generation_models) == 1
    assert len(req.reflection_models) == 1


def test_grid_search_rejects_empty_generation_models() -> None:
    """Verify GridSearchRequest rejects an empty generation_models list."""
    with pytest.raises(ValidationError, match="generation model"):
        GridSearchRequest.model_validate(_grid_base(generation_models=[]))


def test_grid_search_rejects_empty_reflection_models() -> None:
    """Verify GridSearchRequest rejects an empty reflection_models list."""
    with pytest.raises(ValidationError, match="reflection model"):
        GridSearchRequest.model_validate(_grid_base(reflection_models=[]))


def test_grid_search_multiple_pairs_accepted() -> None:
    """Verify GridSearchRequest accepts multiple generation and reflection models."""
    req = GridSearchRequest.model_validate(
        _grid_base(
            generation_models=[{"name": "g1"}, {"name": "g2"}],
            reflection_models=[{"name": "r1"}, {"name": "r2"}],
        )
    )

    assert len(req.generation_models) == 2
    assert len(req.reflection_models) == 2


def test_grid_search_rejects_empty_dataset() -> None:
    """Verify GridSearchRequest rejects a payload with an empty dataset."""
    with pytest.raises(ValidationError, match="at least one row"):
        GridSearchRequest.model_validate(_grid_base(dataset=[]))



def test_optimization_submission_response_defaults() -> None:
    """Verify OptimizationSubmissionResponse defaults name and description to None."""
    resp = OptimizationSubmissionResponse(
        optimization_id="abc123",
        optimization_type="run",
        status=OptimizationStatus.pending,
        created_at=datetime.now(tz=timezone.utc),
        username="alice",
        module_name="predict",
        optimizer_name="gepa",
    )

    assert resp.name is None
    assert resp.description is None
