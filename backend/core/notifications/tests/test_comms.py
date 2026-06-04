"""Tests for the ``core.notifications.comms`` Outlook transport."""

from __future__ import annotations

import pytest

import core.notifications.comms as comms_module
from core.notifications.comms import resolve_email, send_mail

from .mocks import FakeWin32


def test_resolve_email_returns_none_until_sso() -> None:
    """Recipient resolution is a no-op seam until the SSO directory is wired."""
    assert resolve_email("alice") is None


def test_send_mail_returns_false_when_win32_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No Outlook/win32com (non-Windows dev host) yields a logged ``False``."""
    monkeypatch.setattr(comms_module, "win32", None)

    assert send_mail("alice@corp.example.com", "subject", "<p>body</p>") is False


def test_send_mail_logs_skip_when_win32_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The no-Outlook path logs the skipped recipient at INFO."""
    monkeypatch.setattr(comms_module, "win32", None)

    with caplog.at_level("INFO", logger="core.notifications.comms"):
        send_mail("alice@corp.example.com", "subject", "<p>body</p>")

    assert "skipping mail to alice@corp.example.com" in caplog.text


def test_send_mail_returns_true_on_send(monkeypatch: pytest.MonkeyPatch) -> None:
    """A resolvable recipient is composed and sent, returning ``True``."""
    fake = FakeWin32(resolved=True)
    monkeypatch.setattr(comms_module, "win32", fake)

    result = send_mail("alice@corp.example.com", "hello", "<p>hi</p>")

    assert result is True
    assert fake.app.item.sent is True


def test_send_mail_composes_subject_recipient_and_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Subject, HTML body, and recipient are set on the Outlook mail item."""
    fake = FakeWin32(resolved=True)
    monkeypatch.setattr(comms_module, "win32", fake)

    send_mail("alice@corp.example.com", "hello", "<p>hi</p>")

    item = fake.app.item
    assert item.Subject == "hello"
    assert item.HTMLBody == "<p>hi</p>"
    assert item.Recipients.added == ["alice@corp.example.com"]
    assert fake.dispatched == ["Outlook.Application"]


def test_send_mail_returns_false_when_recipient_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unresolved GAL recipient is skipped (no send) and yields ``False``."""
    fake = FakeWin32(resolved=False)
    monkeypatch.setattr(comms_module, "win32", fake)

    result = send_mail("ghost@corp.example.com", "hello", "<p>hi</p>")

    assert result is False
    assert fake.app.item.sent is False


def test_send_mail_logs_warning_when_recipient_unresolved(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unresolved recipient logs a warning naming the address."""
    fake = FakeWin32(resolved=False)
    monkeypatch.setattr(comms_module, "win32", fake)

    with caplog.at_level("WARNING", logger="core.notifications.comms"):
        send_mail("ghost@corp.example.com", "hello", "<p>hi</p>")

    assert "could not resolve recipient" in caplog.text


def test_send_mail_returns_false_on_com_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A COM failure during Dispatch is swallowed and surfaces as ``False``."""
    fake = FakeWin32(dispatch_error=RuntimeError("COM boom"))
    monkeypatch.setattr(comms_module, "win32", fake)

    result = send_mail("alice@corp.example.com", "hello", "<p>hi</p>")

    assert result is False


def test_send_mail_logs_warning_on_com_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A COM failure logs a warning with the transport error."""
    fake = FakeWin32(dispatch_error=RuntimeError("COM boom"))
    monkeypatch.setattr(comms_module, "win32", fake)

    with caplog.at_level("WARNING", logger="core.notifications.comms"):
        send_mail("alice@corp.example.com", "hello", "<p>hi</p>")

    assert "Failed to send Outlook mail" in caplog.text
    assert "COM boom" in caplog.text
