from __future__ import annotations

import pytest

import core.notifications.notifier as notifier_module
from core.notifications.notifier import _job_url, notify_job_completed, notify_job_started

from .conftest import FakeComms




def test_notify_job_started_calls_send_message_once(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """notify_job_started() calls send_message exactly once."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_started(
        optimization_id="abc123",
        username="alice",
        optimization_type="run",
        optimizer_name="GEPA",
        module_name="MyModule",
    )

    assert fake_comms.call_count == 1


def test_notify_job_started_message_contains_username(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """notify_job_started() includes the username in the notification text."""
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
    """notify_job_started() includes the optimizer name in the notification text."""
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
    """notify_job_started() includes the module name in the notification text."""
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
    """notify_job_started() includes the optimization_id in the notification text."""
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
    "optimization_type, expected_label",
    [
        ("grid_search", "סריקה"),
        ("run", "ריצה"),
        ("anything_else", "ריצה"),  # default branch
    ],
)
def test_notify_job_started_type_label(
    monkeypatch: pytest.MonkeyPatch,
    fake_comms: FakeComms,
    optimization_type: str,
    expected_label: str,
) -> None:
    """notify_job_started() uses the correct Hebrew type label for each optimization type."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_started(
        optimization_id="abc123",
        username="alice",
        optimization_type=optimization_type,
        optimizer_name="GEPA",
        module_name="MyModule",
    )

    assert expected_label in fake_comms.last_call()["text"]


def test_notify_job_started_includes_model_name_when_provided(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """notify_job_started() includes the model name in the text when it is provided."""
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
    """notify_job_started() omits the model name section when model_name=None."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_started(
        optimization_id="abc123",
        username="alice",
        optimization_type="run",
        optimizer_name="GEPA",
        module_name="MyModule",
        model_name=None,
    )

    # "מודל:" is the Hebrew label that appears only when model_name is set
    assert "מודל:" not in fake_comms.last_call()["text"]




def test_notify_job_completed_success_calls_send_message_once(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """notify_job_completed() sends exactly one message for a success status."""
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
    """notify_job_completed() includes the username in the success notification."""
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
    """notify_job_completed() includes the optimization_id in the success notification."""
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
    """notify_job_completed() includes baseline and optimized scores when both are given."""
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
    """A positive score delta is prefixed with '+' in the notification text."""
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
    """A negative score delta is shown without a '+' prefix in the notification text."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="success",
        baseline_score=85.0,
        optimized_score=70.0,
    )

    text = fake_comms.last_call()["text"]
    # improvement is -15.0, no leading "+"
    assert "-15.0%" in text
    assert "+-" not in text


def test_notify_job_completed_success_omits_scores_when_only_baseline_provided(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """Scores are omitted from the notification when only baseline_score is given."""
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
    """Scores are omitted from the notification when only optimized_score is given."""
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
    """notify_job_completed() sends exactly one message for a cancelled status."""
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
    """notify_job_completed() includes the username in the cancelled notification."""
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
    """notify_job_completed() sends exactly one message for a failed status."""
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
    """notify_job_completed() includes the username in the failed notification."""
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
    """notify_job_completed() includes the error message text in the failed notification."""
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
    """notify_job_completed() truncates the error message to 150 characters."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)
    long_error = "x" * 300

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="failed",
        message=long_error,
    )

    # The notifier slices message[:150], so the full 300-char string must not appear
    assert long_error not in fake_comms.last_call()["text"]
    assert "x" * 150 in fake_comms.last_call()["text"]


def test_notify_job_completed_failed_omits_error_part_when_no_message(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """notify_job_completed() omits the error label when message=None."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="failed",
        message=None,
    )

    # "שגיאה:" is the Hebrew label prepended only when message is set
    assert "שגיאה:" not in fake_comms.last_call()["text"]




def test_notify_job_completed_unknown_status_treated_as_failed(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """An unrecognised status falls through to the failed branch and sends one message."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="unknown_status",
    )

    # Falls into else (failed) branch — should still send exactly once
    assert fake_comms.call_count == 1




def test_notify_job_completed_success_zero_improvement_uses_plus_sign(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """A zero score delta is rendered as '+0.0%' because the condition is >= 0."""
    monkeypatch.setattr(notifier_module, "send_message", fake_comms.send_message)

    notify_job_completed(
        optimization_id="abc123",
        username="alice",
        status="success",
        baseline_score=75.0,
        optimized_score=75.0,
    )

    # improvement == 0.0, condition is >= 0, so prefix must be "+"
    assert "+0.0%" in fake_comms.last_call()["text"]




def test_job_url_uses_frontend_url_env_var_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """_job_url() builds the URL from the FRONTEND_URL module attribute."""
    monkeypatch.setattr(notifier_module, "FRONTEND_URL", "https://custom.example.com")

    url = _job_url("my-job-id")

    assert url == "https://custom.example.com/optimizations/my-job-id"


def test_job_url_uses_default_when_env_var_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """_job_url() works correctly when FRONTEND_URL is the localhost default."""
    monkeypatch.setattr(notifier_module, "FRONTEND_URL", "http://localhost:3001")

    url = _job_url("my-job-id")

    assert url == "http://localhost:3001/optimizations/my-job-id"


def test_job_url_includes_optimization_id_in_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """_job_url() embeds the optimization_id as the final path segment."""
    monkeypatch.setattr(notifier_module, "FRONTEND_URL", "https://app.example.com")

    url = _job_url("unique-opt-id-42")

    assert "unique-opt-id-42" in url


def test_job_url_env_override_appears_in_notification(
    monkeypatch: pytest.MonkeyPatch, fake_comms: FakeComms
) -> None:
    """The full job URL built from FRONTEND_URL appears in the notification text."""
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
