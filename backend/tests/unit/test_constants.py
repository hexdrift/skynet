"""B-L2: Assert critical constants have the expected value and type.

Focus is on constants that drive protocol-level contracts:
progress event keys, tqdm keys, optimization type strings, and
payload overview keys used as dict keys in the API layer.
Catches accidental type flips (str → int) or rename regressions.
"""

from __future__ import annotations

from core import constants as C  # noqa: N812 — short alias for assertion-heavy module


class TestProgressEventKeys:
    """Pin the worker → parent progress-event keys to their expected wire values."""

    # These exact strings cross the subprocess→parent boundary; renaming silently breaks the worker.

    def test_progress_splits_ready_value_and_type(self) -> None:
        """``PROGRESS_SPLITS_READY`` is the string ``"dataset_splits_ready"``."""
        assert C.PROGRESS_SPLITS_READY == "dataset_splits_ready"
        assert isinstance(C.PROGRESS_SPLITS_READY, str)

    def test_progress_baseline_value_and_type(self) -> None:
        """``PROGRESS_BASELINE`` is the string ``"baseline_evaluated"``."""
        assert C.PROGRESS_BASELINE == "baseline_evaluated"
        assert isinstance(C.PROGRESS_BASELINE, str)

    def test_progress_optimized_value_and_type(self) -> None:
        """``PROGRESS_OPTIMIZED`` is the string ``"optimized_evaluated"``."""
        assert C.PROGRESS_OPTIMIZED == "optimized_evaluated"
        assert isinstance(C.PROGRESS_OPTIMIZED, str)

    def test_progress_optimizer_value_and_type(self) -> None:
        """``PROGRESS_OPTIMIZER`` is the string ``"optimizer_progress"``."""
        assert C.PROGRESS_OPTIMIZER == "optimizer_progress"
        assert isinstance(C.PROGRESS_OPTIMIZER, str)


class TestTqdmKeys:
    """Pin the tqdm wire keys read by the API layer."""

    def test_tqdm_remaining_key_value_and_type(self) -> None:
        """``TQDM_REMAINING_KEY`` is the string ``"tqdm_remaining"``."""
        assert C.TQDM_REMAINING_KEY == "tqdm_remaining"
        assert isinstance(C.TQDM_REMAINING_KEY, str)

    def test_tqdm_total_key_value_and_type(self) -> None:
        """``TQDM_TOTAL_KEY`` is the string ``"tqdm_total"``."""
        assert C.TQDM_TOTAL_KEY == "tqdm_total"
        assert isinstance(C.TQDM_TOTAL_KEY, str)

    def test_tqdm_n_key_value_and_type(self) -> None:
        """``TQDM_N_KEY`` is the string ``"tqdm_n"``."""
        assert C.TQDM_N_KEY == "tqdm_n"
        assert isinstance(C.TQDM_N_KEY, str)


class TestOptimizationTypeStrings:
    """Pin the optimization-type discriminator strings used in the JSON wire format."""

    def test_optimization_type_run_value_and_type(self) -> None:
        """``OPTIMIZATION_TYPE_RUN`` is the literal ``"run"``."""
        assert C.OPTIMIZATION_TYPE_RUN == "run"
        assert isinstance(C.OPTIMIZATION_TYPE_RUN, str)

    def test_optimization_type_grid_search_value_and_type(self) -> None:
        """``OPTIMIZATION_TYPE_GRID_SEARCH`` is the literal ``"grid_search"``."""
        assert C.OPTIMIZATION_TYPE_GRID_SEARCH == "grid_search"
        assert isinstance(C.OPTIMIZATION_TYPE_GRID_SEARCH, str)


class TestPayloadOverviewKeys:
    """Pin payload overview keys used as dict keys throughout the API layer."""

    def test_payload_overview_job_type_is_str(self) -> None:
        """``PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE`` is ``"optimization_type"``."""
        assert isinstance(C.PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, str)
        assert C.PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE == "optimization_type"

    def test_payload_overview_username_is_str(self) -> None:
        """``PAYLOAD_OVERVIEW_USERNAME`` is ``"username"``."""
        assert isinstance(C.PAYLOAD_OVERVIEW_USERNAME, str)
        assert C.PAYLOAD_OVERVIEW_USERNAME == "username"

    def test_payload_overview_total_pairs_is_str(self) -> None:
        """``PAYLOAD_OVERVIEW_TOTAL_PAIRS`` is ``"total_pairs"``."""
        assert isinstance(C.PAYLOAD_OVERVIEW_TOTAL_PAIRS, str)
        assert C.PAYLOAD_OVERVIEW_TOTAL_PAIRS == "total_pairs"
