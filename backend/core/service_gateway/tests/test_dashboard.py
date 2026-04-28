"""Tests for the public-dashboard aggregator (PER-11 Feature B)."""

from __future__ import annotations

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


def test_invalidate_projection_cache_resets_timestamp() -> None:
    """``invalidate_projection_cache`` zeros the timestamp and clears stored points."""
    dashboard._PROJECTION_CACHE["at"] = 9e18
    dashboard._PROJECTION_CACHE["points"] = [{"optimization_id": "stale"}]
    dashboard.invalidate_projection_cache()
    assert dashboard._PROJECTION_CACHE["at"] == 0.0
    assert dashboard._PROJECTION_CACHE["points"] == []
