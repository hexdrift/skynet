"""End-to-end smoke test for the PER-11 recommendation pipeline.

Drives the real ingest + search path against a live pgvector database:

1. Bootstraps schema (CREATE EXTENSION + create_all + HNSW indexes).
2. Seeds two finished-success jobs — one about classifying customer
   support tickets, one about translating English to French.
3. Runs ``embed_finished_job`` on each (calls the real Jina encoder).
4. Queries ``job_embeddings`` to confirm rows and vector dims.
5. Calls ``search_similar`` with a query close to the support-ticket
   task and asserts that job ranks first.

Expects pgvector Postgres on ``postgresql://skynet:skynet@127.0.0.1:5433/skynet``.
Summariser falls back to the heuristic path unless an OPENAI key is loaded.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")
os.environ["REMOTE_DB_URL"] = "postgresql://skynet:skynet@127.0.0.1:5433/skynet"

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from core.config import settings  # noqa: E402
from core.service_gateway.embeddings import get_embedder  # noqa: E402
from core.service_gateway.recommendations import (  # noqa: E402
    embed_finished_job,
    search_similar,
)
from core.storage.remote import RemoteDBJobStore  # noqa: E402


TICKET_JOB = {
    "status": "success",
    "payload_overview": {
        "username": "alice",
        "model_name": "openai/gpt-4o-mini",
        "optimization_type": "run",
    },
    "payload": {
        "signature_code": (
            "class ClassifyTicket(dspy.Signature):\n"
            "    '''Classify a customer-support ticket by urgency.'''\n"
            "    ticket_text = dspy.InputField()\n"
            "    urgency = dspy.OutputField(desc='one of low, medium, high')"
        ),
        "metric_code": (
            "def metric(gold, pred):\n"
            "    return gold.urgency == pred.urgency"
        ),
        "column_mapping": {
            "inputs": {"ticket_text": "body"},
            "outputs": {"urgency": "label"},
        },
        "dataset": [
            {"body": "My server is down, total outage!", "label": "high"},
            {"body": "Small typo on the about page.", "label": "low"},
            {"body": "Billing question about last invoice.", "label": "medium"},
        ],
    },
}

TRANSLATE_JOB = {
    "status": "success",
    "payload_overview": {
        "username": "bob",
        "model_name": "anthropic/claude-3-5-sonnet",
        "optimization_type": "run",
    },
    "payload": {
        "signature_code": (
            "class Translate(dspy.Signature):\n"
            "    '''Translate English to French.'''\n"
            "    en = dspy.InputField()\n"
            "    fr = dspy.OutputField()"
        ),
        "metric_code": (
            "def metric(gold, pred):\n"
            "    return gold.fr.lower() == pred.fr.lower()"
        ),
        "column_mapping": {
            "inputs": {"en": "source"},
            "outputs": {"fr": "target"},
        },
        "dataset": [
            {"source": "Hello, world.", "target": "Bonjour le monde."},
            {"source": "Good morning.", "target": "Bonjour."},
        ],
    },
}


def log(msg: str) -> None:
    """Print a prefixed status line."""
    print(f"[e2e] {msg}")


def seed_job(store: RemoteDBJobStore, oid: str, job: dict) -> None:
    """Insert a pre-finished success job directly via the store."""
    store.create_job(oid)
    store.update_job(
        oid,
        status=job["status"],
        payload=job["payload"],
        payload_overview=job["payload_overview"],
        result=job.get("result"),
    )


def dump_embedding_row(store: RemoteDBJobStore, oid: str) -> dict:
    """Fetch raw counts + dims for the embedding row."""
    sql = text(
        """
        SELECT optimization_id,
               user_id,
               optimization_type,
               winning_model,
               winning_rank,
               array_length(embedding_summary::real[], 1) AS summary_dim,
               array_length(embedding_code::real[], 1) AS code_dim,
               array_length(embedding_schema::real[], 1) AS schema_dim
        FROM job_embeddings
        WHERE optimization_id = :oid
        """
    )
    with Session(store.engine) as session:
        row = session.execute(sql, {"oid": oid}).mappings().first()
    return dict(row) if row else {}


def main() -> int:
    """Run the full ingest + search smoke test."""
    db_url = settings.remote_db_url.get_secret_value() if settings.remote_db_url else None
    assert db_url, "REMOTE_DB_URL must be set"
    log(f"REMOTE_DB_URL = {db_url}")
    log(f"recommendations_enabled = {settings.recommendations_enabled}")
    log(f"embedding_model = {settings.recommendations_embedding_model}")
    log(f"embedding_dim = {settings.recommendations_embedding_dim}")

    log("Connecting to Postgres + bootstrapping schema…")
    store = RemoteDBJobStore(db_url=db_url)

    log("Clearing any previous smoke-test rows…")
    with Session(store.engine) as session:
        session.execute(
            text("DELETE FROM job_embeddings WHERE optimization_id IN ('e2e-ticket', 'e2e-translate')")
        )
        session.execute(
            text("DELETE FROM jobs WHERE optimization_id IN ('e2e-ticket', 'e2e-translate')")
        )
        session.commit()

    log("Warming up embedder (downloading Jina weights on first call)…")
    embedder = get_embedder()
    assert embedder.available(), "embedder failed to load — check sentence-transformers install"
    probe = embedder.encode("warmup")
    assert probe is not None and len(probe) == settings.recommendations_embedding_dim, probe
    log(f"Embedder OK — probe vector dim={len(probe)}")

    log("Seeding two finished-success jobs in `jobs`…")
    seed_job(store, "e2e-ticket", TICKET_JOB)
    seed_job(store, "e2e-translate", TRANSLATE_JOB)

    log("Running embed_finished_job for ticket classifier…")
    embed_finished_job("e2e-ticket", job_store=store)
    ticket_row = dump_embedding_row(store, "e2e-ticket")
    assert ticket_row, "no job_embeddings row written for e2e-ticket"
    log(f"  row: {ticket_row}")
    assert ticket_row["optimization_type"] == "run"
    assert ticket_row["winning_model"] == "openai/gpt-4o-mini"
    assert ticket_row["summary_dim"] == settings.recommendations_embedding_dim
    assert ticket_row["code_dim"] == settings.recommendations_embedding_dim
    assert ticket_row["schema_dim"] == settings.recommendations_embedding_dim

    log("Running embed_finished_job for translate…")
    embed_finished_job("e2e-translate", job_store=store)
    translate_row = dump_embedding_row(store, "e2e-translate")
    assert translate_row, "no job_embeddings row written for e2e-translate"
    log(f"  row: {translate_row}")

    log("Query 1: exact-match — same signature/metric/schema as ticket job")
    results = search_similar(
        job_store=store,
        signature_code=TICKET_JOB["payload"]["signature_code"],
        metric_code=TICKET_JOB["payload"]["metric_code"],
        dataset_schema={
            "columns": [
                {"name": "body", "role": "input", "dtype": "str"},
                {"name": "label", "role": "output", "dtype": "str"},
            ]
        },
        optimization_type="run",
        user_id=None,
        top_k=5,
    )
    log(f"  results: {results}")
    assert results, "expected at least one hit"
    assert results[0]["optimization_id"] == "e2e-ticket", (
        f"expected e2e-ticket on top, got {results[0]}"
    )
    assert results[0]["score"] > 0.7, f"exact-match score unexpectedly low: {results[0]['score']}"
    assert results[0]["score"] - results[1]["score"] > 0.1, (
        f"expected clear gap over runner-up, got {results[0]['score']} vs {results[1]['score']}"
    )

    log("Query 2: natural-language-ish — a *new* ticket-classification task, different wording")
    results2 = search_similar(
        job_store=store,
        signature_code=(
            "class TicketPriority(dspy.Signature):\n"
            "    '''Tag an incoming help-desk message with priority.'''\n"
            "    message = dspy.InputField()\n"
            "    priority = dspy.OutputField()"
        ),
        metric_code="def metric(gold, pred):\n    return gold.priority == pred.priority",
        dataset_schema={
            "columns": [
                {"name": "message", "role": "input", "dtype": "str"},
                {"name": "priority", "role": "output", "dtype": "str"},
            ]
        },
        optimization_type="run",
        user_id=None,
        top_k=5,
    )
    log(f"  results: {results2}")
    assert results2, "expected at least one hit for a similar-task query"
    ranked_ids = [r["optimization_id"] for r in results2]
    assert ranked_ids[0] == "e2e-ticket", (
        f"expected ticket to rank first for a near-duplicate task, got {ranked_ids}"
    )

    log("Query 3: filter by optimization_type='grid_search' — should return nothing")
    results3 = search_similar(
        job_store=store,
        signature_code=TICKET_JOB["payload"]["signature_code"],
        metric_code=TICKET_JOB["payload"]["metric_code"],
        dataset_schema=None,
        optimization_type="grid_search",
        user_id=None,
        top_k=5,
    )
    log(f"  results: {results3}")
    assert results3 == [], "filter by grid_search should exclude the two 'run' rows"

    log("Query 4: translate-specific query — translate job should rank first")
    results4 = search_similar(
        job_store=store,
        signature_code=(
            "class EnToEs(dspy.Signature):\n"
            "    '''Translate English to Spanish.'''\n"
            "    en = dspy.InputField()\n"
            "    es = dspy.OutputField()"
        ),
        metric_code="def metric(gold, pred):\n    return gold.es == pred.es",
        dataset_schema={
            "columns": [
                {"name": "source", "role": "input", "dtype": "str"},
                {"name": "target", "role": "output", "dtype": "str"},
            ]
        },
        optimization_type="run",
        user_id=None,
        top_k=5,
    )
    log(f"  results: {results4}")
    assert results4, "expected hits for translate-like query"
    assert results4[0]["optimization_id"] == "e2e-translate", (
        f"expected translate on top, got {results4[0]}"
    )

    log("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
