"""Tests for the TemplateCreateRequest model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.models.templates import TemplateCreateRequest


@pytest.mark.parametrize(
    ("length", "valid"),
    [
        (0, False),
        (1, True),
        (200, True),
        (201, False),
    ],
    ids=["empty", "min", "max", "over_max"],
)
def test_template_create_name_length_boundary(length: int, valid: bool) -> None:
    """Verify TemplateCreateRequest.name accepts [1, 200] characters and rejects outside."""
    name = "x" * length

    if valid:
        req = TemplateCreateRequest(name=name, username="u", config={"k": "v"})
        assert req.name == name
    else:
        with pytest.raises(ValidationError):
            TemplateCreateRequest(name=name, username="u", config={"k": "v"})


def test_template_create_rejects_config_exceeding_100kb() -> None:
    """Verify TemplateCreateRequest rejects a config larger than 100KB when serialized."""
    huge = {"x": "y" * 150_000}

    with pytest.raises(ValidationError, match="maximum size"):
        TemplateCreateRequest(name="t", username="u", config=huge)


def test_template_create_accepts_config_just_under_limit() -> None:
    """Verify TemplateCreateRequest accepts a small config under the size limit."""
    req = TemplateCreateRequest(name="t", username="u", config={"key": "value"})

    assert req.config == {"key": "value"}


def test_template_create_accepts_empty_config() -> None:
    """Verify TemplateCreateRequest accepts an empty config dict."""
    req = TemplateCreateRequest(name="t", username="u", config={})

    assert req.config == {}


def test_template_create_description_defaults_none() -> None:
    """Verify TemplateCreateRequest defaults description to None."""
    req = TemplateCreateRequest(name="t", username="u", config={})

    assert req.description is None


def test_template_create_description_accepted() -> None:
    """Verify TemplateCreateRequest stores a provided description."""
    req = TemplateCreateRequest(name="t", username="u", config={}, description="A useful template.")

    assert req.description == "A useful template."


def test_template_create_username_stored() -> None:
    """Verify TemplateCreateRequest persists the username."""
    req = TemplateCreateRequest(name="t", username="alice", config={})

    assert req.username == "alice"


def test_template_create_rejects_non_json_serializable_config() -> None:
    """Verify TemplateCreateRequest rejects configs with non-JSON-serializable values."""
    with pytest.raises(ValidationError, match="JSON-serializable"):
        TemplateCreateRequest(name="t", username="u", config={"opaque": object()})
