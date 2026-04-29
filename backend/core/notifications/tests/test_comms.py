"""Tests for the ``core.notifications.comms`` webhook transport."""

from __future__ import annotations

import pytest
import requests  # type: ignore[import-untyped]

import core.notifications.comms as comms_module
from core.notifications.comms import send_message

from .mocks import (
    FakeFailingResponse,
    FakeHTTPResponse,
    capture_requests_post,
    disable_channel,
    enable_channel,
)


def test_send_message_returns_false_when_not_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled channel returns ``False`` without calling out to HTTP."""
    disable_channel(monkeypatch, comms_module)

    result = send_message("hello")

    assert result is False


def test_send_message_logs_truncated_debug_when_not_enabled(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Disabled channel debug log includes only the first 80 message chars."""
    disable_channel(monkeypatch, comms_module)
    message = "x" * 120

    with caplog.at_level("DEBUG", logger="core.notifications.comms"):
        result = send_message(message)

    assert result is False
    assert "x" * 80 in caplog.text
    assert "x" * 120 not in caplog.text


def test_send_message_does_not_call_requests_when_not_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled channel never invokes ``requests.post``."""
    disable_channel(monkeypatch, comms_module)
    captured, fn = capture_requests_post()
    monkeypatch.setattr("requests.post", fn)

    send_message("hello")

    assert captured == []


def test_send_message_returns_true_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful webhook delivery yields ``True``."""
    enable_channel(monkeypatch, comms_module)
    monkeypatch.setattr("requests.post", lambda *a, **kw: FakeHTTPResponse())

    result = send_message("hello")

    assert result is True


def test_send_message_logs_target_on_success(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Successful delivery logs the target channel."""
    enable_channel(monkeypatch, comms_module)
    monkeypatch.setattr("requests.post", lambda *a, **kw: FakeHTTPResponse())

    with caplog.at_level("INFO", logger="core.notifications.comms"):
        result = send_message("hello", channel="#alerts")

    assert result is True
    assert "Comms message sent to #alerts" in caplog.text


def test_send_message_posts_to_webhook_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The configured ``WEBHOOK_URL`` is the target of the POST."""
    enable_channel(monkeypatch, comms_module)
    captured, fn = capture_requests_post()
    monkeypatch.setattr("requests.post", fn)

    send_message("hello")

    assert captured[0][0] == "https://example.com/hook"


def test_send_message_payload_contains_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The JSON body contains the caller-provided ``text`` field."""
    enable_channel(monkeypatch, comms_module)
    captured, fn = capture_requests_post()
    monkeypatch.setattr("requests.post", fn)

    send_message("my message text")

    assert captured[0][1].get("json", {})["text"] == "my message text"


def test_send_message_uses_default_channel_when_none_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``channel=None`` falls back to the module-level default channel."""
    enable_channel(monkeypatch, comms_module)
    monkeypatch.setattr(comms_module, "CHANNEL", "#my-channel")
    captured, fn = capture_requests_post()
    monkeypatch.setattr("requests.post", fn)

    send_message("hello", channel=None)

    assert captured[0][1].get("json", {})["channel"] == "#my-channel"


def test_send_message_uses_explicit_channel_when_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit ``channel`` argument overrides the default."""
    enable_channel(monkeypatch, comms_module)
    monkeypatch.setattr(comms_module, "CHANNEL", "#default")
    captured, fn = capture_requests_post()
    monkeypatch.setattr("requests.post", fn)

    send_message("hello", channel="#override")

    assert captured[0][1].get("json", {})["channel"] == "#override"


def test_send_message_uses_10s_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The webhook POST is issued with a 10-second timeout."""
    enable_channel(monkeypatch, comms_module)
    captured, fn = capture_requests_post()
    monkeypatch.setattr("requests.post", fn)

    send_message("hello")

    assert captured[0][1]["timeout"] == 10


def test_send_message_returns_false_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 5xx response is swallowed and surfaces as ``False``."""
    enable_channel(monkeypatch, comms_module)
    monkeypatch.setattr("requests.post", lambda *a, **kw: FakeFailingResponse())

    result = send_message("hello")

    assert result is False


def test_send_message_logs_warning_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Failed delivery logs a warning with the transport error."""
    enable_channel(monkeypatch, comms_module)
    monkeypatch.setattr("requests.post", lambda *a, **kw: FakeFailingResponse())

    with caplog.at_level("WARNING", logger="core.notifications.comms"):
        result = send_message("hello")

    assert result is False
    assert "Failed to send comms message: 500 Server Error" in caplog.text


def test_send_message_returns_false_on_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A connection error is swallowed and surfaces as ``False``."""
    enable_channel(monkeypatch, comms_module)

    def fake_post(*args, **kwargs):
        """Raise ``requests.ConnectionError`` to simulate a network failure."""
        raise requests.ConnectionError("unreachable")

    monkeypatch.setattr("requests.post", fake_post)

    result = send_message("hello")

    assert result is False


def test_send_message_propagates_unexpected_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected programmer errors are not swallowed as transport failures."""
    enable_channel(monkeypatch, comms_module)

    def fake_post(*args, **kwargs):
        """Raise ``RuntimeError`` to simulate an unexpected transport bug."""
        raise RuntimeError("unexpected boom")

    monkeypatch.setattr("requests.post", fake_post)

    with pytest.raises(RuntimeError, match="unexpected boom"):
        send_message("hello")


def test_send_message_enabled_but_empty_webhook_url_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enabled channel with an empty webhook URL is treated as disabled."""
    enable_channel(monkeypatch, comms_module, webhook="")
    result = send_message("hello")

    assert result is False


def test_send_message_enabled_but_empty_webhook_url_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enabled channel with an empty webhook URL surfaces as ``False``."""
    enable_channel(monkeypatch, comms_module, webhook="")

    result = send_message("any text")

    assert result is False
