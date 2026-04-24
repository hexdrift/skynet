from __future__ import annotations

import pytest
import requests

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
    """send_message() returns False when ENABLED=False (channel not configured)."""
    disable_channel(monkeypatch, comms_module)

    result = send_message("hello")

    assert result is False


def test_send_message_does_not_call_requests_when_not_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_message() makes no HTTP call when the channel is disabled."""
    disable_channel(monkeypatch, comms_module)
    captured, fn = capture_requests_post()
    monkeypatch.setattr("requests.post", fn)

    send_message("hello")

    assert captured == []




def test_send_message_returns_true_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_message() returns True when the webhook responds with a 2xx status."""
    enable_channel(monkeypatch, comms_module)
    monkeypatch.setattr("requests.post", lambda *a, **kw: FakeHTTPResponse())

    result = send_message("hello")

    assert result is True


def test_send_message_posts_to_webhook_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_message() POSTs to the configured WEBHOOK_URL."""
    enable_channel(monkeypatch, comms_module)
    captured, fn = capture_requests_post()
    monkeypatch.setattr("requests.post", fn)

    send_message("hello")

    assert captured[0][0] == "https://example.com/hook"


def test_send_message_payload_contains_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_message() includes the text argument in the JSON payload."""
    enable_channel(monkeypatch, comms_module)
    captured, fn = capture_requests_post()
    monkeypatch.setattr("requests.post", fn)

    send_message("my message text")

    assert captured[0][1].get("json", {})["text"] == "my message text"


def test_send_message_uses_default_channel_when_none_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_message() falls back to the module-level CHANNEL when channel=None."""
    enable_channel(monkeypatch, comms_module)
    monkeypatch.setattr(comms_module, "CHANNEL", "#my-channel")
    captured, fn = capture_requests_post()
    monkeypatch.setattr("requests.post", fn)

    send_message("hello", channel=None)

    assert captured[0][1].get("json", {})["channel"] == "#my-channel"


def test_send_message_uses_explicit_channel_when_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit channel argument overrides the module-level CHANNEL default."""
    enable_channel(monkeypatch, comms_module)
    monkeypatch.setattr(comms_module, "CHANNEL", "#default")
    captured, fn = capture_requests_post()
    monkeypatch.setattr("requests.post", fn)

    send_message("hello", channel="#override")

    assert captured[0][1].get("json", {})["channel"] == "#override"


def test_send_message_uses_10s_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_message() passes timeout=10 to requests.post."""
    enable_channel(monkeypatch, comms_module)
    captured, fn = capture_requests_post()
    monkeypatch.setattr("requests.post", fn)

    send_message("hello")

    assert captured[0][1]["timeout"] == 10




def test_send_message_returns_false_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_message() returns False when raise_for_status() raises HTTPError."""
    enable_channel(monkeypatch, comms_module)
    monkeypatch.setattr("requests.post", lambda *a, **kw: FakeFailingResponse())

    result = send_message("hello")

    assert result is False


def test_send_message_returns_false_on_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_message() returns False when requests.post raises ConnectionError."""
    enable_channel(monkeypatch, comms_module)

    def fake_post(*args, **kwargs):
        raise requests.ConnectionError("unreachable")

    monkeypatch.setattr("requests.post", fake_post)

    result = send_message("hello")

    assert result is False


def test_send_message_does_not_propagate_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enable_channel(monkeypatch, comms_module)

    def fake_post(*args, **kwargs):
        raise RuntimeError("unexpected boom")

    monkeypatch.setattr("requests.post", fake_post)

    # Must not raise — swallows and returns False
    result = send_message("hello")
    assert result is False




def test_send_message_enabled_but_empty_webhook_url_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ENABLED=True but WEBHOOK_URL="" causes requests.post to raise
    MissingSchema (or similar); the except-block must swallow it and
    return False without propagating.
    """
    enable_channel(monkeypatch, comms_module, webhook="")

    # Do NOT mock requests.post — let it raise its real MissingSchema error
    # so we verify the source's except-block handles it.
    result = send_message("hello")

    assert result is False


def test_send_message_enabled_but_empty_webhook_url_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return value must be False (not True, not None) when URL is empty."""
    enable_channel(monkeypatch, comms_module, webhook="")

    result = send_message("any text")

    assert result is False
