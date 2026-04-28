"""Tests for ``core.service_gateway.optimization.artifacts``.

Covers prompt-string formatting, optimized-predictor extraction, and the
``persist_program`` save/cleanup contract.
"""

from __future__ import annotations

import base64
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.exceptions import ServiceError
from core.models import OptimizedDemo, OptimizedPredictor, ProgramArtifact
from core.service_gateway.optimization.artifacts import (
    _format_prompt_string,
    extract_optimized_prompt,
    persist_program,
)


def test_format_prompt_string_instructions_only() -> None:
    """Instructions alone round-trip unchanged when no fields or demos exist."""
    result = _format_prompt_string("Do the thing.", [], [], [], None)

    assert result == "Do the thing."


def test_format_prompt_string_includes_input_and_output_field_labels() -> None:
    """Field labels are rendered as ``[Input]``/``[Output]`` markers."""
    result = _format_prompt_string("Instr", ["question"], ["answer"], [], _mock_sig())

    assert "[Input] question" in result
    assert "[Output] answer" in result


def test_format_prompt_string_demo_block_present() -> None:
    """A single demo's inputs and outputs appear under an ``Examples:`` header."""
    demo = OptimizedDemo(inputs={"q": "What?"}, outputs={"a": "42"})

    result = _format_prompt_string("Instr", ["q"], ["a"], [demo], _mock_sig())

    assert "Examples:" in result
    assert "What?" in result
    assert "42" in result


def test_format_prompt_string_empty_everything_returns_empty_string() -> None:
    """All-empty inputs collapse to an empty string."""
    result = _format_prompt_string("", [], [], [], None)

    assert result == ""


def test_format_prompt_string_multiple_demos_numbered() -> None:
    """Multiple demos are numbered ``Example 1:``, ``Example 2:``..."""
    demo1 = OptimizedDemo(inputs={"q": "q1"}, outputs={"a": "a1"})
    demo2 = OptimizedDemo(inputs={"q": "q2"}, outputs={"a": "a2"})

    result = _format_prompt_string("X", ["q"], ["a"], [demo1, demo2], _mock_sig())

    assert "Example 1:" in result
    assert "Example 2:" in result


def test_extract_optimized_prompt_no_predictors_returns_none() -> None:
    """A program with zero predictors yields ``None``."""
    program = MagicMock()
    program.named_predictors.return_value = []

    result = extract_optimized_prompt(program)

    assert result is None


def test_extract_optimized_prompt_named_predictors_raises_returns_none() -> None:
    """An exception from ``named_predictors()`` must NOT propagate — extraction is best-effort."""
    program = MagicMock()
    program.named_predictors.side_effect = RuntimeError("boom")

    result = extract_optimized_prompt(program)

    assert result is None


def test_extract_optimized_prompt_no_signature_returns_none() -> None:
    """A predictor lacking a ``signature`` attribute yields ``None``."""
    predictor = MagicMock(spec=[])  # no .signature attribute
    program = MagicMock()
    program.named_predictors.return_value = [("predict", predictor)]

    result = extract_optimized_prompt(program)

    assert result is None


def test_extract_optimized_prompt_happy_path_returns_optimized_predictor() -> None:
    """A well-formed predictor returns an ``OptimizedPredictor`` carrying its name."""
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
    """Demo input/output cells are projected into the returned ``OptimizedPredictor``."""
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

    assert result is not None
    assert len(result.demos) == 1
    assert result.demos[0].inputs == {"q": "What?"}
    assert result.demos[0].outputs == {"a": "42"}


def test_persist_program_save_failure_raises_service_error() -> None:
    """A ``save`` failure surfaces as ``ServiceError`` with the save-failure prefix."""
    program = MagicMock()
    program.save.side_effect = RuntimeError("disk full")

    with pytest.raises(ServiceError, match="Failed to save program artifact"):
        persist_program(program, artifact_id="test-id")


def test_persist_program_missing_files_raises_service_error(tmp_path) -> None:
    """Missing artifact files raise the load-failure ``ServiceError``."""
    program = MagicMock()
    program.save.return_value = None  # creates nothing

    with pytest.raises(ServiceError, match="Failed to load program artifact"):
        persist_program(program, artifact_id="test-id")


def test_persist_program_base64_encodes_correctly(tmp_path) -> None:
    """Pickle bytes are base64-encoded into ``program_pickle_base64``."""
    raw_bytes = b"fake-pickle-bytes"
    expected_b64 = base64.b64encode(raw_bytes).decode("ascii")

    program = _fake_save_program(raw_bytes)

    result = persist_program(program, artifact_id=None)

    assert result is not None
    assert result.program_pickle_base64 == expected_b64


def test_persist_program_no_temp_files_left_on_disk() -> None:
    """No ``dspy_artifact_*`` temp directories survive a successful persist call."""
    raw_bytes = b"bytes"
    program = _fake_save_program(raw_bytes)
    tmp_root = Path(tempfile.gettempdir())
    tmp_dirs_before = {p.name for p in tmp_root.iterdir()}

    persist_program(program, artifact_id="cleanup-test")

    tmp_dirs_after = {p.name for p in tmp_root.iterdir()}
    dspy_dirs = [d for d in tmp_dirs_after - tmp_dirs_before if d.startswith("dspy_artifact_")]
    assert dspy_dirs == [], f"Temp dirs not cleaned up: {dspy_dirs}"


def test_persist_program_returns_program_artifact_model() -> None:
    """``persist_program`` returns a ``ProgramArtifact`` with no on-disk path."""
    program = _fake_save_program(b"data")

    result = persist_program(program, artifact_id="abc")

    assert isinstance(result, ProgramArtifact)
    assert result.path is None


def test_persist_program_raises_service_error_when_save_fails() -> None:
    """An ``OSError`` from ``save`` is wrapped as the save-failure ``ServiceError``."""
    program = MagicMock()
    program.save.side_effect = OSError("no space left on device")

    with pytest.raises(ServiceError, match="Failed to save program artifact"):
        persist_program(program, artifact_id="save-fail")


def test_persist_program_raises_service_error_when_metadata_read_fails() -> None:
    """A missing ``metadata.json`` produces the load-failure ``ServiceError``."""
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
    """A missing ``program.pkl`` produces the load-failure ``ServiceError``."""
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
    """The temp dir is removed even when ``ServiceError`` propagates."""
    known_path = tempfile.mkdtemp(prefix="dspy_sentinel_")
    try:
        program = MagicMock()
        program.save.side_effect = RuntimeError("boom")

        with (
            patch("core.service_gateway.optimization.artifacts.tempfile.mkdtemp", return_value=known_path),
            patch("core.service_gateway.optimization.artifacts.shutil.rmtree") as mock_rmtree,
        ):
            with pytest.raises(ServiceError):
                persist_program(program, artifact_id="cleanup-err")

            mock_rmtree.assert_called_once_with(known_path, ignore_errors=True)
    finally:
        if Path(known_path).exists():
            shutil.rmtree(known_path, ignore_errors=True)


def test_persist_program_cleans_up_tempdir_on_success() -> None:
    """Symmetric to the error-cleanup test: cleanup must run on the happy path too."""
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

        with (
            patch("core.service_gateway.optimization.artifacts.tempfile.mkdtemp", return_value=known_path),
            patch("core.service_gateway.optimization.artifacts.shutil.rmtree") as mock_rmtree,
        ):
            result = persist_program(program, artifact_id="cleanup-ok")

            assert result is not None
            mock_rmtree.assert_called_once_with(known_path, ignore_errors=True)
    finally:
        if Path(known_path).exists():
            shutil.rmtree(known_path, ignore_errors=True)


def _mock_sig(
    *,
    input_fields: list[str] | None = None,
    output_fields: list[str] | None = None,
    instructions: str = "test instructions",
) -> MagicMock:
    """Build a ``MagicMock`` shaped like a DSPy ``Signature`` class."""
    sig = MagicMock()
    sig.instructions = instructions
    sig.__class__.__name__ = "MockSignature"
    sig.input_fields = {k: MagicMock(json_schema_extra={}) for k in (input_fields or ["question"])}
    sig.output_fields = {k: MagicMock(json_schema_extra={}) for k in (output_fields or ["answer"])}
    return sig


def _fake_save_program(raw_bytes: bytes) -> MagicMock:
    """Return a fake program whose ``save`` writes ``metadata.json`` and ``program.pkl``."""
    def _save(path: str, save_program: bool = True) -> None:
        dest = Path(path)
        (dest / "metadata.json").write_text(json.dumps({"dspy_version": "0"}))
        (dest / "program.pkl").write_bytes(raw_bytes)

    program = MagicMock()
    program.save.side_effect = _save
    program.named_predictors.return_value = []
    return program
