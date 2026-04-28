"""Tests for the recommendation ingest + search pipeline.

These tests stub out the embedder, summariser, and Session so the pure
Python logic (text building, SQL shape, metadata extraction, upsert
branches) is covered without a live pgvector instance.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.service_gateway.recommendations import core as recs


class _FakeEmbedder:
    """Minimal embedder double used by the tests.

    ``encode`` returns a small deterministic vector so call-count and
    argument shape can be asserted without pulling in torch.
    """

    def __init__(self, *, available: bool = True, vector: list[float] | None = None) -> None:
        """Configure availability and the canned vector returned by ``encode``."""
        self._available = available
        self._vector = vector if vector is not None else [0.1, 0.2, 0.3]
        self.encode_calls: list[str] = []

    def available(self) -> bool:
        """Return whether this embedder is configured as available."""
        return self._available

    def encode(self, text: str) -> list[float] | None:
        """Record the call and return the canned vector (or ``None`` for blanks)."""
        self.encode_calls.append(text)
        if not text or not text.strip():
            return None
        return list(self._vector)


class _FakeJobStore:
    """Carries just the attributes ``embed_finished_job`` and ``search_similar`` touch."""

    def __init__(self, jobs: dict[str, dict[str, Any]] | None = None) -> None:
        """Seed the in-memory job map and an opaque engine handle."""
        self._jobs = jobs or {}
        self.engine = MagicMock(name="engine")

    def get_job(self, optimization_id: str) -> dict[str, Any]:
        """Return the seeded job dict, raising ``KeyError`` if unknown."""
        if optimization_id not in self._jobs:
            raise KeyError(optimization_id)
        return self._jobs[optimization_id]


def _success_job(**overrides: Any) -> dict[str, Any]:
    """Build a minimal successful run-job dict with optional overrides."""
    job = {
        "status": "success",
        "payload_overview": {
            "username": "alice",
            "model_name": "openai/gpt-4o-mini",
            "optimization_type": "run",
        },
        "payload": {
            "signature_code": "class S(dspy.Signature):\n    q = dspy.InputField()\n    a = dspy.OutputField()",
            "metric_code": "def metric(gold, pred):\n    return gold.a == pred.a",
            "column_mapping": {"inputs": {"q": "question"}, "outputs": {"a": "answer"}},
            "dataset": [{"question": "hi", "answer": "hello"}],
        },
        "result": None,
    }
    job.update(overrides)
    return job


def test_build_code_text_joins_signature_and_metric() -> None:
    """``_build_code_text`` emits headed sections for signature and metric."""
    out = recs._build_code_text("sig", "metric")
    assert "# Signature" in out
    assert "sig" in out
    assert "# Metric" in out
    assert "metric" in out


def test_build_code_text_handles_missing_parts() -> None:
    """Empty/None inputs are skipped — no stray section headers are emitted."""
    # Empty/None inputs must be skipped — otherwise a stray "# Signature" header
    # leaks into embeddings and degrades recall.
    assert recs._build_code_text(None, None) == ""
    assert recs._build_code_text("sig", None).strip().startswith("# Signature")
    assert "# Metric" not in recs._build_code_text("sig", None)


def test_build_code_text_strips_whitespace_only() -> None:
    """Whitespace-only sections collapse to an empty string."""
    assert recs._build_code_text("   ", "\n\n") == ""


def test_build_schema_text_annotates_roles() -> None:
    """``_build_schema_text`` annotates each dataset column with its mapping role."""
    dataset = [{"question": "hi", "answer": "hello", "extra": 1}]
    mapping = {"inputs": {"q": "question"}, "outputs": {"a": "answer"}}
    out = recs._build_schema_text(dataset, mapping)
    assert "question (input" in out
    assert "answer (output" in out
    assert "extra (ignore" in out


def test_build_schema_text_empty_dataset_returns_empty() -> None:
    """An empty or missing dataset produces an empty schema text."""
    assert recs._build_schema_text([], {"inputs": {}, "outputs": {}}) == ""
    assert recs._build_schema_text(None, None) == ""


def test_extract_metadata_run_uses_overview_model() -> None:
    """For a ``run`` job the winning model comes from the overview, rank is 1."""
    # For a `run` job the winner comes from overview.model_name (not from result.best_pair).
    job = _success_job()
    model, rank, job_type = recs._extract_metadata(job)
    assert model == "openai/gpt-4o-mini"
    assert rank == 1
    assert job_type == "run"


def test_extract_metadata_grid_search_reads_best_pair() -> None:
    """For grid-search the winning model comes from ``result.best_pair``."""
    # Grid-search winner is pulled from result.best_pair.generation_model (overview is empty for grids).
    job = {
        "payload_overview": {"optimization_type": "grid_search"},
        "result": {"best_pair": {"generation_model": "anthropic/claude-3-5-sonnet"}},
    }
    model, rank, job_type = recs._extract_metadata(job)
    assert model == "anthropic/claude-3-5-sonnet"
    assert rank == 1
    assert job_type == "grid_search"


def test_extract_metadata_grid_search_without_best_pair() -> None:
    """A grid-search job missing ``best_pair`` returns ``(None, None, 'grid_search')``."""
    job = {"payload_overview": {"optimization_type": "grid_search"}, "result": {}}
    model, rank, job_type = recs._extract_metadata(job)
    assert model is None
    assert rank is None
    assert job_type == "grid_search"


def test_encode_vector_literal_formats_for_pgvector() -> None:
    """Vector literals are formatted as ``[x,y,z]`` with 6 decimals per component."""
    # pgvector literal contract: [x,y,z] with exactly 6 decimals per component.
    assert recs._encode_vector_literal([0.1, 0.25, 0.333333]) == "[0.100000,0.250000,0.333333]"


def test_encode_vector_literal_none_is_none() -> None:
    """``None`` round-trips to ``None`` instead of a literal string."""
    assert recs._encode_vector_literal(None) is None


def test_weighted_fusion_sql_all_three_aspects() -> None:
    """SQL with all three aspects includes the canonical 0.5/0.3/0.2 weights."""
    sql = recs._weighted_fusion_sql(has_summary=True, has_code=True, has_schema=True, filter_type=False)
    assert "embedding_summary <=> CAST(:q_summary AS vector)" in sql
    assert "embedding_code <=> CAST(:q_code AS vector)" in sql
    assert "embedding_schema <=> CAST(:q_schema AS vector)" in sql
    assert "0.5" in sql
    assert "0.3" in sql
    assert "0.2" in sql
    assert "ORDER BY score DESC" in sql
    assert "LIMIT :top_k" in sql
    assert "optimization_type = :filter_type" not in sql
    assert "is_recommendable = TRUE" in sql


def test_weighted_fusion_sql_selects_apply_config_columns() -> None:
    """The fusion SQL selects every column the apply-config UI consumes."""
    sql = recs._weighted_fusion_sql(has_summary=True, has_code=True, has_schema=True, filter_type=False)
    for col in (
        "baseline_metric",
        "optimized_metric",
        "summary_text",
        "signature_code",
        "metric_name",
        "optimizer_name",
        "optimizer_kwargs",
        "module_name",
        "task_name",
    ):
        assert col in sql


def test_weighted_fusion_sql_only_code() -> None:
    """SQL with only the code aspect references only ``:q_code``."""
    sql = recs._weighted_fusion_sql(has_summary=False, has_code=True, has_schema=False, filter_type=False)
    assert ":q_code" in sql
    assert ":q_summary" not in sql
    assert ":q_schema" not in sql


def test_weighted_fusion_sql_with_type_filter() -> None:
    """``filter_type`` adds a ``WHERE optimization_type`` clause to the SQL."""
    sql = recs._weighted_fusion_sql(has_summary=True, has_code=False, has_schema=False, filter_type=True)
    assert "optimization_type = :filter_type" in sql


def test_build_schema_from_query_schema_columns_shape() -> None:
    """A typed columns spec renders ``name (role, dtype)`` lines."""
    schema = {
        "columns": [
            {"name": "question", "role": "input", "dtype": "str"},
            {"name": "answer", "role": "output", "dtype": "str"},
        ]
    }
    out = recs._build_schema_from_query_schema(schema)
    assert "question (input, str)" in out
    assert "answer (output, str)" in out


def test_build_schema_from_query_schema_fallback_json() -> None:
    """An unrecognised schema falls back to JSON serialization."""
    out = recs._build_schema_from_query_schema({"foo": "bar"})
    assert '"foo"' in out
    assert '"bar"' in out


def test_build_schema_from_query_schema_none_empty() -> None:
    """``None`` and ``{}`` produce an empty schema string."""
    assert recs._build_schema_from_query_schema(None) == ""
    assert recs._build_schema_from_query_schema({}) == ""


@pytest.fixture
def fake_embedder() -> _FakeEmbedder:
    """Provide a fresh ``_FakeEmbedder`` for each test."""
    return _FakeEmbedder()


def _patch_pipeline(fake_embedder: _FakeEmbedder, summary_text: str = "A summary.") -> tuple[Any, Any]:
    """Build matching patches for ``get_embedder`` and ``summarize_task``."""
    return (
        patch.object(recs, "get_embedder", return_value=fake_embedder),
        patch.object(recs, "summarize_task", return_value=summary_text),
    )


def test_embed_finished_job_inserts_new_row(fake_embedder: _FakeEmbedder) -> None:
    """A new optimization id triggers an INSERT with all three embeddings."""
    store = _FakeJobStore({"job-1": _success_job()})
    session_mock = MagicMock()
    session_mock.query.return_value.filter.return_value.first.return_value = None
    session_cm = MagicMock()
    session_cm.__enter__.return_value = session_mock
    session_cm.__exit__.return_value = False

    get_emb, summ = _patch_pipeline(fake_embedder, "what this task does")
    with get_emb, summ, patch.object(recs, "Session", return_value=session_cm):
        recs.embed_finished_job("job-1", job_store=store)

    session_mock.add.assert_called_once()
    added = session_mock.add.call_args[0][0]
    assert added.optimization_id == "job-1"
    assert added.user_id == "alice"
    assert added.optimization_type == "run"
    assert added.winning_model == "openai/gpt-4o-mini"
    assert added.winning_rank == 1
    assert added.embedding_summary == [0.1, 0.2, 0.3]
    assert added.embedding_code == [0.1, 0.2, 0.3]
    assert added.embedding_schema == [0.1, 0.2, 0.3]
    # Baseline job has no scores → quality gate fails by default.
    assert added.is_recommendable is False
    assert added.baseline_metric is None
    assert added.optimized_metric is None
    session_mock.commit.assert_called_once()


def test_embed_finished_job_marks_recommendable_when_quality_clears_gate(
    fake_embedder: _FakeEmbedder,
) -> None:
    """A strong score lift sets ``is_recommendable=True`` and persists apply-config fields."""
    job = _success_job(
        latest_metrics={"baseline_test_metric": 52.0, "optimized_test_metric": 78.5},
    )
    job["payload"].update(
        {
            "optimizer_name": "gepa",
            "optimizer_kwargs": {"auto": "light", "reflection_minibatch_size": 3},
            "module_name": "dspy.ChainOfThought",
            "metric_name": "accuracy",
        }
    )
    job["payload_overview"]["name"] = "tickets-q4"

    store = _FakeJobStore({"job-1": job})
    session_mock = MagicMock()
    session_mock.query.return_value.filter.return_value.first.return_value = None
    session_cm = MagicMock()
    session_cm.__enter__.return_value = session_mock
    session_cm.__exit__.return_value = False

    get_emb, summ = _patch_pipeline(fake_embedder, "summary")
    with get_emb, summ, patch.object(recs, "Session", return_value=session_cm):
        recs.embed_finished_job("job-1", job_store=store)

    added = session_mock.add.call_args[0][0]
    assert added.is_recommendable is True
    assert added.baseline_metric == 52.0
    assert added.optimized_metric == 78.5
    assert added.optimizer_name == "gepa"
    assert added.optimizer_kwargs == {"auto": "light", "reflection_minibatch_size": 3}
    assert added.module_name == "dspy.ChainOfThought"
    assert added.metric_name == "accuracy"
    assert added.task_name == "tickets-q4"


def test_embed_finished_job_low_absolute_score_not_recommendable(
    fake_embedder: _FakeEmbedder,
) -> None:
    """An optimized score below the absolute floor never sets ``is_recommendable``."""
    # Quality gate: an optimized score below the absolute floor must NEVER earn the
    # recommendable flag — even when the relative lift looks large.
    job = _success_job(
        latest_metrics={"baseline_test_metric": 5.0, "optimized_test_metric": 40.0},
    )
    store = _FakeJobStore({"job-1": job})
    session_mock = MagicMock()
    session_mock.query.return_value.filter.return_value.first.return_value = None
    session_cm = MagicMock()
    session_cm.__enter__.return_value = session_mock
    session_cm.__exit__.return_value = False

    get_emb, summ = _patch_pipeline(fake_embedder, "summary")
    with get_emb, summ, patch.object(recs, "Session", return_value=session_cm):
        recs.embed_finished_job("job-1", job_store=store)

    added = session_mock.add.call_args[0][0]
    # 40 < default floor of 50
    assert added.is_recommendable is False
    assert added.baseline_metric == 5.0
    assert added.optimized_metric == 40.0


def test_embed_finished_job_updates_existing_row(fake_embedder: _FakeEmbedder) -> None:
    """Re-running ingest on the same id updates the existing row instead of inserting."""
    # Idempotency invariant: re-running ingest on the same optimization_id must
    # update the existing row, not insert a duplicate.
    store = _FakeJobStore({"job-1": _success_job()})
    existing = MagicMock()
    session_mock = MagicMock()
    session_mock.query.return_value.filter.return_value.first.return_value = existing
    session_cm = MagicMock()
    session_cm.__enter__.return_value = session_mock
    session_cm.__exit__.return_value = False

    get_emb, summ = _patch_pipeline(fake_embedder)
    with get_emb, summ, patch.object(recs, "Session", return_value=session_cm):
        recs.embed_finished_job("job-1", job_store=store)

    session_mock.add.assert_not_called()
    assert existing.user_id == "alice"
    assert existing.optimization_type == "run"
    assert existing.winning_model == "openai/gpt-4o-mini"
    assert existing.embedding_summary == [0.1, 0.2, 0.3]
    session_mock.commit.assert_called_once()


def test_embed_finished_job_skips_when_disabled(fake_embedder: _FakeEmbedder) -> None:
    """The ``recommendations_enabled=False`` setting short-circuits the entire pipeline."""
    store = _FakeJobStore({"job-1": _success_job()})
    with (
        patch.object(recs.settings, "recommendations_enabled", False),
        patch.object(recs, "get_embedder") as get_emb,
        patch.object(recs, "Session") as sess,
    ):
        recs.embed_finished_job("job-1", job_store=store)

    get_emb.assert_not_called()
    sess.assert_not_called()


def test_embed_finished_job_skips_when_embedder_unavailable() -> None:
    """An unavailable embedder skips the DB session entirely."""
    store = _FakeJobStore({"job-1": _success_job()})
    unavailable = _FakeEmbedder(available=False)
    with (
        patch.object(recs, "get_embedder", return_value=unavailable),
        patch.object(recs, "Session") as sess,
    ):
        recs.embed_finished_job("job-1", job_store=store)

    sess.assert_not_called()


def test_embed_finished_job_skips_non_success_jobs(fake_embedder: _FakeEmbedder) -> None:
    """A non-success status is ignored with no DB writes."""
    store = _FakeJobStore({"job-1": _success_job(status="failed")})
    get_emb, summ = _patch_pipeline(fake_embedder)
    with get_emb, summ, patch.object(recs, "Session") as sess:
        recs.embed_finished_job("job-1", job_store=store)

    sess.assert_not_called()


def test_embed_finished_job_missing_job_is_silent(fake_embedder: _FakeEmbedder) -> None:
    """An unknown optimization id logs and returns silently rather than raising."""
    # Daemon-thread contract: unknown optimization_id must log and return — never raise.
    store = _FakeJobStore({})
    get_emb, summ = _patch_pipeline(fake_embedder)
    with get_emb, summ, patch.object(recs, "Session") as sess:
        recs.embed_finished_job("missing", job_store=store)

    sess.assert_not_called()


def test_embed_finished_job_skips_when_all_text_empty() -> None:
    """Jobs with no embeddable text bypass DB writes entirely."""
    empty_job = {
        "status": "success",
        "payload_overview": {"username": "alice", "optimization_type": "run"},
        "payload": {"signature_code": "", "metric_code": "", "column_mapping": {}, "dataset": []},
    }
    store = _FakeJobStore({"job-1": empty_job})
    empty_embedder = _FakeEmbedder(vector=[0.1, 0.2, 0.3])
    with (
        patch.object(recs, "get_embedder", return_value=empty_embedder),
        patch.object(recs, "summarize_task", return_value=""),
        patch.object(recs, "Session") as sess,
    ):
        recs.embed_finished_job("job-1", job_store=store)

    sess.assert_not_called()


def test_embed_finished_job_swallows_commit_errors(fake_embedder: _FakeEmbedder) -> None:
    """A DB failure during commit is logged, never propagated."""
    # Daemon-thread contract: DB failure during upsert is logged, never propagated.
    store = _FakeJobStore({"job-1": _success_job()})
    session_mock = MagicMock()
    session_mock.query.return_value.filter.return_value.first.return_value = None
    session_mock.commit.side_effect = RuntimeError("connection lost")
    session_cm = MagicMock()
    session_cm.__enter__.return_value = session_mock
    session_cm.__exit__.return_value = False

    get_emb, summ = _patch_pipeline(fake_embedder)
    with get_emb, summ, patch.object(recs, "Session", return_value=session_cm):
        recs.embed_finished_job("job-1", job_store=store)


def _session_returning(rows: list[dict[str, Any]]) -> tuple[MagicMock, MagicMock]:
    """Build a Session context-manager mock whose ``execute`` returns ``rows``."""
    session_mock = MagicMock()
    exec_result = MagicMock()
    exec_result.mappings.return_value.all.return_value = rows
    session_mock.execute.return_value = exec_result
    session_cm = MagicMock()
    session_cm.__enter__.return_value = session_mock
    session_cm.__exit__.return_value = False
    return session_cm, session_mock


def test_search_similar_returns_parsed_rows(fake_embedder: _FakeEmbedder) -> None:
    """``search_similar`` parses SQL rows into stable result dicts and emits embedded params."""
    store = _FakeJobStore()
    rows = [
        {
            "optimization_id": "job-A",
            "optimization_type": "run",
            "winning_model": "openai/gpt-4o-mini",
            "winning_rank": 1,
            "score": 0.87,
            "baseline_metric": 52.3,
            "optimized_metric": 78.9,
            "summary_text": "qa on support tickets",
            "signature_code": "class S(dspy.Signature): ...",
            "metric_name": "accuracy",
            "optimizer_name": "gepa",
            "optimizer_kwargs": {"auto": "light", "reflection_minibatch_size": 3},
            "module_name": "dspy.ChainOfThought",
            "task_name": "tickets-q4",
        },
        {
            "optimization_id": "job-B",
            "optimization_type": "run",
            "winning_model": "anthropic/claude-3-5-sonnet",
            "winning_rank": 1,
            "score": 0.72,
            "baseline_metric": None,
            "optimized_metric": None,
            "summary_text": None,
            "signature_code": None,
            "metric_name": None,
            "optimizer_name": None,
            "optimizer_kwargs": None,
            "module_name": None,
            "task_name": None,
        },
    ]
    session_cm, session_mock = _session_returning(rows)
    get_emb, summ = _patch_pipeline(fake_embedder, "query summary")
    with get_emb, summ, patch.object(recs, "Session", return_value=session_cm):
        out = recs.search_similar(
            job_store=store,
            signature_code="sig",
            metric_code="metric",
            dataset_schema={"columns": [{"name": "q", "role": "input", "dtype": "str"}]},
            optimization_type="run",
            user_id="alice",
            top_k=5,
        )

    assert len(out) == 2
    assert out[0]["optimization_id"] == "job-A"
    assert out[0]["score"] == 0.87
    assert out[0]["baseline_metric"] == 52.3
    assert out[0]["optimized_metric"] == 78.9
    assert out[0]["optimizer_name"] == "gepa"
    assert out[0]["optimizer_kwargs"] == {"auto": "light", "reflection_minibatch_size": 3}
    assert out[0]["module_name"] == "dspy.ChainOfThought"
    assert out[0]["metric_name"] == "accuracy"
    assert out[0]["task_name"] == "tickets-q4"
    # Null SQL columns round-trip to None, never raise.
    assert out[1]["optimization_id"] == "job-B"
    assert out[1]["baseline_metric"] is None
    assert out[1]["optimizer_kwargs"] == {}
    assert out[1]["optimizer_name"] is None

    params = session_mock.execute.call_args[0][1]
    assert params["top_k"] == 5
    assert params["filter_type"] == "run"
    assert params["q_code"].startswith("[")
    assert params["q_schema"].startswith("[")
    assert params["q_summary"].startswith("[")


def test_search_similar_returns_empty_when_disabled(fake_embedder: _FakeEmbedder) -> None:
    """``search_similar`` returns ``[]`` when the feature flag is off."""
    with patch.object(recs.settings, "recommendations_enabled", False):
        out = recs.search_similar(
            job_store=_FakeJobStore(),
            signature_code="sig",
            metric_code=None,
            dataset_schema=None,
            optimization_type=None,
            user_id=None,
            top_k=5,
        )
    assert out == []


def test_search_similar_returns_empty_when_embedder_unavailable() -> None:
    """``search_similar`` returns ``[]`` when the embedder is unavailable."""
    unavailable = _FakeEmbedder(available=False)
    with (
        patch.object(recs, "get_embedder", return_value=unavailable),
        patch.object(recs, "Session") as sess,
    ):
        out = recs.search_similar(
            job_store=_FakeJobStore(),
            signature_code="sig",
            metric_code=None,
            dataset_schema=None,
            optimization_type=None,
            user_id=None,
            top_k=5,
        )
    assert out == []
    sess.assert_not_called()


def test_search_similar_returns_empty_when_no_text_to_embed() -> None:
    """A query with no embeddable text returns ``[]`` and never opens a session."""
    fake_embedder = _FakeEmbedder()
    with (
        patch.object(recs, "get_embedder", return_value=fake_embedder),
        patch.object(recs, "summarize_task", return_value=""),
        patch.object(recs, "Session") as sess,
    ):
        out = recs.search_similar(
            job_store=_FakeJobStore(),
            signature_code=None,
            metric_code=None,
            dataset_schema=None,
            optimization_type=None,
            user_id=None,
            top_k=5,
        )
    assert out == []
    sess.assert_not_called()


def test_search_similar_swallows_sql_errors(fake_embedder: _FakeEmbedder) -> None:
    """A Postgres error degrades to ``[]`` rather than surfacing as a 500."""
    # Postgres hiccup must degrade to an empty result rather than surface a 500.
    session_mock = MagicMock()
    session_mock.execute.side_effect = RuntimeError("pgvector extension missing")
    session_cm = MagicMock()
    session_cm.__enter__.return_value = session_mock
    session_cm.__exit__.return_value = False

    get_emb, summ = _patch_pipeline(fake_embedder)
    with get_emb, summ, patch.object(recs, "Session", return_value=session_cm):
        out = recs.search_similar(
            job_store=_FakeJobStore(),
            signature_code="sig",
            metric_code=None,
            dataset_schema=None,
            optimization_type=None,
            user_id=None,
            top_k=5,
        )
    assert out == []


def test_search_similar_omits_type_filter_when_not_given(fake_embedder: _FakeEmbedder) -> None:
    """Without ``optimization_type`` the SQL params omit ``filter_type``."""
    session_cm, session_mock = _session_returning([])
    get_emb, summ = _patch_pipeline(fake_embedder)
    with get_emb, summ, patch.object(recs, "Session", return_value=session_cm):
        recs.search_similar(
            job_store=_FakeJobStore(),
            signature_code="sig",
            metric_code="metric",
            dataset_schema=None,
            optimization_type=None,
            user_id=None,
            top_k=3,
        )
    params = session_mock.execute.call_args[0][1]
    assert "filter_type" not in params
    assert params["top_k"] == 3


def test_extract_scores_run_reads_latest_metrics() -> None:
    """For ``run`` jobs scores come from ``latest_metrics``."""
    job = {
        "payload_overview": {"optimization_type": "run"},
        "latest_metrics": {"baseline_test_metric": 51.2, "optimized_test_metric": 74.9},
    }
    baseline, optimized = recs._extract_scores(job)
    assert baseline == 51.2
    assert optimized == 74.9


def test_extract_scores_grid_search_prefers_best_pair() -> None:
    """Grid-search scores come from ``result.best_pair`` and override top-level metrics."""
    # Grid search: the winner's scores live on result.best_pair and OVERRIDE top-level
    # metrics (which would otherwise reflect an arbitrary pair).
    job = {
        "payload_overview": {"optimization_type": "grid_search"},
        "latest_metrics": {"baseline_test_metric": 10.0, "optimized_test_metric": 20.0},
        "result": {
            "best_pair": {"baseline_test_metric": 55.0, "optimized_test_metric": 82.0},
        },
    }
    baseline, optimized = recs._extract_scores(job)
    assert baseline == 55.0
    assert optimized == 82.0


def test_extract_scores_handles_missing_metrics() -> None:
    """Jobs without metrics return ``(None, None)`` rather than raising."""
    assert recs._extract_scores({}) == (None, None)
    assert recs._extract_scores({"payload_overview": {"optimization_type": "run"}}) == (None, None)


def test_extract_scores_coerces_string_numbers() -> None:
    """Stringified floats from SQL/JSON are coerced to numeric scores."""
    # SQL/JSON often hands back stringified floats — coerce rather than drop them.
    job = {
        "payload_overview": {"optimization_type": "run"},
        "latest_metrics": {"baseline_test_metric": "50.5", "optimized_test_metric": "77.0"},
    }
    baseline, optimized = recs._extract_scores(job)
    assert baseline == 50.5
    assert optimized == 77.0


def test_extract_scores_returns_none_on_bad_string() -> None:
    """Non-numeric strings yield ``(None, None)``."""
    job = {
        "payload_overview": {"optimization_type": "run"},
        "latest_metrics": {"baseline_test_metric": "abc", "optimized_test_metric": None},
    }
    assert recs._extract_scores(job) == (None, None)


def test_evaluate_quality_clears_gate_on_strong_run() -> None:
    """A strong score lift clears the quality gate."""
    assert recs._evaluate_quality(52.0, 78.5) is True


def test_evaluate_quality_rejects_below_absolute_floor() -> None:
    """An optimized score below the absolute floor fails the gate."""
    assert recs._evaluate_quality(10.0, 45.0) is False  # 45 < default 50


def test_evaluate_quality_rejects_tiny_lift() -> None:
    """A lift below the required (absolute or relative) threshold fails."""
    # Default min_gain_absolute=5.0, min_gain_relative=0.10 → required=max(5, 60*0.10)=6.0
    assert recs._evaluate_quality(60.0, 64.0) is False
    assert recs._evaluate_quality(60.0, 67.0) is True


def test_evaluate_quality_rejects_non_improvement() -> None:
    """A flat or negative lift fails the gate."""
    assert recs._evaluate_quality(70.0, 70.0) is False
    assert recs._evaluate_quality(70.0, 65.0) is False


def test_evaluate_quality_handles_missing() -> None:
    """Missing scores fail the gate without raising."""
    assert recs._evaluate_quality(None, 80.0) is False
    assert recs._evaluate_quality(80.0, None) is False
    assert recs._evaluate_quality(None, None) is False


def test_extract_applyable_config_pulls_from_payload() -> None:
    """Apply-config fields are pulled from the payload, with task name from overview."""
    job = {
        "payload": {
            "optimizer_name": "gepa",
            "optimizer_kwargs": {"auto": "light"},
            "module_name": "dspy.ChainOfThought",
            "metric_name": "accuracy",
            "name": "fallback-name",
        },
        "payload_overview": {"name": "tickets-q4"},
    }
    cfg = recs._extract_applyable_config(job)
    assert cfg == {
        "optimizer_name": "gepa",
        "optimizer_kwargs": {"auto": "light"},
        "module_name": "dspy.ChainOfThought",
        "metric_name": "accuracy",
        "task_name": "tickets-q4",
    }


def test_extract_applyable_config_defaults_to_empty() -> None:
    """An empty job produces all-None apply-config defaults."""
    cfg = recs._extract_applyable_config({})
    assert cfg["optimizer_name"] is None
    assert cfg["optimizer_kwargs"] == {}
    assert cfg["module_name"] is None
    assert cfg["metric_name"] is None
    assert cfg["task_name"] is None


def test_as_float_coercion() -> None:
    """``_as_float`` coerces ints, decimals, and numeric strings; rejects others."""
    from decimal import Decimal

    assert recs._as_float(None) is None
    assert recs._as_float(5) == 5.0
    assert recs._as_float(Decimal("3.14")) == 3.14
    assert recs._as_float("1.5") == 1.5
    assert recs._as_float("nope") is None
    assert recs._as_float(object()) is None
