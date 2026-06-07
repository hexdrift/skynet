"""Tests for recovering and explaining DSPy's generic run failures."""

from __future__ import annotations

import logging

from core.service_gateway.optimization import llm_error

_GENERIC = "Execution cancelled due to errors or interruption."

_RAW_BILLING = (
    "Error for Example({'question': 'x'}) (input_keys={'question'}): "
    "litellm.RateLimitError: RateLimitError: OpenAIException - Error code: 429 - "
    "{'error': {'message': 'You exceeded your current quota, please check your plan "
    "and billing details.', 'type': 'insufficient_quota'}}. "
    "Set `provide_traceback=True` for traceback."
)


def test_enrich_generic_with_billing_detail_explains_and_strips_wrapper() -> None:
    """A generic message plus a logged billing error becomes an explained, cleaned message."""
    out = llm_error.enrich_error_message(_GENERIC, detail=_RAW_BILLING)
    assert out.startswith("Billing/quota:")
    assert "Provider detail: litellm.RateLimitError" in out
    assert "Error for Example(" not in out
    assert "provide_traceback" not in out


def test_enrich_specific_message_passes_through_with_explanation() -> None:
    """A message that already carries signal is kept, prefixed with its explanation."""
    raw = "litellm.AuthenticationError: Incorrect API key provided"
    out = llm_error.enrich_error_message(raw)
    assert out.startswith("Authentication:")
    assert raw in out


def test_enrich_generic_without_detail_returns_generic() -> None:
    """With no captured cause, the generic message is returned unchanged rather than blanked."""
    llm_error.reset_llm_error()
    assert llm_error.enrich_error_message(_GENERIC) == _GENERIC


def test_classify_known_and_unknown() -> None:
    """Known provider failures map to explanations; unrelated text maps to None."""
    assert llm_error.classify_llm_error("HTTP 429 too many requests").startswith("Rate limit:")
    assert llm_error.classify_llm_error("context_length exceeded").startswith("Context window:")
    assert llm_error.classify_llm_error("some unrelated failure") is None


def test_capture_handler_records_latest_dspy_error() -> None:
    """The capture handler surfaces the most recent ERROR record from the dspy logger."""
    dspy_logger = logging.getLogger("dspy")
    capture = llm_error.LlmErrorCapture()
    llm_error.reset_llm_error()
    dspy_logger.addHandler(capture)
    try:
        logging.getLogger("dspy.utils.parallelizer").error(_RAW_BILLING)
        assert llm_error.current_llm_error() == _RAW_BILLING
        out = llm_error.enrich_error_message(_GENERIC)
        assert out.startswith("Billing/quota:")
    finally:
        dspy_logger.removeHandler(capture)
        llm_error.reset_llm_error()
