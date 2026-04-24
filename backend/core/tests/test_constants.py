"""B-L2: Assert critical constants have the expected value and type.

Focus is on constants that drive protocol-level contracts:
progress event keys, tqdm keys, optimization type strings, and
payload overview keys used as dict keys in the API layer.
Catches accidental type flips (str → int) or rename regressions.
"""
from __future__ import annotations

import core.constants as C


class TestProgressEventKeys:
    """Progress event key constants must be the exact strings the worker emits."""

    def test_progress_splits_ready_value_and_type(self) -> None:
        """Verify PROGRESS_SPLITS_READY equals 'dataset_splits_ready'."""
        assert C.PROGRESS_SPLITS_READY == "dataset_splits_ready"
        assert isinstance(C.PROGRESS_SPLITS_READY, str)

    def test_progress_baseline_value_and_type(self) -> None:
        """Verify PROGRESS_BASELINE equals 'baseline_evaluated'."""
        assert C.PROGRESS_BASELINE == "baseline_evaluated"
        assert isinstance(C.PROGRESS_BASELINE, str)

    def test_progress_optimized_value_and_type(self) -> None:
        """Verify PROGRESS_OPTIMIZED equals 'optimized_evaluated'."""
        assert C.PROGRESS_OPTIMIZED == "optimized_evaluated"
        assert isinstance(C.PROGRESS_OPTIMIZED, str)

    def test_progress_optimizer_value_and_type(self) -> None:
        """Verify PROGRESS_OPTIMIZER equals 'optimizer_progress'."""
        assert C.PROGRESS_OPTIMIZER == "optimizer_progress"
        assert isinstance(C.PROGRESS_OPTIMIZER, str)


class TestTqdmKeys:
    """tqdm key constants used in progress streaming must remain stable strings."""

    def test_tqdm_remaining_key_value_and_type(self) -> None:
        """Verify TQDM_REMAINING_KEY equals 'tqdm_remaining'."""
        assert C.TQDM_REMAINING_KEY == "tqdm_remaining"
        assert isinstance(C.TQDM_REMAINING_KEY, str)

    def test_tqdm_total_key_value_and_type(self) -> None:
        """Verify TQDM_TOTAL_KEY equals 'tqdm_total'."""
        assert C.TQDM_TOTAL_KEY == "tqdm_total"
        assert isinstance(C.TQDM_TOTAL_KEY, str)

    def test_tqdm_n_key_value_and_type(self) -> None:
        """Verify TQDM_N_KEY equals 'tqdm_n'."""
        assert C.TQDM_N_KEY == "tqdm_n"
        assert isinstance(C.TQDM_N_KEY, str)


class TestOptimizationTypeStrings:
    """Optimization type values appear in stored overviews and API responses."""

    def test_optimization_type_run_value_and_type(self) -> None:
        """Verify OPTIMIZATION_TYPE_RUN equals 'run'."""
        assert C.OPTIMIZATION_TYPE_RUN == "run"
        assert isinstance(C.OPTIMIZATION_TYPE_RUN, str)

    def test_optimization_type_grid_search_value_and_type(self) -> None:
        """Verify OPTIMIZATION_TYPE_GRID_SEARCH equals 'grid_search'."""
        assert C.OPTIMIZATION_TYPE_GRID_SEARCH == "grid_search"
        assert isinstance(C.OPTIMIZATION_TYPE_GRID_SEARCH, str)


class TestPayloadOverviewKeys:
    """A selection of payload overview key constants used as dict keys in the API."""

    def test_payload_overview_job_type_is_str(self) -> None:
        """Verify PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE equals 'optimization_type'."""
        assert isinstance(C.PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, str)
        assert C.PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE == "optimization_type"

    def test_payload_overview_username_is_str(self) -> None:
        """Verify PAYLOAD_OVERVIEW_USERNAME equals 'username'."""
        assert isinstance(C.PAYLOAD_OVERVIEW_USERNAME, str)
        assert C.PAYLOAD_OVERVIEW_USERNAME == "username"

    def test_payload_overview_total_pairs_is_str(self) -> None:
        """Verify PAYLOAD_OVERVIEW_TOTAL_PAIRS equals 'total_pairs'."""
        assert isinstance(C.PAYLOAD_OVERVIEW_TOTAL_PAIRS, str)
        assert C.PAYLOAD_OVERVIEW_TOTAL_PAIRS == "total_pairs"
