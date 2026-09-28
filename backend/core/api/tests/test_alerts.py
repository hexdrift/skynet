"""Tests for the operational alert sinks (:mod:`core.api.alerts`).

Delivery runs on a daemon thread, so tests that assert on a POST join the
thread returned by :func:`~core.api.alerts.send_alert` first. The network call
itself is replaced with an in-memory recorder; no socket is ever opened.
"""

from __future__ import annotations

import logging
import sys

import pytest

from core.api import alerts
from core.config import settings


@pytest.fixture(autouse=True)
def _reset_throttle(monkeypatch):
    """Clear shared throttle state and disable email so nothing leaks between tests."""
    monkeypatch.setattr(settings, "alert_email", "")
    alerts._throttle._last_sent.clear()
    alerts._email_sent_at.clear()
    yield
    alerts._throttle._last_sent.clear()
    alerts._email_sent_at.clear()


@pytest.fixture
def captured_emails(monkeypatch):
    """Record alert emails in-memory with SMTP reported as configured and no webhook.

    Returns:
        The list that each :func:`~core.api.alerts.send_email` call appends
        ``(to, subject, body)`` to.
    """
    emails: list[tuple[str, str, str]] = []
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, body: emails.append((to, subject, body)))
    monkeypatch.setattr(alerts, "email_configured", lambda: True)
    monkeypatch.setattr(settings, "alert_webhook_url", "")
    monkeypatch.setattr(settings, "alert_email", "ops@example.com")
    monkeypatch.setattr(settings, "alert_email_max_per_hour", 20)
    monkeypatch.setattr(settings, "alert_environment", "test")
    monkeypatch.setattr(settings, "alert_throttle_seconds", 300.0)
    return emails


@pytest.fixture
def captured_posts(monkeypatch):
    """Record webhook posts in-memory and configure a webhook for the test.

    Returns:
        The list that each :func:`~core.api.alerts._post` call appends
        ``(url, text, timeout)`` to.
    """
    posts: list[tuple[str, str, float]] = []

    def _fake_post(url, text_value, timeout):
        posts.append((url, text_value, timeout))

    monkeypatch.setattr(alerts, "_post", _fake_post)
    monkeypatch.setattr(settings, "alert_webhook_url", "http://hook.test/webhook")
    monkeypatch.setattr(settings, "alert_min_level", "ERROR")
    monkeypatch.setattr(settings, "alert_environment", "test")
    monkeypatch.setattr(settings, "alert_throttle_seconds", 300.0)
    return posts


def _join(thread) -> None:
    """Assert a delivery thread was started and wait for it to finish.

    Args:
        thread: The thread returned by :func:`~core.api.alerts.send_alert`.
    """
    assert thread is not None
    thread.join(timeout=5.0)
    assert not thread.is_alive()


def test_send_alert_noop_when_webhook_unset(monkeypatch):
    """An unset webhook makes send_alert a no-op that never touches the network."""
    calls: list = []
    monkeypatch.setattr(alerts, "_post", lambda *args: calls.append(args))
    monkeypatch.setattr(settings, "alert_webhook_url", "")
    assert alerts.send_alert("boom") is None
    assert calls == []


def test_send_alert_posts_rendered_message(captured_posts):
    """A configured webhook receives one post carrying header, body and pod."""
    thread = alerts.send_alert("disk full", body="stack trace here", level="ERROR")
    _join(thread)
    assert len(captured_posts) == 1
    url, text_value, timeout = captured_posts[0]
    assert url == "http://hook.test/webhook"
    assert "[test] ERROR: disk full" in text_value
    assert "stack trace here" in text_value
    assert f"pod={alerts._POD_NAME}" in text_value
    assert timeout == alerts._DELIVERY_TIMEOUT_SECONDS


def test_identical_alerts_throttled_within_window(captured_posts):
    """A second identical alert inside the window is dropped."""
    _join(alerts.send_alert("same", level="ERROR", now=1000.0))
    second = alerts.send_alert("same", level="ERROR", now=1100.0)
    assert second is None
    assert len(captured_posts) == 1


def test_alert_resent_after_window(captured_posts):
    """An identical alert past the cooldown window is sent again."""
    _join(alerts.send_alert("same", level="ERROR", now=1000.0))
    _join(alerts.send_alert("same", level="ERROR", now=1000.0 + 301.0))
    assert len(captured_posts) == 2


def test_distinct_alerts_are_not_throttled(captured_posts):
    """Different titles at the same instant both go out — the key includes the title."""
    _join(alerts.send_alert("first", level="ERROR", now=1000.0))
    _join(alerts.send_alert("second", level="ERROR", now=1000.0))
    assert len(captured_posts) == 2


def test_throttle_disabled_lets_duplicates_through(captured_posts, monkeypatch):
    """A zero window disables throttling entirely."""
    monkeypatch.setattr(settings, "alert_throttle_seconds", 0.0)
    _join(alerts.send_alert("same", now=1.0))
    _join(alerts.send_alert("same", now=1.0))
    assert len(captured_posts) == 2


def test_delivery_swallows_post_failure(monkeypatch):
    """A failing POST is swallowed on the sender thread, never re-raised."""
    monkeypatch.setattr(settings, "alert_webhook_url", "http://hook.test/webhook")
    monkeypatch.setattr(settings, "alert_throttle_seconds", 0.0)

    def _boom(*args):
        raise OSError("network down")

    monkeypatch.setattr(alerts, "_post", _boom)
    thread = alerts.send_alert("will fail")
    assert thread is not None
    thread.join(timeout=5.0)
    assert not thread.is_alive()


def test_log_handler_passes_message_and_level(monkeypatch):
    """The handler forwards the formatted message as the title and the record level."""
    captured: dict[str, object] = {}

    def _fake_send(title, *, body="", level="ERROR"):
        captured.update(title=title, body=body, level=level)
        return

    monkeypatch.setattr(alerts, "send_alert", _fake_send)
    record = logging.LogRecord(
        name="core.api.app",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="boom %s",
        args=("x",),
        exc_info=None,
    )
    alerts.AlertLogHandler().emit(record)
    assert captured["title"] == "boom x"
    assert captured["level"] == "ERROR"
    assert captured["body"] == ""


def test_log_handler_includes_traceback(monkeypatch):
    """A record carrying exc_info has its formatted traceback forwarded as the body."""
    captured: dict[str, object] = {}

    def _fake_send(title, *, body="", level="ERROR"):
        captured.update(title=title, body=body, level=level)
        return

    monkeypatch.setattr(alerts, "send_alert", _fake_send)
    try:
        raise ValueError("kaboom")
    except ValueError:
        record = logging.LogRecord(
            name="core.api.app",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )
    alerts.AlertLogHandler().emit(record)
    assert "ValueError: kaboom" in captured["body"]
    assert "Traceback" in captured["body"]


def test_log_handler_skips_own_records(monkeypatch):
    """A record from the alerts module itself is not forwarded (recursion guard)."""
    called: list = []
    monkeypatch.setattr(alerts, "send_alert", lambda *args, **kwargs: called.append(args))
    record = logging.LogRecord(
        name=alerts.__name__,
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="delivery failed",
        args=(),
        exc_info=None,
    )
    alerts.AlertLogHandler().emit(record)
    assert called == []


def test_install_returns_none_when_unconfigured(monkeypatch):
    """No webhook means no handler is attached."""
    monkeypatch.setattr(settings, "alert_webhook_url", "")
    root = logging.getLogger("test-alerts-unconfigured")
    root.handlers.clear()
    assert alerts.install_alert_log_handler(root) is None
    assert not any(isinstance(h, alerts.AlertLogHandler) for h in root.handlers)


def test_install_attaches_handler_at_configured_level(monkeypatch):
    """A configured webhook attaches a handler set to ALERT_MIN_LEVEL."""
    monkeypatch.setattr(settings, "alert_webhook_url", "http://hook.test/webhook")
    monkeypatch.setattr(settings, "alert_min_level", "WARNING")
    root = logging.getLogger("test-alerts-configured")
    root.handlers.clear()
    handler = alerts.install_alert_log_handler(root)
    assert isinstance(handler, alerts.AlertLogHandler)
    assert handler.level == logging.WARNING
    assert handler in root.handlers
    root.handlers.clear()


def test_send_alert_emails_when_only_email_configured(captured_emails):
    """With no webhook, an alert is emailed with the header line as its subject."""
    _join(alerts.send_alert("disk full", body="details", level="WARNING", now=1.0))
    assert len(captured_emails) == 1
    to, subject, body = captured_emails[0]
    assert to == "ops@example.com"
    assert subject == "[test] WARNING: disk full"
    assert "details" in body


def test_email_skipped_without_smtp(captured_emails, monkeypatch):
    """ALERT_EMAIL alone does nothing when SMTP is not configured."""
    monkeypatch.setattr(alerts, "email_configured", lambda: False)
    assert alerts.send_alert("x", now=1.0) is None
    assert captured_emails == []


def test_email_hourly_cap(captured_emails, monkeypatch):
    """Distinct alerts past the hourly cap are not emailed; the cap resets after an hour."""
    monkeypatch.setattr(settings, "alert_email_max_per_hour", 2)
    for i in range(2):
        _join(alerts.send_alert(f"alert {i}", now=1.0))
    assert alerts.send_alert("alert 2", now=2.0) is None
    _join(alerts.send_alert("alert 3", now=1.0 + alerts._EMAIL_WINDOW_SECONDS))
    assert [subject for _, subject, _ in captured_emails] == [
        "[test] ERROR: alert 0",
        "[test] ERROR: alert 1",
        "[test] ERROR: alert 3",
    ]


def test_capped_email_still_posts_webhook(captured_emails, captured_posts, monkeypatch):
    """Hitting the email cap drops only the email; the webhook still fires."""
    monkeypatch.setattr(settings, "alert_email", "ops@example.com")
    monkeypatch.setattr(settings, "alert_email_max_per_hour", 0)
    _join(alerts.send_alert("both", now=1.0))
    assert len(captured_posts) == 1
    assert captured_emails == []


def test_email_failure_is_swallowed(captured_emails, monkeypatch):
    """A failing SMTP send is swallowed on the sender thread."""

    def _boom(*args):
        raise OSError("smtp down")

    monkeypatch.setattr(alerts, "send_email", _boom)
    _join(alerts.send_alert("will fail", now=1.0))


def test_install_with_email_only(captured_emails):
    """An email target alone is enough to attach the handler."""
    root = logging.getLogger("test-alerts-email-only")
    root.handlers.clear()
    handler = alerts.install_alert_log_handler(root)
    assert isinstance(handler, alerts.AlertLogHandler)
    root.removeHandler(handler)
