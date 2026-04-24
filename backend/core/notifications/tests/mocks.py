"""Centralized mock builders for core/notifications tests.

HTTP response doubles, channel-enable helpers, and realistic notification
payloads loaded from live-captured fixtures.
"""

from __future__ import annotations

from typing import Any

import requests

from tests.fixtures import load_fixture




class FakeHTTPResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        pass


class FakeFailingResponse:
    status_code = 500

    def raise_for_status(self) -> None:
        raise requests.HTTPError("500 Server Error")


def fake_requests_post_ok(*args: Any, **kwargs: Any) -> FakeHTTPResponse:
    """Drop-in for requests.post that always succeeds."""
    return FakeHTTPResponse()


def fake_requests_post_failing(*args: Any, **kwargs: Any) -> None:
    """Drop-in for requests.post that always raises HTTPError."""
    raise requests.HTTPError("500 Server Error")


def capture_requests_post() -> tuple[list[tuple], Any]:
    """Return (captured_list, callable) for inspecting requests.post calls.

    Usage::

        captured, fn = capture_requests_post()
        monkeypatch.setattr("requests.post", fn)
        ...
        url, kwargs = captured[0]
    """
    captured: list[tuple] = []

    def _post(url: str, **kwargs: Any) -> FakeHTTPResponse:
        captured.append((url, kwargs))
        return FakeHTTPResponse()

    return captured, _post




def enable_channel(
    monkeypatch: Any,
    module: Any,
    webhook: str = "https://example.com/hook",
) -> None:
    """Set ENABLED=True and WEBHOOK_URL on *module* via monkeypatch."""
    monkeypatch.setattr(module, "ENABLED", True)
    monkeypatch.setattr(module, "WEBHOOK_URL", webhook)


def disable_channel(monkeypatch: Any, module: Any) -> None:
    """Set ENABLED=False on *module* via monkeypatch."""
    monkeypatch.setattr(module, "ENABLED", False)




def real_success_summary() -> dict:
    return load_fixture("jobs/success_single_gepa.summary.json")


def real_failed_summary() -> dict:
    return load_fixture("jobs/failed_runtime.summary.json")


def real_grid_summary() -> dict:
    return load_fixture("jobs/success_grid.summary.json")


def real_cancelled_summary() -> dict:
    return load_fixture("jobs/cancelled_mid_run.summary.json")
