from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.models.artifacts import OptimizedDemo, OptimizedPredictor, ProgramArtifact



def test_optimized_demo_defaults_empty_dicts() -> None:
    """Verify OptimizedDemo initializes inputs and outputs to empty dicts."""
    d = OptimizedDemo()

    assert d.inputs == {}
    assert d.outputs == {}


def test_optimized_demo_stores_values() -> None:
    """Verify OptimizedDemo stores provided input/output values."""
    d = OptimizedDemo(inputs={"q": "What is 2+2?"}, outputs={"a": "4"})

    assert d.inputs == {"q": "What is 2+2?"}
    assert d.outputs == {"a": "4"}



def test_optimized_predictor_required_fields() -> None:
    """Verify OptimizedPredictor accepts the minimal required fields."""
    p = OptimizedPredictor(predictor_name="pred0", instructions="Do X.")

    assert p.predictor_name == "pred0"
    assert p.instructions == "Do X."


def test_optimized_predictor_defaults() -> None:
    """Verify OptimizedPredictor optional fields default to None/empty."""
    p = OptimizedPredictor(predictor_name="pred0", instructions="Do X.")

    assert p.signature_name is None
    assert p.input_fields == []
    assert p.output_fields == []
    assert p.demos == []
    assert p.formatted_prompt == ""


def test_optimized_predictor_accepts_demos() -> None:
    """Verify OptimizedPredictor stores a list of OptimizedDemo objects."""
    p = OptimizedPredictor(
        predictor_name="pred0",
        instructions="Do X.",
        demos=[OptimizedDemo(inputs={"q": "hi"}, outputs={"a": "bye"})],
    )

    assert len(p.demos) == 1
    assert p.demos[0].inputs == {"q": "hi"}


def test_optimized_predictor_with_full_fields() -> None:
    """Verify OptimizedPredictor stores all optional fields when provided."""
    p = OptimizedPredictor(
        predictor_name="pred0",
        instructions="Do X.",
        signature_name="MySignature",
        input_fields=["question"],
        output_fields=["answer"],
        formatted_prompt="question: ...\nanswer: ...",
    )

    assert p.signature_name == "MySignature"
    assert p.input_fields == ["question"]
    assert p.output_fields == ["answer"]
    assert "question" in p.formatted_prompt



def test_program_artifact_all_defaults_none() -> None:
    """Verify ProgramArtifact defaults all optional fields to None."""
    art = ProgramArtifact()

    assert art.path is None
    assert art.program_pickle_base64 is None
    assert art.metadata is None
    assert art.optimized_prompt is None


def test_program_artifact_with_nested_predictor() -> None:
    """Verify ProgramArtifact stores a nested OptimizedPredictor with demos."""
    art = ProgramArtifact(
        optimized_prompt=OptimizedPredictor(
            predictor_name="pred0",
            instructions="Do X.",
            demos=[OptimizedDemo(inputs={"q": "a"}, outputs={"a": "b"})],
        )
    )

    assert art.optimized_prompt is not None
    assert len(art.optimized_prompt.demos) == 1


def test_program_artifact_with_metadata() -> None:
    """Verify ProgramArtifact stores path and metadata dict."""
    art = ProgramArtifact(
        path="/opt/artifacts/job123",
        metadata={"score": 0.95, "num_demos": 3},
    )

    assert art.path == "/opt/artifacts/job123"
    assert art.metadata["score"] == pytest.approx(0.95)


def test_program_artifact_with_pickle() -> None:
    """Verify ProgramArtifact stores a base64-encoded pickle string."""
    art = ProgramArtifact(program_pickle_base64="abc123==")

    assert art.program_pickle_base64 == "abc123=="
