"""Regression tests for GEPA tqdm progress streaming (regression from #23/#24).

#23/#24 forced ``disable_cache=True`` on the GEPA generation and
reflection LMs across the training/eval region. With caching off, GEPA's
recognized valset ``Evaluate`` / rollouts tqdm bar stops being produced,
so ``_TqdmProxy._emit`` short-circuits and no ``optimizer_progress`` /
``tqdm_percent`` ever reaches the progress callback (and thus
``latest_metrics``). These tests pin the fix: GEPA LMs are built cached,
and a GEPA-shaped bar created under the real ``capture_tqdm`` patch
relays progress to the callback.
"""

from __future__ import annotations

from typing import Any, Literal
from unittest.mock import MagicMock, patch

from core.constants import PROGRESS_OPTIMIZER, TQDM_PERCENT_KEY
from core.models import ColumnMapping, ModelConfig, RunRequest, SplitFractions
from core.registry import ServiceRegistry
from core.service_gateway.optimization import progress as progress_mod
from core.service_gateway.optimization.core import DspyService
from core.service_gateway.tests.mocks import fake_compiled_program, fake_language_model

_VALID_SIG = """\
import dspy
class QA(dspy.Signature):
    question: str = dspy.InputField()
    answer: str = dspy.OutputField()
"""

_VALID_METRIC = "def metric(example, prediction, trace=None): return 1.0"

_DATASET = [{"q": "What is 1+1?", "a": "2"}, {"q": "What is 2+2?", "a": "4"}]

_MAPPING = ColumnMapping(inputs={"question": "q"}, outputs={"answer": "a"})


def _service() -> DspyService:
    """Return a fresh ``DspyService`` backed by a clean registry."""
    return DspyService(registry=ServiceRegistry())


def _gepa_run_request(**overrides: Any) -> RunRequest:
    """Build a GEPA ``RunRequest`` (gen + reflection model, all-train split)."""
    base: dict[str, Any] = {
        "username": "tester",
        "module_name": "cot",
        "signature_code": _VALID_SIG,
        "metric_code": _VALID_METRIC,
        "optimizer_name": "gepa",
        "dataset": _DATASET * 10,
        "column_mapping": _MAPPING,
        "split_fractions": SplitFractions(train=1.0, val=0.0, test=0.0),
        "model_config": ModelConfig(name="openai/gpt-4o-mini"),
        "reflection_model_config": ModelConfig(name="openai/gpt-4o"),
        "shuffle": False,
    }
    base.update(overrides)
    return RunRequest(**base)


class _GepaBar:
    """Stand-in for GEPA's valset ``Evaluate`` / rollouts tqdm bar.

    Shaped so the real ``_TqdmProxy`` classifies it as a GEPA bar
    (``unit='rollouts'``) and computes a non-None ``tqdm_percent``.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Accept and ignore arbitrary tqdm constructor args."""
        self.total = kwargs.get("total", 10)
        self.n = 0
        self.desc = kwargs.get("desc", "GEPA")
        self.unit = "rollouts"
        self.format_dict: dict[str, Any] = {"rate": 1.0, "elapsed": 1.0}

    def update(self, n: int = 1) -> None:
        """Advance the rollout count by ``n``."""
        self.n += n

    def close(self) -> None:
        """No-op close to match the tqdm API."""

    def refresh(self) -> None:
        """No-op refresh to match the tqdm API."""

    def __enter__(self) -> _GepaBar:
        """Return self for ``with`` semantics."""
        return self

    def __exit__(self, *args: Any) -> Literal[False]:
        """Suppress no exceptions."""
        return False


def test_gepa_run_builds_generation_and_reflection_lms_cached() -> None:
    """A GEPA run must not force ``disable_cache=True`` on its gen/reflection LMs.

    Forcing cache off across the GEPA training/eval region is what
    suppressed the recognized tqdm bar; the fix builds both LMs cached.
    """
    service = _service()
    payload = _gepa_run_request()

    with (
        patch(
            "core.service_gateway.optimization.core.build_language_model",
            return_value=fake_language_model(),
        ) as p_lm,
        patch(
            "core.service_gateway.optimization.core.compile_program",
            return_value=fake_compiled_program(),
        ),
        patch("core.service_gateway.optimization.core.persist_program", return_value=None),
        patch(
            "core.service_gateway.optimization.core.instantiate_optimizer",
            return_value=MagicMock(),
        ),
    ):
        service.run(payload)

    # Every build_language_model call in the GEPA path must be cached
    # (no disable_cache=True kwarg).
    assert p_lm.call_count >= 2
    for call in p_lm.call_args_list:
        assert call.kwargs.get("disable_cache", False) is False


def test_gepa_recognized_bar_under_capture_tqdm_emits_progress_to_callback() -> None:
    """A GEPA bar created during compile, under real capture_tqdm, relays progress.

    Simulates GEPA constructing its valset ``Evaluate`` / rollouts bar via
    the patched ``tqdm.tqdm`` factory inside ``compile_program``. With the
    fix, the proxy is not short-circuited and the progress callback (which
    feeds ``latest_metrics``) receives ``optimizer_progress`` events
    carrying a populated ``tqdm_percent``.
    """
    service = _service()
    payload = _gepa_run_request()

    events: list[tuple[str, dict]] = []

    def _cb(event: str, metrics: dict) -> None:
        events.append((event, metrics))

    def _compile_side_effect(**kwargs: Any) -> Any:
        # GEPA constructs and drives its valset bar during compile; the
        # active capture_tqdm patch wraps it in the real _TqdmProxy.
        bar = progress_mod.tqdm.tqdm(total=10, desc="GEPA", unit="rollouts")
        bar.update(5)
        bar.close()
        return fake_compiled_program()

    with (
        patch(
            "core.service_gateway.optimization.core.build_language_model",
            return_value=fake_language_model(),
        ),
        patch(
            "core.service_gateway.optimization.core.compile_program",
            side_effect=_compile_side_effect,
        ),
        patch("core.service_gateway.optimization.core.persist_program", return_value=None),
        patch(
            "core.service_gateway.optimization.core.instantiate_optimizer",
            return_value=MagicMock(),
        ),
        patch.object(progress_mod.tqdm, "tqdm", side_effect=_GepaBar),
    ):
        service.run(payload, progress_callback=_cb)

    optimizer_events = [m for ev, m in events if ev == PROGRESS_OPTIMIZER]
    assert optimizer_events, "no optimizer_progress events reached the callback"
    assert any(
        m.get(TQDM_PERCENT_KEY) is not None for m in optimizer_events
    ), "optimizer_progress events carried no tqdm_percent"
