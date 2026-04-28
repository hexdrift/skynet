"""Tests for ``core.service_gateway.language_models.build_language_model``."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.exceptions import ServiceError
from core.models import ModelConfig
from core.service_gateway.language_models import build_language_model


def _cfg(**kwargs: Any) -> ModelConfig:
    """Build a ``ModelConfig`` with a default model name and optional overrides."""
    base: dict[str, Any] = {"name": "openai/gpt-4o-mini"}
    base.update(kwargs)
    return ModelConfig(**base)


def test_build_language_model_passes_model_name_to_dspy() -> None:
    """The model name is passed through to ``dspy.LM`` and the LM is returned."""
    mock_lm = MagicMock()

    with patch("dspy.LM", return_value=mock_lm) as mock_cls:
        result = build_language_model(_cfg(name="openai/gpt-4o-mini"))

    mock_cls.assert_called_once()
    call_kwargs = mock_cls.call_args[1]
    assert call_kwargs["model"] == "openai/gpt-4o-mini"
    assert result is mock_lm


def test_build_language_model_strips_leading_slash_from_name() -> None:
    """A leading slash in the model name is stripped before forwarding."""
    with patch("dspy.LM") as mock_cls:
        build_language_model(_cfg(name="/openai/gpt-4o-mini"))

    call_kwargs = mock_cls.call_args[1]
    assert call_kwargs["model"] == "openai/gpt-4o-mini"


def test_build_language_model_includes_temperature() -> None:
    """The ``temperature`` value is forwarded to ``dspy.LM``."""
    with patch("dspy.LM") as mock_cls:
        build_language_model(_cfg(temperature=0.7))

    call_kwargs = mock_cls.call_args[1]
    assert call_kwargs["temperature"] == 0.7


def test_build_language_model_omits_base_url_when_none() -> None:
    """``base_url`` is omitted from the call when unset."""
    with patch("dspy.LM") as mock_cls:
        build_language_model(_cfg(base_url=None))

    call_kwargs = mock_cls.call_args[1]
    assert "base_url" not in call_kwargs


def test_build_language_model_passes_base_url_when_set() -> None:
    """A configured ``base_url`` is forwarded to ``dspy.LM``."""
    with patch("dspy.LM") as mock_cls:
        build_language_model(_cfg(base_url="http://localhost:8080"))

    call_kwargs = mock_cls.call_args[1]
    assert call_kwargs["base_url"] == "http://localhost:8080"


def test_build_language_model_omits_max_tokens_when_none() -> None:
    """``max_tokens`` is omitted when not configured."""
    with patch("dspy.LM") as mock_cls:
        build_language_model(_cfg(max_tokens=None))

    call_kwargs = mock_cls.call_args[1]
    assert "max_tokens" not in call_kwargs


def test_build_language_model_passes_max_tokens_when_set() -> None:
    """A configured ``max_tokens`` is forwarded to ``dspy.LM``."""
    with patch("dspy.LM") as mock_cls:
        build_language_model(_cfg(max_tokens=512))

    call_kwargs = mock_cls.call_args[1]
    assert call_kwargs["max_tokens"] == 512


def test_build_language_model_omits_top_p_when_none() -> None:
    """``top_p`` is omitted when not configured."""
    with patch("dspy.LM") as mock_cls:
        build_language_model(_cfg(top_p=None))

    call_kwargs = mock_cls.call_args[1]
    assert "top_p" not in call_kwargs


def test_build_language_model_passes_top_p_when_set() -> None:
    """A configured ``top_p`` is forwarded to ``dspy.LM``."""
    with patch("dspy.LM") as mock_cls:
        build_language_model(_cfg(top_p=0.9))

    call_kwargs = mock_cls.call_args[1]
    assert call_kwargs["top_p"] == 0.9


def test_build_language_model_merges_extra_kwargs() -> None:
    """Entries in the ``extra`` mapping are merged into the call kwargs."""
    with patch("dspy.LM") as mock_cls:
        build_language_model(_cfg(extra={"api_key": "sk-test", "timeout": 30}))

    call_kwargs = mock_cls.call_args[1]
    assert call_kwargs["api_key"] == "sk-test"
    assert call_kwargs["timeout"] == 30


def test_build_language_model_all_optional_fields_combined() -> None:
    """All optional fields can be combined and are forwarded together."""
    with patch("dspy.LM") as mock_cls:
        build_language_model(
            _cfg(
                name="openai/gpt-4o",
                base_url="http://proxy",
                temperature=0.5,
                max_tokens=256,
                top_p=0.95,
                extra={"logit_bias": {}},
            )
        )

    call_kwargs = mock_cls.call_args[1]
    assert call_kwargs["model"] == "openai/gpt-4o"
    assert call_kwargs["base_url"] == "http://proxy"
    assert call_kwargs["temperature"] == 0.5
    assert call_kwargs["max_tokens"] == 256
    assert call_kwargs["top_p"] == 0.95
    assert "logit_bias" in call_kwargs


def test_build_language_model_value_error_from_dspy_raises_service_error() -> None:
    """A ``ValueError`` from ``dspy.LM`` is wrapped into a ``ServiceError``."""
    with (
        patch("dspy.LM", side_effect=ValueError("unsupported model")),
        pytest.raises(ServiceError, match="Failed to build language model"),
    ):
        build_language_model(_cfg(name="bad/model"))


def test_build_language_model_service_error_message_contains_model_name() -> None:
    """The wrapped ``ServiceError`` message includes the offending model name."""
    with patch("dspy.LM", side_effect=ValueError("nope")), pytest.raises(ServiceError, match="my-model-name"):
        build_language_model(_cfg(name="my-model-name"))
