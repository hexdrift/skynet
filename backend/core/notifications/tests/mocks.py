"""Centralized mock builders for core/notifications tests.

HTTP response doubles, channel-enable helpers, and realistic notification
payloads loaded from live-captured fixtures.
"""

from __future__ import annotations

from typing import Any

import requests  # type: ignore[import-untyped]


class FakeHTTPResponse:
    """Stand-in for a successful 200 ``requests`` response."""

    status_code = 200

    def raise_for_status(self) -> None:
        """No-op to satisfy the ``requests`` API surface for success cases."""


class FakeFailingResponse:
    """Stand-in for a 500 ``requests`` response that raises on ``raise_for_status``."""

    status_code = 500

    def raise_for_status(self) -> None:
        """Raise ``requests.HTTPError`` to mimic a server failure.

        Raises:
            requests.HTTPError: Always.
        """
        raise requests.HTTPError("500 Server Error")


def capture_requests_post() -> tuple[list[tuple], Any]:
    """Return a list to record calls and a fake ``requests.post`` that appends to it.

    Returns:
        Tuple of ``(captured_list, callable)``. Monkeypatch
        ``requests.post`` with the callable, then assert against
        ``captured_list`` to inspect call arguments.
    """
    captured: list[tuple] = []

    def _post(url: str, **kwargs: Any) -> FakeHTTPResponse:
        """Capture the call and return a successful fake response."""
        captured.append((url, kwargs))
        return FakeHTTPResponse()

    return captured, _post


def enable_channel(
    monkeypatch: Any,
    module: Any,
    webhook: str = "https://example.com/hook",
) -> None:
    """Force a comms ``module`` to be enabled with the given webhook URL.

    Args:
        monkeypatch: pytest's ``MonkeyPatch`` fixture.
        module: The comms module whose ``ENABLED``/``WEBHOOK_URL`` are patched.
        webhook: Target webhook URL to install on the module.
    """
    monkeypatch.setattr(module, "ENABLED", True)
    monkeypatch.setattr(module, "WEBHOOK_URL", webhook)


def disable_channel(monkeypatch: Any, module: Any) -> None:
    """Force a comms ``module`` to act as if no webhook is configured.

    Args:
        monkeypatch: pytest's ``MonkeyPatch`` fixture.
        module: The comms module whose ``ENABLED`` flag is set to ``False``.
    """
    monkeypatch.setattr(module, "ENABLED", False)
