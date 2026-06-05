"""Tests for the FastMCP mount's tool-annotation derivation."""

from __future__ import annotations

from types import SimpleNamespace

from core.api.mcp_mount import _annotations_for_method, _annotations_for_route


def test_annotations_for_method_reads_are_read_only() -> None:
    """Safe HTTP reads project a read-only hint."""
    for method in ("GET", "HEAD", "OPTIONS"):
        ann = _annotations_for_method(method)
        assert ann is not None
        assert ann.readOnlyHint is True


def test_annotations_for_method_delete_is_destructive() -> None:
    """DELETE projects a non-read-only, destructive hint."""
    ann = _annotations_for_method("DELETE")
    assert ann is not None
    assert ann.readOnlyHint is False
    assert ann.destructiveHint is True


def test_annotations_for_method_writes_are_mutating_not_destructive() -> None:
    """Body-bearing writes project a non-read-only, non-destructive hint."""
    for method in ("POST", "PUT", "PATCH"):
        ann = _annotations_for_method(method)
        assert ann is not None
        assert ann.readOnlyHint is False
        assert ann.destructiveHint is False


def test_annotations_for_method_unmapped_returns_none() -> None:
    """A verb with no clear approval semantics stays unannotated."""
    assert _annotations_for_method("TRACE") is None


def test_annotations_for_route_falls_back_to_method() -> None:
    """A route with no authored hints inherits the method default."""
    route = SimpleNamespace(method="GET", extensions={})
    ann = _annotations_for_route(route)
    assert ann is not None
    assert ann.readOnlyHint is True


def test_annotations_for_route_authored_hint_overrides_method() -> None:
    """An authored destructive hint merges over a POST's mutating default."""
    route = SimpleNamespace(
        method="POST", extensions={"x-mcp-annotations": {"destructiveHint": True}}
    )
    ann = _annotations_for_route(route)
    assert ann is not None
    assert ann.readOnlyHint is False
    assert ann.destructiveHint is True


def test_annotations_for_route_authored_hint_without_method_default() -> None:
    """Authored hints apply even when the verb itself maps to no default."""
    route = SimpleNamespace(
        method="TRACE", extensions={"x-mcp-annotations": {"destructiveHint": True}}
    )
    ann = _annotations_for_route(route)
    assert ann is not None
    assert ann.destructiveHint is True
