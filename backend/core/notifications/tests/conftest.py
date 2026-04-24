from __future__ import annotations

import pytest


class FakeComms:
    """Records calls to send_message for assertion in tests."""

    def __init__(self) -> None:
        """Initialize with an empty call log."""
        self.calls: list[dict] = []

    def send_message(self, text: str, channel: str | None = None) -> bool:
        """Record a send_message call and return True (simulating success)."""
        self.calls.append({"text": text, "channel": channel})
        return True

    @property
    def call_count(self) -> int:
        """Return the number of recorded send_message calls."""
        return len(self.calls)

    def last_call(self) -> dict:
        """Return the most recent send_message call dict."""
        return self.calls[-1]


@pytest.fixture()
def fake_comms() -> FakeComms:
    """Return a fresh FakeComms instance for each test."""
    return FakeComms()
