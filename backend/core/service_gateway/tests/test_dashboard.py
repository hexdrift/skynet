"""Tests for the public-dashboard aggregator (PER-11 Feature B)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from core.service_gateway import dashboard


def test_parse_pgvector_literal_string() -> None:
    """A bracketed comma list parses into a list of floats."""
    assert dashboard._parse_pgvector_literal("[0.1,0.25,-0.5]") == [0.1, 0.25, -0.5]


def test_parse_pgvector_literal_empty_and_none() -> None:
    """``None``, empty string, and ``[]`` all resolve to ``None``."""
    assert dashboard._parse_pgvector_literal(None) is None
    assert dashboard._parse_pgvector_literal("") is None
    assert dashboard._parse_pgvector_literal("[]") is None


def test_parse_pgvector_literal_list_passthrough() -> None:
    """If the driver already handed us a list, coerce to floats without reparsing."""
    assert dashboard._parse_pgvector_literal([1, 2, 3]) == [1.0, 2.0, 3.0]


def test_parse_pgvector_literal_bad_string_returns_none() -> None:
    """A malformed literal never raises — the caller skips the row."""
    assert dashboard._parse_pgvector_literal("[nope,1,2]") is None


def test_fit_pca_2d_empty_input() -> None:
    """An empty input list returns an empty list."""
    assert dashboard._fit_pca_2d([]) == []


def test_fit_pca_2d_single_vector_returns_origin() -> None:
    """A single row can't drive PCA — place it at the origin."""
    assert dashboard._fit_pca_2d([[0.1, 0.2, 0.3]]) == [(0.0, 0.0)]


def test_fit_pca_2d_normalises_to_unit_range() -> None:
    """Output coordinates are bounded by [-1, 1] so the frontend can treat them as normalised."""
    vectors = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    coords = dashboard._fit_pca_2d(vectors)
    assert len(coords) == 4
    for x, y in coords:
        assert -1.0001 <= x <= 1.0001
        assert -1.0001 <= y <= 1.0001
    # At least one point reaches the edge (post-normalisation extreme).
    max_abs = max(abs(c) for pair in coords for c in pair)
    assert max_abs > 0.5


def test_fit_pca_2d_survives_degenerate_matrix() -> None:
    """All-equal rows produce a zero-variance matrix — should not raise."""
    coords = dashboard._fit_pca_2d([[1.0, 2.0], [1.0, 2.0], [1.0, 2.0]])
    assert len(coords) == 3
    for x, y in coords:
        assert abs(x) < 1e-6
        assert abs(y) < 1e-6


def test_invalidate_projection_cache_resets_state() -> None:
    """``invalidate_projection_cache`` clears the fingerprint, timestamp, and payload."""
    dashboard._CACHE["fingerprint"] = "stale"
    dashboard._CACHE["at"] = 9e18
    dashboard._CACHE["payload"] = {"points": [{"optimization_id": "stale"}], "meta": {}}
    dashboard.invalidate_projection_cache()
    assert dashboard._CACHE["fingerprint"] is None
    assert dashboard._CACHE["at"] == 0.0
    assert dashboard._CACHE["payload"] is None


def test_compute_cluster_levels_empty() -> None:
    """An empty input yields one empty list per granularity level."""
    levels = dashboard._compute_cluster_levels([])
    assert len(levels) == dashboard.CLUSTER_LEVELS
    assert all(level == [] for level in levels)


def test_compute_cluster_levels_assigns_dense_ids() -> None:
    """Each level produces zero-indexed cluster IDs of the same length as the input."""
    coords = [
        (-1.0, -1.0),
        (-0.9, -1.0),
        (1.0, 1.0),
        (1.1, 0.9),
        (0.0, 0.0),
        (0.05, -0.1),
    ]
    levels = dashboard._compute_cluster_levels(coords)
    assert len(levels) == dashboard.CLUSTER_LEVELS
    for level in levels:
        assert len(level) == len(coords)
        assert all(isinstance(cid, int) and cid >= 0 for cid in level)


def _row(
    *,
    optimization_id: str,
    created_at: datetime,
    overview: dict | None = None,
    vector: str = "[0.1,0.2,0.3]",
) -> dict:
    """Build a fake DB mapping row matching the new ``_fetch_projection_rows`` shape."""
    return {
        "optimization_id": optimization_id,
        "optimization_type": "run",
        "winning_model": "gpt-4o-mini",
        "baseline_metric": 50.0,
        "optimized_metric": 75.0,
        "summary_text": "task summary",
        "task_name": "label",
        "module_name": "Predict",
        "optimizer_name": "MIPROv2",
        "created_at": created_at,
        "embedding_summary_text": vector,
        "payload_overview": overview or {},
    }


def _stub_session(rows: list[dict]) -> MagicMock:
    """Return a mock ``Session`` whose ``execute(...).mappings().all()`` yields ``rows``."""
    session = MagicMock(name="session")
    session.execute.return_value.mappings.return_value.all.return_value = rows
    return session


def test_fetch_projection_rows_collapses_same_compare_fingerprint() -> None:
    """Two rows with identical task + split collapse to one leader plus a sibling."""
    overview = {
        "task_fingerprint": "task-abc",
        "seed": 42,
        "shuffle": True,
        "split_fractions": {"train": 0.7, "val": 0.15, "test": 0.15},
    }
    rows = [
        _row(optimization_id="opt-newer", created_at=datetime(2026, 5, 14, 12, 0), overview=overview),
        _row(optimization_id="opt-older", created_at=datetime(2026, 5, 14, 11, 0), overview=overview),
    ]
    out = dashboard._fetch_projection_rows(_stub_session(rows))
    assert len(out) == 1
    leader = out[0]
    assert leader["optimization_id"] == "opt-newer"
    assert leader["siblings"] == ["opt-older"]
    assert leader["task_fingerprint"] == "task-abc"
    assert leader["compare_fingerprint"] is not None


def test_fetch_projection_rows_keeps_distinct_splits_separate() -> None:
    """Same task_fingerprint but different splits stay as two points."""
    overview_a = {
        "task_fingerprint": "task-xyz",
        "seed": 1,
        "shuffle": True,
        "split_fractions": {"train": 0.7, "val": 0.15, "test": 0.15},
    }
    overview_b = {
        "task_fingerprint": "task-xyz",
        "seed": 2,
        "shuffle": True,
        "split_fractions": {"train": 0.7, "val": 0.15, "test": 0.15},
    }
    rows = [
        _row(optimization_id="opt-a", created_at=datetime(2026, 5, 14, 12, 0), overview=overview_a),
        _row(optimization_id="opt-b", created_at=datetime(2026, 5, 14, 11, 0), overview=overview_b),
    ]
    out = dashboard._fetch_projection_rows(_stub_session(rows))
    assert len(out) == 2
    assert {p["optimization_id"] for p in out} == {"opt-a", "opt-b"}
    assert all(p["task_fingerprint"] == "task-xyz" for p in out)
    compare_fps = {p["compare_fingerprint"] for p in out}
    assert len(compare_fps) == 2
    assert all(p["siblings"] == [] for p in out)


def test_fetch_projection_rows_missing_task_fp_does_not_collapse() -> None:
    """Rows without a task_fingerprint each keep their own group (no bogus merge)."""
    rows = [
        _row(optimization_id="opt-a", created_at=datetime(2026, 5, 14, 12, 0), overview={}),
        _row(optimization_id="opt-b", created_at=datetime(2026, 5, 14, 11, 0), overview={}),
    ]
    out = dashboard._fetch_projection_rows(_stub_session(rows))
    assert len(out) == 2
    for point in out:
        assert point["task_fingerprint"] is None
        assert point["compare_fingerprint"] is None
        assert point["siblings"] == []


def test_fetch_projection_rows_skips_unparseable_vector() -> None:
    """A row whose embedding can't be parsed is dropped."""
    rows = [
        _row(
            optimization_id="bad-vec",
            created_at=datetime(2026, 5, 14, 12, 0),
            vector="[nope]",
        ),
    ]
    assert dashboard._fetch_projection_rows(_stub_session(rows)) == []
