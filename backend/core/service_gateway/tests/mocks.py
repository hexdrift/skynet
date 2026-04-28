"""Centralised mock builders for core/service_gateway tests.

All numeric constants are loaded from real fixtures captured from a live
backend run — see tests/fixtures/ for the source files.

Usage
-----
    from core.service_gateway.tests.mocks import (
        fake_language_model,
        fake_language_model_no_history,
        fake_compiled_program,
        fake_original_program,
        fake_optimizer,
        fake_capture_tqdm,
        patch_core_dependencies,
        REAL_NUM_LM_CALLS,
        REAL_BASELINE_METRIC,
        REAL_OPTIMIZED_METRIC,
        REAL_OPTIMIZER_NAME,
        REAL_MODULE_NAME,
        REAL_AVG_RESPONSE_TIME_MS,
    )
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from tests.fixtures import load_fixture

_gepa = load_fixture("jobs/success_single_gepa.detail.json")

REAL_NUM_LM_CALLS: int = _gepa["result"]["num_lm_calls"]  # 1257
REAL_AVG_RESPONSE_TIME_MS: float = _gepa["result"]["avg_response_time_ms"]  # 58686.1
REAL_BASELINE_METRIC: float = _gepa["result"]["baseline_test_metric"]  # 52.89
REAL_OPTIMIZED_METRIC: float = _gepa["result"]["optimized_test_metric"]  # 75.9
REAL_MODULE_NAME: str = _gepa["module_name"]  # "cot"
REAL_OPTIMIZER_NAME: str = _gepa["optimizer_name"]  # "gepa"


def fake_language_model(history_len: int | None = None) -> MagicMock:
    """Return a ``MagicMock`` LM with a populated ``history`` list.

    Args:
        history_len: Number of fake history entries. Defaults to
            ``REAL_NUM_LM_CALLS`` so ``avg_response_time_ms`` uses
            production-scale data; tests targeting an exact count should pass
            ``history_len`` explicitly.

    Returns:
        A ``MagicMock`` whose ``history`` attribute is a list of
        ``history_len`` mock entries.
    """
    n = history_len if history_len is not None else REAL_NUM_LM_CALLS
    lm = MagicMock()
    lm.history = [MagicMock() for _ in range(n)]
    return lm


def fake_language_model_no_history() -> MagicMock:
    """Return a ``MagicMock`` that forbids any attribute access.

    ``spec=[]`` simulates a non-DSPy LM with no ``history`` attribute, used
    to verify the gateway's defensive handling of foreign LM objects.
    """
    return MagicMock(spec=[])


def fake_compiled_program(name: str = "compiled") -> MagicMock:
    """Return a ``MagicMock`` standing in for a compiled DSPy program."""
    return MagicMock(name=name)


def fake_original_program(name: str = "original_program") -> MagicMock:
    """Return a ``MagicMock`` standing in for the pre-compile baseline program."""
    return MagicMock(name=name)


def fake_optimizer() -> MagicMock:
    """Return a bare ``MagicMock`` standing in for a DSPy optimizer."""
    return MagicMock()


def fake_capture_tqdm() -> MagicMock:
    """Return a ``MagicMock`` shaped like the ``capture_tqdm`` context manager.

    The ``__enter__``/``__exit__`` slots are pre-wired so the mock can be
    used as a ``with`` target without per-test setup.
    """
    ctx = MagicMock()
    ctx.return_value.__enter__ = MagicMock(return_value=None)
    ctx.return_value.__exit__ = MagicMock(return_value=False)
    return ctx


@contextmanager
def patch_core_dependencies(
    *,
    fake_lm: MagicMock | None = None,
    compiled_program: MagicMock | None = None,
):
    """Patch the five external collaborators of ``core.service_gateway.optimization.core``.

    Args:
        fake_lm: Optional pre-built mock LM; defaults to ``fake_language_model()``.
        compiled_program: Optional pre-built mock program; defaults to
            ``fake_compiled_program()``.

    Yields:
        A namespace object exposing each patched mock as a class attribute
        (``build_language_model_mock``, ``compile_program_mock``, ...).
    """
    lm = fake_lm if fake_lm is not None else fake_language_model()
    program = compiled_program if compiled_program is not None else fake_compiled_program()
    tqdm_ctx = fake_capture_tqdm()

    with (
        patch("core.service_gateway.optimization.core.build_language_model", return_value=lm) as p_lm,
        patch("core.service_gateway.optimization.core.compile_program", return_value=program) as p_compile,
        patch("core.service_gateway.optimization.core.persist_program", return_value=None) as p_persist,
        patch("core.service_gateway.optimization.core.instantiate_optimizer", return_value=MagicMock()) as p_opt,
        patch("core.service_gateway.optimization.core.capture_tqdm", tqdm_ctx) as p_tqdm,
    ):

        class _Mocks:
            build_language_model_mock = p_lm
            compile_program_mock = p_compile
            persist_program_mock = p_persist
            instantiate_optimizer_mock = p_opt
            capture_tqdm_mock = p_tqdm

        yield _Mocks
