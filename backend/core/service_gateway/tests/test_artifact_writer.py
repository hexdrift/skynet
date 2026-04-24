from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.exceptions import ServiceError
from core.models import OptimizedDemo, OptimizedPredictor, ProgramArtifact
from core.service_gateway.artifacts import (
    _format_prompt_string,
    extract_optimized_prompt,
    persist_program,
)



def test_format_prompt_string_instructions_only() -> None:
    """Instructions-only call returns just the instruction text."""
    result = _format_prompt_string("Do the thing.", [], [], [], None)

    assert result == "Do the thing."


def test_format_prompt_string_includes_input_and_output_field_labels() -> None:
    """Field names are prefixed with [Input] / [Output] labels."""
    result = _format_prompt_string("Instr", ["question"], ["answer"], [], _mock_sig())

    assert "[Input] question" in result
    assert "[Output] answer" in result


def test_format_prompt_string_demo_block_present() -> None:
    """A demo list produces an Examples section with demo content."""
    demo = OptimizedDemo(inputs={"q": "What?"}, outputs={"a": "42"})

    result = _format_prompt_string("Instr", ["q"], ["a"], [demo], _mock_sig())

    assert "Examples:" in result
    assert "What?" in result
    assert "42" in result


def test_format_prompt_string_empty_everything_returns_empty_string() -> None:
    """All-empty inputs produce an empty string, not whitespace."""
    result = _format_prompt_string("", [], [], [], None)

    assert result == ""


def test_format_prompt_string_multiple_demos_numbered() -> None:
    """Multiple demos are numbered sequentially (Example 1, Example 2, …)."""
    demo1 = OptimizedDemo(inputs={"q": "q1"}, outputs={"a": "a1"})
    demo2 = OptimizedDemo(inputs={"q": "q2"}, outputs={"a": "a2"})

    result = _format_prompt_string("X", ["q"], ["a"], [demo1, demo2], _mock_sig())

    assert "Example 1:" in result
    assert "Example 2:" in result



def test_extract_optimized_prompt_no_predictors_returns_none() -> None:
    """Program with no named predictors returns None."""
    program = MagicMock()
    program.named_predictors.return_value = []

    result = extract_optimized_prompt(program)

    assert result is None


def test_extract_optimized_prompt_named_predictors_raises_returns_none() -> None:
    """Exception from named_predictors() is swallowed and None is returned."""
    program = MagicMock()
    program.named_predictors.side_effect = RuntimeError("boom")

    result = extract_optimized_prompt(program)

    assert result is None


def test_extract_optimized_prompt_no_signature_returns_none() -> None:
    """Predictor without a signature attribute returns None."""
    predictor = MagicMock(spec=[])          # no .signature attribute
    program = MagicMock()
    program.named_predictors.return_value = [("predict", predictor)]

    result = extract_optimized_prompt(program)

    assert result is None


def test_extract_optimized_prompt_happy_path_returns_optimized_predictor() -> None:
    """Happy path returns an OptimizedPredictor with the correct predictor name."""
    sig = _mock_sig()
    predictor = MagicMock()
    predictor.signature = sig
    predictor.demos = []
    program = MagicMock()
    program.named_predictors.return_value = [("predict", predictor)]

    result = extract_optimized_prompt(program)

    assert isinstance(result, OptimizedPredictor)
    assert result.predictor_name == "predict"


def test_extract_optimized_prompt_demos_extracted() -> None:
    """Demo inputs and outputs are correctly extracted into OptimizedDemo objects."""
    sig = _mock_sig(input_fields=["q"], output_fields=["a"])
    demo = MagicMock()
    demo.q = "What?"
    demo.a = "42"
    predictor = MagicMock()
    predictor.signature = sig
    predictor.demos = [demo]
    program = MagicMock()
    program.named_predictors.return_value = [("predict", predictor)]

    result = extract_optimized_prompt(program)

    assert len(result.demos) == 1
    assert result.demos[0].inputs == {"q": "What?"}
    assert result.demos[0].outputs == {"a": "42"}



def test_persist_program_save_failure_raises_service_error() -> None:
    """program.save() raising RuntimeError becomes a ServiceError."""
    program = MagicMock()
    program.save.side_effect = RuntimeError("disk full")

    with pytest.raises(ServiceError, match="Failed to save program artifact"):
        persist_program(program, artifact_id="test-id")


def test_persist_program_missing_files_raises_service_error(tmp_path) -> None:
    """save() creates the temp dir but writes no files."""
    program = MagicMock()
    program.save.return_value = None  # creates nothing

    with pytest.raises(ServiceError, match="Failed to load program artifact"):
        persist_program(program, artifact_id="test-id")


def test_persist_program_base64_encodes_correctly(tmp_path) -> None:
    """program.pkl bytes are base64-encoded in the returned ProgramArtifact."""
    raw_bytes = b"fake-pickle-bytes"
    expected_b64 = base64.b64encode(raw_bytes).decode("ascii")

    program = _fake_save_program(raw_bytes)

    result = persist_program(program, artifact_id=None)

    assert result is not None
    assert result.program_pickle_base64 == expected_b64


def test_persist_program_no_temp_files_left_on_disk() -> None:
    """Temp artifact directory is cleaned up after a successful persist."""
    raw_bytes = b"bytes"
    program = _fake_save_program(raw_bytes)
    tmp_dirs_before = set(os.listdir(tempfile.gettempdir()))

    persist_program(program, artifact_id="cleanup-test")

    tmp_dirs_after = set(os.listdir(tempfile.gettempdir()))
    dspy_dirs = [d for d in tmp_dirs_after - tmp_dirs_before if d.startswith("dspy_artifact_")]
    assert dspy_dirs == [], f"Temp dirs not cleaned up: {dspy_dirs}"


def test_persist_program_returns_program_artifact_model() -> None:
    """Return value is a ProgramArtifact instance with path=None."""
    program = _fake_save_program(b"data")

    result = persist_program(program, artifact_id="abc")

    assert isinstance(result, ProgramArtifact)
    assert result.path is None



def test_persist_program_raises_service_error_when_save_fails() -> None:
    """OSError during save is wrapped in a ServiceError."""
    program = MagicMock()
    program.save.side_effect = OSError("no space left on device")

    with pytest.raises(ServiceError, match="Failed to save program artifact"):
        persist_program(program, artifact_id="save-fail")


def test_persist_program_raises_service_error_when_metadata_read_fails() -> None:
    """save() succeeds (files written) but metadata.json read raises."""
    def _save_no_metadata(path: str, save_program: bool = True) -> None:
        dest = Path(path)
        # Deliberately omit metadata.json so read_text() raises FileNotFoundError
        (dest / "program.pkl").write_bytes(b"pkl-bytes")

    program = MagicMock()
    program.save.side_effect = _save_no_metadata
    program.named_predictors.return_value = []

    with pytest.raises(ServiceError, match="Failed to load program artifact"):
        persist_program(program, artifact_id="meta-fail")


def test_persist_program_raises_service_error_when_pkl_read_fails() -> None:
    """save() succeeds, metadata.json is present, but program.pkl is absent."""
    def _save_no_pkl(path: str, save_program: bool = True) -> None:
        dest = Path(path)
        (dest / "metadata.json").write_text(json.dumps({"dspy_version": "0"}))
        # Deliberately omit program.pkl

    program = MagicMock()
    program.save.side_effect = _save_no_pkl
    program.named_predictors.return_value = []

    with pytest.raises(ServiceError, match="Failed to load program artifact"):
        persist_program(program, artifact_id="pkl-fail")


def test_persist_program_cleans_up_tempdir_on_error() -> None:
    """Temp dir is removed via shutil.rmtree even when ServiceError is raised."""
    known_path = tempfile.mkdtemp(prefix="dspy_sentinel_")
    try:
        program = MagicMock()
        program.save.side_effect = RuntimeError("boom")

        with patch("core.service_gateway.artifacts.tempfile.mkdtemp", return_value=known_path), \
             patch("core.service_gateway.artifacts.shutil.rmtree") as mock_rmtree:
            with pytest.raises(ServiceError):
                persist_program(program, artifact_id="cleanup-err")

            mock_rmtree.assert_called_once_with(known_path, ignore_errors=True)
    finally:
        if os.path.exists(known_path):
            shutil.rmtree(known_path, ignore_errors=True)


def test_persist_program_cleans_up_tempdir_on_success() -> None:
    """Temp dir is removed via shutil.rmtree on the happy path too."""
    known_path = tempfile.mkdtemp(prefix="dspy_sentinel_success_")
    try:
        raw_bytes = b"success-bytes"

        def _save_files(path: str, save_program: bool = True) -> None:
            dest = Path(path)
            (dest / "metadata.json").write_text(json.dumps({"dspy_version": "0"}))
            (dest / "program.pkl").write_bytes(raw_bytes)

        program = MagicMock()
        program.save.side_effect = _save_files
        program.named_predictors.return_value = []

        with patch("core.service_gateway.artifacts.tempfile.mkdtemp", return_value=known_path), \
             patch("core.service_gateway.artifacts.shutil.rmtree") as mock_rmtree:
            result = persist_program(program, artifact_id="cleanup-ok")

            assert result is not None
            mock_rmtree.assert_called_once_with(known_path, ignore_errors=True)
    finally:
        if os.path.exists(known_path):
            shutil.rmtree(known_path, ignore_errors=True)



def _mock_sig(
    *,
    input_fields: list[str] | None = None,
    output_fields: list[str] | None = None,
    instructions: str = "test instructions",
) -> MagicMock:
    """Return a MagicMock DSPy signature with configurable fields and instructions."""
    sig = MagicMock()
    sig.instructions = instructions
    sig.__class__.__name__ = "MockSignature"
    sig.input_fields = {k: MagicMock(json_schema_extra={}) for k in (input_fields or ["question"])}
    sig.output_fields = {k: MagicMock(json_schema_extra={}) for k in (output_fields or ["answer"])}
    return sig


def _fake_save_program(raw_bytes: bytes) -> MagicMock:
    """Return a program mock whose .save() writes the expected artifact files."""
    def _save(path: str, save_program: bool = True) -> None:
        dest = Path(path)
        (dest / "metadata.json").write_text(json.dumps({"dspy_version": "0"}))
        (dest / "program.pkl").write_bytes(raw_bytes)

    program = MagicMock()
    program.save.side_effect = _save
    program.named_predictors.return_value = []
    return program
