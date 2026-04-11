"""Validation tests for the Pydantic model split.

These guard the invariants enforced by the old `backend/core/models.py`
that are now spread across `backend/core/models/*.py`.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from core.models import (
    ColumnMapping,
    GridSearchRequest,
    ModelConfig,
    OptimizationStatus,
    OptimizedDemo,
    OptimizedPredictor,
    ProgramArtifact,
    RunRequest,
    SplitFractions,
    TemplateCreateRequest,
    ValidateCodeRequest,
    ValidateCodeResponse,
)



def test_column_mapping_requires_inputs() -> None:
    with pytest.raises(ValidationError, match="At least one input"):
        ColumnMapping(inputs={}, outputs={"answer": "answer"})


def test_column_mapping_rejects_shared_columns() -> None:
    with pytest.raises(ValidationError, match="must not reuse the same columns"):
        ColumnMapping(inputs={"q": "col"}, outputs={"a": "col"})


def test_column_mapping_accepts_disjoint_columns() -> None:
    m = ColumnMapping(inputs={"q": "question"}, outputs={"a": "answer"})
    assert m.inputs == {"q": "question"}
    assert m.outputs == {"a": "answer"}



def test_split_fractions_default_sums_to_one() -> None:
    s = SplitFractions()
    assert abs(s.train + s.val + s.test - 1.0) < 1e-6


def test_split_fractions_rejects_negative() -> None:
    with pytest.raises(ValidationError, match="non-negative"):
        SplitFractions(train=-0.1, val=0.55, test=0.55)


def test_split_fractions_rejects_wrong_total() -> None:
    with pytest.raises(ValidationError, match="sum to 1.0"):
        SplitFractions(train=0.5, val=0.25, test=0.25 + 0.01)



def test_model_config_normalized_identifier_strips_slashes() -> None:
    assert ModelConfig(name="/gpt-4o-mini/").normalized_identifier() == "gpt-4o-mini"


def test_model_config_temperature_bounds() -> None:
    with pytest.raises(ValidationError):
        ModelConfig(name="x", temperature=2.5)
    with pytest.raises(ValidationError):
        ModelConfig(name="x", temperature=-0.1)



def _base_run_payload(**overrides) -> dict:
    base = dict(
        username="alice",
        module_name="predict",
        signature_code="class S: pass",
        metric_code="def m(e, p): return 1.0",
        optimizer_name="miprov2",
        dataset=[{"q": "1+1", "a": "2"}],
        column_mapping={"inputs": {"q": "q"}, "outputs": {"a": "a"}},
        model_config={"name": "gpt-4o-mini"},
    )
    base.update(overrides)
    return base


def test_run_request_accepts_minimal_payload() -> None:
    req = RunRequest.model_validate(_base_run_payload())
    assert req.model_settings.name == "gpt-4o-mini"
    assert req.dataset == [{"q": "1+1", "a": "2"}]


def test_run_request_rejects_empty_dataset() -> None:
    with pytest.raises(ValidationError, match="at least one row"):
        RunRequest.model_validate(_base_run_payload(dataset=[]))


def test_run_request_description_max_length() -> None:
    with pytest.raises(ValidationError):
        RunRequest.model_validate(_base_run_payload(description="x" * 281))
    req = RunRequest.model_validate(_base_run_payload(description="x" * 280))
    assert req.description is not None
    assert len(req.description) == 280



def test_grid_search_requires_both_model_lists() -> None:
    base = _base_run_payload()
    base.pop("model_config")
    with pytest.raises(ValidationError, match="generation model"):
        GridSearchRequest.model_validate(
            dict(base, generation_models=[], reflection_models=[{"name": "r"}])
        )
    with pytest.raises(ValidationError, match="reflection model"):
        GridSearchRequest.model_validate(
            dict(base, generation_models=[{"name": "g"}], reflection_models=[])
        )


def test_grid_search_accepts_both_lists() -> None:
    base = _base_run_payload()
    base.pop("model_config")
    req = GridSearchRequest.model_validate(
        dict(base, generation_models=[{"name": "g"}], reflection_models=[{"name": "r"}])
    )
    assert len(req.generation_models) == 1
    assert len(req.reflection_models) == 1



def test_validate_code_request_accepts_single_block() -> None:
    req = ValidateCodeRequest.model_validate(
        {
            "signature_code": "class S: pass",
            "column_mapping": {"inputs": {"q": "q"}, "outputs": {"a": "a"}},
        }
    )
    assert req.signature_code == "class S: pass"
    assert req.metric_code is None


def test_validate_code_response_default_shape() -> None:
    r = ValidateCodeResponse(valid=True)
    assert r.errors == []
    assert r.warnings == []
    assert r.signature_fields is None



def test_optimized_predictor_defaults() -> None:
    p = OptimizedPredictor(predictor_name="pred0", instructions="Do X.")
    assert p.input_fields == []
    assert p.output_fields == []
    assert p.demos == []
    assert p.formatted_prompt == ""


def test_program_artifact_nested_predictor() -> None:
    art = ProgramArtifact(
        optimized_prompt=OptimizedPredictor(
            predictor_name="pred0",
            instructions="Do X.",
            demos=[OptimizedDemo(inputs={"q": "a"}, outputs={"a": "b"})],
        )
    )
    assert art.optimized_prompt is not None
    assert len(art.optimized_prompt.demos) == 1



def test_template_create_rejects_oversized_config() -> None:
    huge = {"x": "y" * 150_000}
    with pytest.raises(ValidationError, match="maximum size"):
        TemplateCreateRequest(name="t", username="u", config=huge)


def test_template_create_name_length() -> None:
    with pytest.raises(ValidationError):
        TemplateCreateRequest(name="", username="u", config={})
    with pytest.raises(ValidationError):
        TemplateCreateRequest(name="x" * 201, username="u", config={})
    ok = TemplateCreateRequest(name="valid", username="u", config={"k": "v"})
    assert ok.name == "valid"



def test_optimization_status_values() -> None:
    assert OptimizationStatus.success.value == "success"
    assert OptimizationStatus.pending.value == "pending"
    assert {s.value for s in OptimizationStatus} == {
        "pending", "validating", "running", "success", "failed", "cancelled",
    }
