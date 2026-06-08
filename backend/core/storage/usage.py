"""Unified per-user storage accounting for the Skynet storage budget.

A single number — the sum of every table a user's data lands in — backs the
storage budget that is enforced at submit/save time and surfaced in the usage
meter. The two dominant contributors (a job's ``payload`` + ``result`` and the
dataset blobs) are read from precomputed indexed columns
(``jobs.stored_bytes`` / ``datasets.byte_size``); the smaller tail (logs,
progress events, agent chat messages, staged uploads, embeddings) is sized live
with a dialect-aware byte expression so the meter and the gate agree to the
byte.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import Engine, Text, cast, func, select
from sqlalchemy.orm import Session

from .models import (
    EMBEDDING_DIM,
    AgentConversationModel,
    AgentMessageModel,
    AgentStagedDatasetModel,
    ConversationEmbeddingModel,
    DatasetModel,
    JobEmbeddingModel,
    JobModel,
    LogEntryModel,
    ProgressEventModel,
)

# A stored pgvector is dim×4 bytes (float32). ``job_embeddings`` holds three
# such vectors per row; ``conversation_embeddings`` holds one. Counted by row
# rather than measured because ``octet_length`` does not apply to the vector
# type and casting it to text would size the decimal repr, not the storage.
_VECTOR_BYTES = EMBEDDING_DIM * 4
_JOB_EMBEDDING_ROW_BYTES = _VECTOR_BYTES * 3
_CONVERSATION_EMBEDDING_ROW_BYTES = _VECTOR_BYTES

STORAGE_CATEGORIES = (
    "optimizations",
    "datasets",
    "agent_chats",
    "staged_uploads",
    "logs",
    "progress_events",
    "embeddings",
)


@dataclass(frozen=True)
class StorageUsage:
    """A user's total stored bytes and the per-category breakdown behind it.

    ``breakdown`` is keyed by :data:`STORAGE_CATEGORIES`; ``total`` is their sum.
    """

    total: int
    breakdown: dict[str, int]


def json_byte_size(value: object) -> int:
    """Return the UTF-8 byte length of ``value`` serialized as compact JSON.

    Args:
        value: A JSON-serializable mapping or list, or ``None``.

    Returns:
        ``0`` when ``value`` is ``None``; otherwise the encoded length. Used to
        size a job's JSON columns at write time and to size an incoming
        submission before it is persisted.
    """
    if value is None:
        return 0
    return len(json.dumps(value, separators=(",", ":"), default=str).encode("utf-8"))


def _byte_size(column: object, dialect_name: str):
    """Return a SQL expression for the byte length of ``column`` rendered as text.

    Args:
        column: The model column to size.
        dialect_name: ``engine.dialect.name`` — selects ``octet_length``
            (Postgres) versus ``length`` (SQLite and others, where there is no
            ``octet_length``).

    Returns:
        A SQLAlchemy expression yielding the per-row byte length, ``0`` on NULL.
    """
    as_text = cast(column, Text)
    length_fn = func.octet_length if dialect_name == "postgresql" else func.length
    return func.coalesce(length_fn(as_text), 0)


def compute_user_storage(engine: Engine, username: str) -> StorageUsage:
    """Sum every byte the user owns across the database into one budget figure.

    Args:
        engine: The shared SQLAlchemy engine all storage tables live on.
        username: The owner whose footprint is measured; matched
            case-insensitively against the lowercased owner columns.

    Returns:
        A :class:`StorageUsage` with the per-category breakdown and total. An
        empty/blank username yields an all-zero usage rather than scanning.
    """
    normalized = (username or "").strip().lower()
    empty = StorageUsage(total=0, breakdown=dict.fromkeys(STORAGE_CATEGORIES, 0))
    if not normalized:
        return empty

    dialect = engine.dialect.name
    with Session(engine) as session:
        user_job_ids = select(JobModel.optimization_id).where(JobModel.username == normalized)
        user_conversation_ids = select(AgentConversationModel.id).where(
            AgentConversationModel.username == normalized
        )

        def scalar(statement) -> int:
            """Execute a single-aggregate select and coerce the result to int."""
            return int(session.execute(statement).scalar() or 0)

        optimizations = scalar(
            select(func.coalesce(func.sum(JobModel.stored_bytes), 0)).where(JobModel.username == normalized)
        )
        datasets = scalar(
            select(func.coalesce(func.sum(DatasetModel.byte_size), 0)).where(
                DatasetModel.owner_username == normalized
            )
        )
        logs = scalar(
            select(func.coalesce(func.sum(_byte_size(LogEntryModel.message, dialect)), 0)).where(
                LogEntryModel.optimization_id.in_(user_job_ids)
            )
        )
        progress_events = scalar(
            select(func.coalesce(func.sum(_byte_size(ProgressEventModel.metrics, dialect)), 0)).where(
                ProgressEventModel.optimization_id.in_(user_job_ids)
            )
        )
        agent_chats = scalar(
            select(
                func.coalesce(
                    func.sum(
                        _byte_size(AgentMessageModel.content, dialect)
                        + _byte_size(AgentMessageModel.tool_calls, dialect)
                    ),
                    0,
                )
            ).where(AgentMessageModel.conversation_id.in_(user_conversation_ids))
        )
        staged_uploads = scalar(
            select(func.coalesce(func.sum(_byte_size(AgentStagedDatasetModel.rows, dialect)), 0)).where(
                AgentStagedDatasetModel.username == normalized
            )
        )
        job_embedding_rows = scalar(
            select(func.count(JobEmbeddingModel.optimization_id)).where(JobEmbeddingModel.user_id == normalized)
        )
        conversation_embedding_rows = scalar(
            select(func.count(ConversationEmbeddingModel.conversation_id)).where(
                ConversationEmbeddingModel.username == normalized
            )
        )
        embeddings = (
            job_embedding_rows * _JOB_EMBEDDING_ROW_BYTES
            + conversation_embedding_rows * _CONVERSATION_EMBEDDING_ROW_BYTES
        )

    breakdown = {
        "optimizations": optimizations,
        "datasets": datasets,
        "agent_chats": agent_chats,
        "staged_uploads": staged_uploads,
        "logs": logs,
        "progress_events": progress_events,
        "embeddings": embeddings,
    }
    return StorageUsage(total=sum(breakdown.values()), breakdown=breakdown)
