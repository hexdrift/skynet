"""Tests for the AI co-tagging engine's pure helpers.

Covers label normalization across the three annotation modes, defensive JSON
parsing of model output, few-shot example selection (corrections-first,
exclusions, provenance filtering), instruction compilation, token
estimation, and the synthetic-dataset generator's row normalization and
slicing.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from .. import tagging
from ..tagging import (
    MAX_EXAMPLES,
    InterviewTurnSig,
    _MessageLeakGuard,
    _normalize_synthetic_rows,
    _parse_interview_prediction,
    _parse_json,
    _StreamedArrayItems,
    assist_model_name,
    build_data_rows,
    compile_instructions,
    effective_task_config,
    estimate_tokens_for_rows,
    normalize_dataset_spec,
    normalize_label,
    select_examples,
    summarize_dataset,
    synthesize_rows,
    task_description,
)

_BINARY = {"mode": "binary", "inputColumns": ["text"], "question": "Positive?"}
_MULTI = {
    "mode": "multiclass",
    "inputColumns": ["text"],
    "categories": [
        {"id": "cat1", "label": "Billing"},
        {"id": "cat2", "label": "Support"},
    ],
}
_FREE = {"mode": "freetext", "inputColumns": ["text"], "prompt": "Extract the city."}


def test_normalize_binary_maps_variants() -> None:
    """Binary labels normalize yes/no spellings to 1/0 and reject junk."""
    assert normalize_label(_BINARY, "Yes") == "1"
    assert normalize_label(_BINARY, "NO") == "0"
    assert normalize_label(_BINARY, "true") == "1"
    assert normalize_label(_BINARY, "כן") == "1"
    assert normalize_label(_BINARY, "1") == "1"
    assert normalize_label(_BINARY, "0") == "0"
    assert normalize_label(_BINARY, "maybe") is None


def test_normalize_multiclass_maps_names_to_ids() -> None:
    """Category names map to ids case-insensitively; unknowns are dropped."""
    assert normalize_label(_MULTI, ["billing", "Support"]) == ["cat1", "cat2"]
    assert normalize_label(_MULTI, "Billing") == ["cat1"]
    assert normalize_label(_MULTI, ["cat2"]) == ["cat2"]
    assert normalize_label(_MULTI, ["nonsense"]) is None


def test_normalize_freetext_strips_and_rejects_empty() -> None:
    """Freetext labels are stripped strings; empty means unmappable."""
    assert normalize_label(_FREE, "  Paris ") == "Paris"
    assert normalize_label(_FREE, "") is None
    assert normalize_label(_FREE, None) is None


def test_parse_json_tolerates_fences_and_prose() -> None:
    """Model JSON survives code fences and surrounding prose."""
    assert _parse_json("```json\n[1, 2]\n```", None) == [1, 2]
    assert _parse_json('Here you go: {"a": 1} — done.', None) == {"a": 1}
    assert _parse_json("not json at all", "fallback") == "fallback"


def test_select_examples_prioritizes_corrections_and_excludes() -> None:
    """Corrections rank first; excluded and auto-tagged rows never appear."""
    data = [{"id": i, "text": f"row {i}"} for i in range(1, 6)]
    annotations = {"1": "yes", "2": "no", "3": "yes", "4": "no"}
    assist = {
        "predictions": {"2": {"value": "yes", "confidence": 0.9}},
        "provenance": {"1": "human", "2": "human", "3": "ai_confirmed", "4": "ai_auto"},
    }
    examples = select_examples(_BINARY, data, annotations, assist, exclude_ids={"3"})
    texts = [e["text"] for e in examples]
    assert texts[0] == "row 2"
    assert examples[0]["corrected_from"] == "yes"
    assert "row 3" not in texts
    assert "row 4" not in texts
    assert len(examples) <= MAX_EXAMPLES


def test_compile_instructions_carries_task_rubric_examples() -> None:
    """The compiled prompt contains the task, every rubric rule and examples."""
    examples = [{"text": "great", "label": "yes"}]
    prompt = compile_instructions(_BINARY, ["Sarcasm counts as negative."], examples)
    assert "Positive?" in prompt
    assert "Sarcasm counts as negative." in prompt
    assert "great" in prompt
    assert task_description(_MULTI).count("Billing") == 1


def test_missing_task_definition_interviews_in_both_assist_modes() -> None:
    """Autopilot automates the tagging, not the task definition — both modes ask."""
    base = {"mode": "binary", "inputColumns": ["text"]}
    copilot = task_description({**base, "_assist_mode": "copilot"})
    autopilot = task_description({**base, "_assist_mode": "autopilot"})
    assert "first question must ask" in copilot
    assert autopilot == copilot
    multiclass = task_description({"mode": "multiclass", "_assist_mode": "copilot"})
    extraction = task_description({"mode": "freetext", "_assist_mode": "autopilot"})
    assert "which categories" in multiclass
    assert "must ask the user" in extraction


def test_interview_normalizes_inferred_multiclass_categories() -> None:
    """Convert inferred category names into stable tagger category records."""
    pred = SimpleNamespace(
        done="true",
        message="Ready",
        options_json="[]",
        rubric_json='["Apply every matching category."]',
        task_config_json='{"categories": ["Billing", "Support", "Billing"]}',
    )
    turn = _parse_interview_prediction(pred, 1, {"mode": "multiclass"})
    assert turn["task_override"] == {
        "categories": [
            {"id": "cat1", "label": "Billing"},
            {"id": "cat2", "label": "Support"},
        ]
    }


def test_provisional_mode_interviews_in_both_assist_modes() -> None:
    """A provisional-mode config leaves the answer style to the interview."""
    base = {"mode": "freetext", "modeProvisional": True, "inputColumns": ["text"]}
    copilot = task_description({**base, "_assist_mode": "copilot"})
    autopilot = task_description({**base, "_assist_mode": "autopilot"})
    assert "You decide the answer style" in copilot
    assert "2-4 concrete task directions" in copilot
    assert '"mode"' in copilot
    assert autopilot == copilot


def test_provisional_override_carries_inferred_mode() -> None:
    """Finalize payloads on provisional sessions emit the inferred mode."""
    provisional = {"mode": "freetext", "modeProvisional": True}
    pred = SimpleNamespace(
        done="true",
        message="Ready",
        options_json="[]",
        rubric_json='["Answer the question."]',
        task_config_json='{"mode": "binary", "question": "Is it spam?"}',
    )
    turn = _parse_interview_prediction(pred, 1, provisional)
    assert turn["task_override"] == {"mode": "binary", "question": "Is it spam?"}
    pred.task_config_json = '{"categories": ["Billing", "Support"]}'
    turn = _parse_interview_prediction(pred, 1, provisional)
    assert turn["task_override"]["mode"] == "multiclass"
    assert [c["label"] for c in turn["task_override"]["categories"]] == ["Billing", "Support"]
    pred.task_config_json = '{"mode": "multiclass", "categories": ["Only one"]}'
    assert _parse_interview_prediction(pred, 1, provisional)["task_override"] == {}
    pred.task_config_json = '{"mode": "freetext"}'
    assert _parse_interview_prediction(pred, 1, provisional)["task_override"] == {"mode": "freetext"}


def test_synthetic_session_interviews_for_the_data_first() -> None:
    """A data-less synthetic session gets the data-first briefing and an empty summary."""
    config = {"mode": "freetext", "modeProvisional": True, "synthetic": True, "_synthetic_pending": True}
    description = task_description(config)
    assert "No dataset exists yet" in description
    assert "dataset_json" in description
    assert "how many rows" in description
    summary = json.loads(summarize_dataset(config, [], []))
    assert summary["row_count"] == 0
    assert "dataset_json" in summary["note"]
    # Once rows exist the flag is off and the regular provisional briefing applies.
    assert "No dataset exists yet" not in task_description(
        {"mode": "freetext", "modeProvisional": True, "synthetic": True}
    )
    assert len(InterviewTurnSig.output_fields) == 7
    assert list(InterviewTurnSig.output_fields)[-2:] == ["dataset_json", "session_title"]


def test_dataset_spec_rides_the_final_turn_of_synthetic_sessions_only() -> None:
    """The dataset spec is normalized, gated on ``done`` and dropped off synthetic sessions."""
    pending = {"mode": "freetext", "modeProvisional": True, "synthetic": True, "_synthetic_pending": True}
    pred = SimpleNamespace(
        done="true",
        message="Ready",
        options_json="[]",
        rubric_json='["Rule."]',
        task_config_json='{"mode": "binary", "question": "Is it a complaint?"}',
        dataset_json='{"brief": " Bank support chats ", "columns": ["text", "", "text", "channel"], "rows": "500"}',
        session_title="Bank complaints",
    )
    turn = _parse_interview_prediction(pred, 3, pending)
    assert turn["dataset_spec"] == {"brief": "Bank support chats", "columns": ["text", "channel"], "rows": 200}
    assert turn["task_override"] == {"mode": "binary", "question": "Is it a complaint?"}
    pred.done = "false"
    assert _parse_interview_prediction(pred, 3, pending)["dataset_spec"] == {}
    pred.done = "true"
    assert _parse_interview_prediction(pred, 3, _FREE)["dataset_spec"] == {}
    assert normalize_dataset_spec({"brief": "x", "rows": None}) == {"brief": "x", "columns": [], "rows": 30}
    assert normalize_dataset_spec({"columns": ["text"]}) == {}
    assert normalize_dataset_spec("nope") == {}


def test_synthetic_sessions_get_a_longer_interview() -> None:
    """The forced finish waits for the synthetic cap, since the data comes first."""
    pending = {"mode": "freetext", "modeProvisional": True, "synthetic": True, "_synthetic_pending": True}
    pred = SimpleNamespace(done="false", message="Next?", options_json="[]", rubric_json="[]", task_config_json="{}")
    assert _parse_interview_prediction(pred, 5, pending)["done"] is False
    assert _parse_interview_prediction(pred, 8, pending)["done"] is True
    assert _parse_interview_prediction(pred, 5, _FREE)["done"] is True


def test_build_data_rows_mirrors_the_setup_wizard_mapping() -> None:
    """Rows get ids, structured fields and the flat text the export and search read."""
    single = build_data_rows(["text"], [{"text": "Card declined"}])
    assert single == [{"text": "Card declined", "id": 1, "fields": [{"column": "text", "value": "Card declined"}]}]
    multi = build_data_rows(["text", "channel"], [{"text": "Hi", "channel": "chat"}, {"text": "Bye"}])
    assert multi[0]["text"] == "text: Hi\nchannel: chat"
    assert multi[1] == {
        "text": "text: Bye\nchannel: ",
        "id": 2,
        "fields": [{"column": "text", "value": "Bye"}, {"column": "channel", "value": ""}],
    }


def test_interview_title_rides_the_final_turn_only() -> None:
    """The proposed session title is stripped and gated on ``done``."""
    pred = SimpleNamespace(
        done="true",
        message="Ready",
        options_json="[]",
        rubric_json='["Rule."]',
        task_config_json="{}",
        session_title='  "Routing support tickets"  ',
    )
    turn = _parse_interview_prediction(pred, 1, _FREE)
    assert turn["title"] == "Routing support tickets"
    # session_title is the last output field, so minimax's malformed terminal
    # marker lands in its tail (seen in the wild as "… [[ ## completed ## ]").
    pred.session_title = "Route support tickets [[ ## completed ## ]"
    assert _parse_interview_prediction(pred, 1, _FREE)["title"] == "Route support tickets"
    pred.done = "false"
    assert _parse_interview_prediction(pred, 1, _FREE)["title"] == ""


def test_message_leak_guard_passes_clean_prose() -> None:
    """A prose reply streams through unchanged, flushing buffered whitespace."""
    guard = _MessageLeakGuard()
    assert guard.feed("\n") == ("", False)
    assert guard.feed("What should") == ("\nWhat should", False)
    assert guard.feed(" a row count as?") == (" a row count as?", False)


def test_message_leak_guard_mutes_structured_openings() -> None:
    """A reply that opens like the raw payload is never forwarded."""
    for opening in ('{"message": "hi",', "[[ ## message ## ]]", "```json"):
        guard = _MessageLeakGuard()
        assert guard.feed(opening) == ("", False)
        assert guard.feed(' "options_json": []}') == ("", False)


def test_message_leak_guard_resets_on_midstream_drift() -> None:
    """Prose that drifts into payload fields resets the client once, then mutes."""
    guard = _MessageLeakGuard()
    assert guard.feed("Which direction fits?") == ("Which direction fits?", False)
    assert guard.feed('\n"options_json": [{"label"') == ("", True)
    assert guard.feed(': "Topic"}]') == ("", False)


def test_interview_signature_streams_done_before_payload_fields() -> None:
    """``done`` precedes the slow payload fields so the stream can hint early.

    The interview stream emits ``turn_hint`` from the streamed ``done`` field;
    that only works while ``done`` is generated before options/rubric/task.
    """
    fields = list(InterviewTurnSig.output_fields)
    assert fields.index("done") < fields.index("options_json")
    assert fields.index("done") < fields.index("rubric_json")
    assert fields.index("done") < fields.index("task_config_json")
    assert fields.index("done") < fields.index("session_title")


def test_streamed_array_items_emits_objects_per_chunk() -> None:
    """Objects surface the moment their closing brace arrives, across chunk splits."""
    scanner = _StreamedArrayItems()
    assert scanner.feed('[{"id": "1", "label"') == []
    assert scanner.feed(': "yes"}, {"id": "2",') == [{"id": "1", "label": "yes"}]
    assert scanner.feed(' "label": "no"}]') == [{"id": "2", "label": "no"}]


def test_streamed_array_items_ignores_braces_inside_strings() -> None:
    """Braces and escaped quotes inside string values never skew the balance."""
    scanner = _StreamedArrayItems()
    items = scanner.feed('[{"id": "1", "reason": "brace } and quote \\" inside"}]')
    assert items == [{"id": "1", "reason": 'brace } and quote " inside'}]


def test_streamed_array_items_survives_fences_and_nesting() -> None:
    """Fences and prose around the array are ignored; nested objects stay whole."""
    scanner = _StreamedArrayItems()
    items = scanner.feed('```json\n[{"id": "1", "extra": {"a": 1}}]\n```')
    assert items == [{"id": "1", "extra": {"a": 1}}]


def test_predict_rows_stream_merges_batches_into_terminal_event(monkeypatch) -> None:
    """Per-row events from every batch relay through; the terminal map merges them."""

    async def fake_drive(*, lm, instructions, batch, config, queue, semaphore) -> None:
        """Emit one canned prediction event per batch row."""
        for row in batch:
            await queue.put(
                {
                    "event": "prediction",
                    "data": {"id": str(row["id"]), "prediction": {"value": "1", "confidence": 0.9, "reason": ""}},
                }
            )

    monkeypatch.setattr(tagging, "_drive_predict_batch", fake_drive)
    monkeypatch.setattr(tagging, "_build_assist_lm", lambda *a, **k: SimpleNamespace(history=[]))
    monkeypatch.setattr(tagging, "usage_by_model_from_history", lambda lm: {})
    rows = [{"id": i, "text": f"row {i}"} for i in range(tagging.BATCH_SIZE + 2)]

    async def run() -> list[dict]:
        """Collect the full event stream."""
        return [event async for event in tagging.predict_rows_stream(_BINARY, "instructions", rows)]

    events = asyncio.run(run())
    assert events[-1]["event"] == "predict_done"
    assert all(e["event"] == "prediction" for e in events[:-1])
    assert set(events[-1]["data"]["predictions"]) == {str(i) for i in range(tagging.BATCH_SIZE + 2)}
    assert events[-1]["data"]["total_tokens"] == 0


def test_summarize_dataset_samples_rows() -> None:
    """The summary carries the row count and a bounded sample."""
    data = [{"id": i, "text": f"row {i}"} for i in range(100)]
    summary = summarize_dataset(_BINARY, ["text"], data)
    assert '"row_count": 100' in summary
    assert "row 0" in summary


def test_summarize_dataset_marks_unselected_columns_excluded() -> None:
    """Columns outside the input selection surface as excluded, not available."""
    data = [{"id": 1, "text": "What is 2+2?", "question": "What is 2+2?", "answer": "4"}]
    config = {"mode": "freetext", "inputColumns": ["question"], "modeProvisional": True}
    summary = json.loads(summarize_dataset(config, ["question", "answer"], data))
    assert summary["input_columns"] == ["question"]
    assert summary["excluded_columns"] == ["answer"]
    assert "all_columns" not in summary


def test_estimate_scales_with_rows_and_handles_empty() -> None:
    """More rows require more tokens; zero rows require none."""
    rows = [{"id": i, "text": "x" * 400} for i in range(50)]
    small = estimate_tokens_for_rows("instructions", rows[:10])
    large = estimate_tokens_for_rows("instructions", rows)
    assert small["rows"] == 10
    assert large["estimated_input_tokens"] >= small["estimated_input_tokens"] >= 0
    assert large["estimated_output_tokens"] >= small["estimated_output_tokens"] >= 0
    assert "model" not in large
    empty = estimate_tokens_for_rows("instructions", [])
    assert empty == {"rows": 0, "estimated_input_tokens": 0, "estimated_output_tokens": 0}


def test_effective_task_config_ignores_client_model() -> None:
    """A ``model``/``modelParams`` pair written onto ``assist`` never reaches the config."""
    merged = effective_task_config(
        _BINARY, {"model": "openai/gpt-test", "modelParams": {"temperature": 0.2}}
    )
    assert "model" not in merged
    assert "modelParams" not in merged


def test_build_assist_lm_runs_on_configured_model(monkeypatch) -> None:
    """The LM always builds on the operator-configured tagging model."""
    captured: list[tuple[str, float | None, int | None]] = []

    def fake_build(config, disable_cache):
        """Record the requested model config instead of building an LM."""
        captured.append((config.name, config.temperature, config.max_tokens))
        return "lm"

    monkeypatch.setattr(tagging, "build_language_model", fake_build)
    monkeypatch.setattr(tagging, "apply_model_reasoning_config", lambda config: config)
    tagging._build_assist_lm()
    tagging._build_assist_lm(None)
    assert captured == [(assist_model_name(), None, None)] * 2


def test_build_assist_lm_merges_lm_extra_body(monkeypatch) -> None:
    """Extra request-body fields land in the LM config."""
    captured: list[dict] = []

    def fake_build(config, disable_cache):
        """Record the config extras instead of building an LM."""
        captured.append(config.extra)
        return "lm"

    monkeypatch.setattr(tagging, "build_language_model", fake_build)
    monkeypatch.setattr(tagging, "apply_model_reasoning_config", lambda config: config)
    tagging._build_assist_lm(
        lm_extra_body={"plugins": [{"id": "auto-router", "cost_quality_tradeoff": 5}]}
    )
    assert captured == [
        {"extra_body": {"plugins": [{"id": "auto-router", "cost_quality_tradeoff": 5}]}}
    ]


def test_normalize_synthetic_rows_projects_onto_given_columns() -> None:
    """Given columns win: extras are dropped, gaps become empty strings, blanks vanish."""
    parsed = [
        {"text": "Card declined twice", "channel": "chat", "junk": 1},
        {"text": "  ", "channel": ""},
        {"channel": "email", "extra": {"a": 1}},
        "not an object",
    ]
    columns, rows = _normalize_synthetic_rows(parsed, ["text", "channel"])
    assert columns == ["text", "channel"]
    assert rows == [
        {"text": "Card declined twice", "channel": "chat"},
        {"text": "", "channel": "email"},
    ]


def test_normalize_synthetic_rows_lets_first_object_settle_columns() -> None:
    """Without columns the first usable object decides them; nested cells are JSON."""
    parsed = [{"review": "Great", "tags": ["a", "b"]}, {"review": "Bad", "other": "x"}]
    columns, rows = _normalize_synthetic_rows(parsed, [])
    assert columns == ["review", "tags"]
    assert rows == [{"review": "Great", "tags": '["a", "b"]'}, {"review": "Bad", "tags": ""}]
    assert _normalize_synthetic_rows("nope", []) == ([], [])


def test_synthesize_rows_slices_dedupes_and_caps(monkeypatch) -> None:
    """The first slice settles columns, later slices reuse them, repeats and overflow are dropped."""
    calls: list[tuple[list[str], int, int, int]] = []

    def fake_batch(lm, brief, columns, count, part, parts):
        """Record the slice request and return predictable rows on the settled columns."""
        calls.append((list(columns), count, part, parts))
        cols = columns or ["text"]
        rows = [{c: f"{c}-{part}-{i}" for c in cols} for i in range(count)]
        rows.append(dict(rows[0]))
        return cols, rows

    monkeypatch.setattr(tagging, "_synthesize_batch", fake_batch)
    monkeypatch.setattr(tagging, "_build_assist_lm", lambda *a, **k: SimpleNamespace())
    sink: list = []
    columns, rows = synthesize_rows("support tickets", [], 55, usage_sink=sink)
    assert columns == ["text"]
    assert len(rows) == 55
    assert len({r["text"] for r in rows}) == 55
    assert len(sink) == 1
    assert calls[0] == ([], 25, 1, 3)
    assert sorted(calls[1:]) == [(["text"], 5, 3, 3), (["text"], 25, 2, 3)]


def test_synthesize_rows_raises_when_nothing_usable(monkeypatch) -> None:
    """A model that writes no rows surfaces as an error instead of an empty dataset."""
    monkeypatch.setattr(tagging, "_synthesize_batch", lambda *a, **k: ([], []))
    monkeypatch.setattr(tagging, "_build_assist_lm", lambda *a, **k: SimpleNamespace())
    try:
        synthesize_rows("anything", [], 10)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")
