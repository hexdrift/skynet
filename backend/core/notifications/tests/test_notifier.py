"""Tests for the ``core.notifications.notifier`` job-lifecycle messages."""

from __future__ import annotations

import pytest

import core.notifications.notifier as notifier_module
from core.notifications.notifier import _job_url, notify_job_completed, notify_job_started

from .conftest import FakeComms


def test_notify_job_started_calls_send_message_once(monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms) -> None:
    """``notify_job_started`` invokes ``send_message`` exactly once."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_started(
        optimization_id="abc123",
        username="alice",
        optimization_type="run",
        optimizer_name="GEPA",
        module_name="MyModule",
    )

    assert fake_comms.call_count == 1


def test_notify_job_started_message_contains_username(monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms) -> None:
    """The submission message includes the username."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_started(
        optimization_id="abc123",
        username="alice",
        optimization_type="run",
        optimizer_name="GEPA",
        module_name="MyModule",
    )

    assert "alice" in fake_comms.last_call()["text"]


def test_notify_job_started_message_contains_optimizer_name(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """The submission message includes the optimizer name."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_started(
        optimization_id="abc123",
        username="alice",
        optimization_type="run",
        optimizer_name="GEPA",
        module_name="MyModule",
    )

    assert "GEPA" in fake_comms.last_call()["text"]


def test_notify_job_started_message_contains_module_name(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """The submission message includes the module name."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_started(
        optimization_id="abc123",
        username="alice",
        optimization_type="run",
        optimizer_name="GEPA",
        module_name="MyModule",
    )

    assert "MyModule" in fake_comms.last_call()["text"]


def test_notify_job_started_message_contains_optimization_id_as_link(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """The submission message embeds the optimization id (used in the dashboard link)."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_started(
        optimization_id="abc123",
        username="alice",
        optimization_type="run",
        optimizer_name="GEPA",
        module_name="MyModule",
    )

    assert "abc123" in fake_comms.last_call()["text"]


@pytest.mark.parametrize(
        ("optimization_type", "expected_label"),
        [
            ("grid_search", "סריקה"),
            ("run", "ריצה"),
            ("anything_else", "ריצה"),
        ],
)
def test_notify_job_started_type_label(
    monkeypatch: pytest.MonkeyPatch,
    fake_comms: FakeComms,
    optimization_type: str,
    expected_label: str,
) -> None:
    """``optimization_type`` maps to the correct Hebrew label, with ``run`` fallback."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_started(
        optimization_id="abc123",
        username="alice",
        optimization_type=optimization_type,
        optimizer_name="GEPA",
        module_name="MyModule",
    )

    assert expected_label in fake_comms.last_call()["text"]


def test_notify_job_started_unknown_type_logs_warning(
    monkeypatch: pytest.MonkeyPatch,
    fake_comms: FakeComms,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unknown optimization types are visible in logs while still notifying."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    with caplog.at_level("WARNING", logger="core.notifications.notifier"):
        notify_job_started(
            optimization_id="abc123",
            username="alice",
            optimization_type="anything_else",
            optimizer_name="GEPA",
            module_name="MyModule",
        )

    assert fake_comms.call_count == 1
    assert "Unknown optimization type for started notification: anything_else" in caplog.text


def test_notify_job_started_includes_model_name_when_provided(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """A non-None ``model_name`` is rendered inside the submission message."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_started(
        optimization_id="abc123",
        username="alice",
        optimization_type="run",
        optimizer_name="GEPA",
        module_name="MyModule",
        model_name="gpt-4o",
    )

    assert "gpt-4o" in fake_comms.last_call()["text"]


def test_notify_job_started_omits_model_part_when_model_name_is_none(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """When ``model_name`` is ``None`` the model label is omitted from the message."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_started(
        optimization_id="abc123",
        username="alice",
        optimization_type="run",
        optimizer_name="GEPA",
        module_name="MyModule",
        model_name=None,
    )

    assert "מודל:" not in fake_comms.last_call()["text"]


def test_notify_job_completed_success_calls_send_message_once(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """A success completion sends exactly one message."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="success",
    )

    assert fake_comms.call_count == 1


def test_notify_job_completed_success_message_contains_username(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """The success completion message includes the username."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="success",
    )

    assert "alice" in fake_comms.last_call()["text"]


def test_notify_job_completed_success_message_contains_optimization_id(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """The success completion message includes the optimization id (in the link)."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="success",
    )

    assert "abc123" in fake_comms.last_call()["text"]


def test_notify_job_completed_success_includes_scores_when_both_provided(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """When both scores are supplied, both percentages appear in the message."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="success",
        baseline_score=70.0,
        optimized_score=85.0,
    )

    text = fake_comms.last_call()["text"]
    assert "70.0%" in text
    assert "85.0%" in text


def test_notify_job_completed_success_shows_positive_improvement(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """Positive improvements render with a leading ``+`` sign."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="success",
        baseline_score=70.0,
        optimized_score=85.0,
    )

    assert "+15.0%" in fake_comms.last_call()["text"]


def test_notify_job_completed_success_shows_negative_improvement(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """Negative improvements render with the bare ``-`` sign (no ``+-``)."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="success",
        baseline_score=85.0,
        optimized_score=70.0,
    )

    text = fake_comms.last_call()["text"]
    assert "-15.0%" in text
    assert "+-" not in text


def test_notify_job_completed_success_omits_scores_when_only_baseline_provided(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """A baseline-only call omits the scores line."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="success",
        baseline_score=70.0,
        optimized_score=None,
    )

    text = fake_comms.last_call()["text"]
    assert "70.0%" not in text


def test_notify_job_completed_success_omits_scores_when_only_optimized_provided(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """An optimized-only call omits the scores line."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="success",
        baseline_score=None,
        optimized_score=85.0,
    )

    text = fake_comms.last_call()["text"]
    assert "85.0%" not in text


def test_notify_job_completed_cancelled_calls_send_message_once(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """A cancelled completion sends exactly one message."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="cancelled",
    )

    assert fake_comms.call_count == 1


def test_notify_job_completed_cancelled_message_contains_username(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """The cancelled completion message includes the username."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="cancelled",
    )

    assert "alice" in fake_comms.last_call()["text"]


def test_notify_job_completed_failed_calls_send_message_once(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """A failed completion sends exactly one message."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="failed",
    )

    assert fake_comms.call_count == 1


def test_notify_job_completed_failed_message_contains_username(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """The failed completion message includes the username."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="failed",
    )

    assert "alice" in fake_comms.last_call()["text"]


def test_notify_job_completed_failed_includes_message_when_provided(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """A non-None ``message`` is rendered inside the failure notification."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="failed",
        message="Something went wrong",
    )

    assert "Something went wrong" in fake_comms.last_call()["text"]


def test_notify_job_completed_failed_truncates_long_message(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """The failure ``message`` is truncated to 150 characters plus marker."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)
    long_error = "x" * 300

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="failed",
        message=long_error,
    )

    text = fake_comms.last_call()["text"]
    assert long_error not in text
    assert f"{'x' * 150}..." in text


def test_notify_job_completed_failed_omits_error_part_when_no_message(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """A failure with no ``message`` skips the error label entirely."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="failed",
        message=None,
    )

    assert "שגיאה:" not in fake_comms.last_call()["text"]


def test_notify_job_completed_unknown_status_treated_as_failed(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """Unknown statuses are skipped rather than mislabeled as failed."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="unknown_status",
    )

    assert fake_comms.call_count == 0


def test_notify_job_completed_unknown_status_logs_warning(
    monkeypatch: pytest.MonkeyPatch,
    fake_comms: FakeComms,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unknown statuses are logged for operator visibility."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    with caplog.at_level("WARNING", logger="core.notifications.notifier"):
        notify_job_completed(
            optimization_id="abc123",
            username="alice",
            status="unknown_status",
        )

    assert fake_comms.call_count == 0
    assert "Skipping notification for unknown job status: unknown_status" in caplog.text


def test_notify_job_completed_success_zero_improvement_uses_plus_sign(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """A zero improvement still uses the ``+`` prefix because the check is ``>= 0``."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="success",
        baseline_score=75.0,
        optimized_score=75.0,
    )

    assert "+0.0%" in fake_comms.last_call()["text"]


def test_job_url_uses_frontend_url_env_var_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_job_url`` honours the patched ``FRONTEND_URL`` env override."""
    monkeypatch.setattr(notifier_module, "FRONTEND_URL", "https://custom.example.com")

    url = _job_url("my-job-id")

    assert url == "https://custom.example.com/optimizations/my-job-id"


def test_job_url_uses_default_when_env_var_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_job_url`` defaults to the local frontend URL when nothing is overridden."""
    monkeypatch.setattr(notifier_module, "FRONTEND_URL", "http://localhost:3001")

    url = _job_url("my-job-id")

    assert url == "http://localhost:3001/optimizations/my-job-id"


def test_job_url_includes_optimization_id_in_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_job_url`` embeds the optimization id into the path."""
    monkeypatch.setattr(notifier_module, "FRONTEND_URL", "https://app.example.com")

    url = _job_url("unique-opt-id-42")

    assert "unique-opt-id-42" in url


def test_job_url_env_override_appears_in_notification(monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms) -> None:
    """A patched ``FRONTEND_URL`` flows through into the rendered notification link."""
    monkeypatch.setattr(notifier_module, "FRONTEND_URL", "https://prod.example.com")
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_started(
        optimization_id="job-xyz",
        username="bob",
        optimization_type="run",
        optimizer_name="GEPA",
        module_name="MyModule",
    )

    assert "https://prod.example.com/optimizations/job-xyz" in fake_comms.last_call()["text"]
