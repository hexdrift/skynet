"""Outlook mail transport for Skynet notifications.

On the on-prem Windows deployment Skynet runs on a domain-joined host with the
Outlook desktop client signed in, so notifications go out through Outlook via
COM automation (``win32com``): no SMTP host or credentials to configure, mail
is sent as the signed-in profile, and recipients resolve against the Exchange
Global Address List (GAL).

``win32com`` ships in ``pywin32`` and is Windows-only. On dev/CI hosts
(macOS/Linux) the import fails, ``win32`` is ``None``, and every send becomes a
logged no-op so the rest of the app is unaffected.
"""

from __future__ import annotations

import logging

try:
    import win32com.client as win32  # type: ignore[import-untyped]
except ImportError:  # Windows-only (pywin32); absent on dev/CI hosts.
    win32 = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_OL_MAIL_ITEM = 0  # Outlook.OlItemType.olMailItem


def resolve_email(username: str) -> str | None:
    """Resolve a Skynet username to a mail address for Outlook delivery.

    Returns ``None`` for now: usernames carry no email address until the
    on-prem SSO / Active Directory directory is wired up, so notifications are
    recorded and logged but not delivered. When SSO lands, resolve the address
    here — or return the AD ``username``/UPN and let Outlook resolve it against
    the GAL inside :func:`send_mail`.

    Args:
        username: Skynet account name (a share grantee or a job owner).

    Returns:
        The recipient's mail address, or ``None`` when it cannot be resolved
        yet — in which case delivery is skipped.
    """
    return None


def send_mail(to: str, subject: str, html_body: str) -> bool:
    """Send an HTML email through the local Outlook desktop client.

    Never raises: when Outlook/``win32com`` is unavailable (non-Windows dev
    hosts) or the COM call fails, the error is logged and ``False`` is returned
    so a notification can never break the request or job that triggered it.

    Args:
        to: Recipient mail address, or an AD name resolvable against the GAL.
        subject: Mail subject line.
        html_body: RTL HTML message body.

    Returns:
        ``True`` when Outlook accepted and sent the message, ``False`` when
        delivery was skipped (no Outlook) or failed.
    """
    if win32 is None:
        logger.info("Outlook unavailable (win32com not importable); skipping mail to %s", to)
        return False
    try:
        outlook = win32.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(_OL_MAIL_ITEM)
        recipient = mail.Recipients.Add(to)
        if not recipient.Resolve():
            logger.warning("Outlook could not resolve recipient %r against the GAL; skipping mail", to)
            return False
        mail.Subject = subject
        mail.HTMLBody = html_body
        mail.Send()
        logger.info("Outlook mail sent to %s", to)
        return True
    except Exception as exc:  # COM boundary: a send must never break the caller.
        logger.warning("Failed to send Outlook mail to %s: %s", to, exc)
        return False
