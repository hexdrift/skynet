"""Shared pytest fixtures for the ``core.notifications`` test suite."""

from __future__ import annotations

import pytest


class FakeComms:
    """Capture ``send_message`` calls in-memory for behaviour assertions."""

    def __init__(self) -> None:
        """Start with an empty call log."""
        self.calls: list[dict] = []

    def send_message(self, text: str, channel: str | None = None) -> bool:
        """Record a ``send_message`` invocation and pretend it succeeded.

        Args:
            text: Message body that would have been sent.
            channel: Optional channel override.

        Returns:
            Always ``True`` to mimic a successful webhook delivery.
        """
        self.calls.append({"text": text, "channel": channel})
        return True

    @property
    def call_count(self) -> int:
        """Return how many times ``send_message`` has been invoked."""
        return len(self.calls)

    def last_call(self) -> dict:
        """Return the most recent recorded call payload."""
        return self.calls[-1]


@pytest.fixture
def fake_comms() -> FakeComms:
    """Yield a fresh ``FakeComms`` instance for each test.

    Yields:
        A ``FakeComms`` ready to record ``send_message`` invocations.
    """
    return FakeComms()
