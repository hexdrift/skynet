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


def test_send_message_does_not_propagate_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even unexpected ``RuntimeError`` is swallowed and surfaces as ``False``."""
    enable_channel(monkeypatch, comms_module)

    def fake_post(*args, **kwargs):
        """Raise ``RuntimeError`` to simulate an unexpected transport bug."""
        raise RuntimeError("unexpected boom")

    monkeypatch.setattr("requests.post", fake_post)

    result = send_message("hello")
    assert result is False


def test_send_message_enabled_but_empty_webhook_url_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enabled channel with an empty webhook URL must not propagate exceptions."""
    # Empty WEBHOOK_URL makes requests.post raise MissingSchema; the source's
    # except-block must swallow it and return False — do NOT mock requests.post
    # here so the real exception path is exercised.
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
