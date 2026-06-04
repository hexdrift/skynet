"""Centralized mock builders for core/notifications tests.

Outlook/``win32com`` COM doubles so the transport in ``core.notifications.comms``
can be exercised on any platform without a real Outlook client.
"""

from __future__ import annotations


class FakeRecipient:
    """Stand-in for an Outlook ``Recipient`` with a configurable GAL resolve."""

    def __init__(self, name: str, resolved: bool) -> None:
        """Record the added name and whether the GAL lookup should succeed."""
        self.name = name
        self._resolved = resolved

    def Resolve(self) -> bool:  # noqa: N802 — mirrors the Outlook COM API name.
        """Return whether the recipient resolves against the address book."""
        return self._resolved


class FakeRecipients:
    """Stand-in for an Outlook ``Recipients`` collection."""

    def __init__(self, resolved: bool) -> None:
        """Track added recipients; ``resolved`` controls their resolve result."""
        self.added: list[str] = []
        self._resolved = resolved

    def Add(self, name: str) -> FakeRecipient:  # noqa: N802 — Outlook COM API name.
        """Record and return a recipient for ``name``."""
        self.added.append(name)
        return FakeRecipient(name, self._resolved)


class FakeMailItem:
    """Stand-in for an Outlook ``MailItem`` capturing the composed message."""

    def __init__(self, resolved: bool) -> None:
        """Initialise empty mail fields; ``resolved`` flows to recipients."""
        self.Recipients = FakeRecipients(resolved)
        self.Subject: str | None = None
        self.HTMLBody: str | None = None
        self.sent = False

    def Send(self) -> None:  # noqa: N802 — Outlook COM API name.
        """Mark the message as sent."""
        self.sent = True


class FakeOutlookApp:
    """Stand-in for the ``Outlook.Application`` COM object."""

    def __init__(self, resolved: bool) -> None:
        """Hold a single reusable mail item; ``resolved`` flows to recipients."""
        self.item = FakeMailItem(resolved)
        self.created_item_types: list[int] = []

    def CreateItem(self, item_type: int) -> FakeMailItem:  # noqa: N802 — COM API name.
        """Record the requested item type and return the mail item."""
        self.created_item_types.append(item_type)
        return self.item


class FakeWin32:
    """Stand-in for the ``win32com.client`` module used by ``comms``."""

    def __init__(self, *, resolved: bool = True, dispatch_error: Exception | None = None) -> None:
        """Configure resolve success and an optional Dispatch failure.

        Args:
            resolved: Whether ``Recipient.Resolve()`` returns ``True``.
            dispatch_error: When set, ``Dispatch`` raises it (COM failure path).
        """
        self.app = FakeOutlookApp(resolved)
        self._dispatch_error = dispatch_error
        self.dispatched: list[str] = []

    def Dispatch(self, prog_id: str) -> FakeOutlookApp:  # noqa: N802 — COM API name.
        """Return the fake Outlook app, or raise the configured COM error."""
        self.dispatched.append(prog_id)
        if self._dispatch_error is not None:
            raise self._dispatch_error
        return self.app
