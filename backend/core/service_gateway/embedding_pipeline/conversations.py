"""Per-conversation embedding pipeline backing the agent-history search.

Same shape as :mod:`core` (the job-summary pipeline) so the lexical/semantic
dispatch in :mod:`agent_history` can reuse the contract verbatim:

1. After an assistant turn lands, the router fires
   ``embed_conversation(conversation_id, engine=…)`` on a daemon thread.
2. That task: pulls the conversation's user + assistant turns, concatenates
   a capped haystack, runs it through the shared embedder, and upserts the
   vector + ``summary_text`` into ``conversation_embeddings``.
3. On backend startup, ``backfill_missing_conversation_embeddings`` scans
   for rows whose conversation gained turns after the last embed (or were
   never embedded) and drains them sequentially on a daemon thread.

The configured embedding model is shared with the job pipeline; only the
*source* differs. Failures never raise — a missing key or flaky API
degrades to "skip this conversation," and the row is retried on the next
startup scan.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ...config import settings
from ...storage.models import (
    AgentConversationModel,
    AgentMessageModel,
    ConversationEmbeddingModel,
)
from .embeddings import get_embedder

logger = logging.getLogger(__name__)

# Budget for the concatenated haystack handed to the embedder. The Jina v4
# adapter handles longer inputs, but capping keeps the embedding cost bounded
# for users who run multi-day threads.
_HAYSTACK_CHAR_BUDGET = 8000
# Per-turn cap so a single very long message can't crowd out the rest of the
# thread. Tuned to keep typical multi-paragraph turns intact while leaving
# room for at least a dozen turns inside the global budget.
_PER_TURN_CHAR_CAP = 1200


def _build_haystack(messages: list[tuple[str, str]]) -> str:
    """Concatenate role-tagged turns into a single embedder-ready string.

    Args:
        messages: ``[(role, content)]`` pairs in chronological order.

    Returns:
        A string of the form ``"user: …\\nassistant: …\\n…"`` capped at
        :data:`_HAYSTACK_CHAR_BUDGET` characters; per-turn entries are
        clipped to :data:`_PER_TURN_CHAR_CAP` first so a runaway turn can't
        starve the rest of the thread.
    """
    parts: list[str] = []
    used = 0
    for role, content in messages:
        text_part = (content or "").strip()
        if not text_part:
            continue
        if len(text_part) > _PER_TURN_CHAR_CAP:
            text_part = text_part[:_PER_TURN_CHAR_CAP] + "…"
        entry = f"{role}: {text_part}"
        if used + len(entry) + 1 > _HAYSTACK_CHAR_BUDGET:
            break
        parts.append(entry)
        used += len(entry) + 1
    return "\n".join(parts)


def _load_conversation_text(
    session: Session, conversation_id: str
) -> tuple[str | None, str | None]:
    """Return ``(username, haystack)`` for the conversation, or ``(None, None)``.

    Args:
        session: Active SQLAlchemy session bound to the engine.
        conversation_id: ID of the conversation to materialize.

    Returns:
        A 2-tuple of ``(username, haystack)``. ``haystack`` is the
        concatenated text built by :func:`_build_haystack`; both entries
        are ``None`` when the conversation is missing or has no usable
        turns.
    """
    conv = session.get(AgentConversationModel, conversation_id)
    if conv is None:
        return None, None
    rows = (
        session.query(AgentMessageModel.role, AgentMessageModel.content)
        .filter(AgentMessageModel.conversation_id == conversation_id)
        .filter(AgentMessageModel.role.in_(("user", "assistant")))
        .order_by(AgentMessageModel.created_at.asc(), AgentMessageModel.id.asc())
        .all()
    )
    haystack = _build_haystack([(r.role, r.content) for r in rows])
    return str(conv.username), haystack or None


def embed_conversation(conversation_id: str, *, engine: Engine) -> bool:
    """Compute and upsert the haystack embedding for one conversation.

    Called on a daemon thread from the generalist-agent router and from
    the startup backfill — must never raise.

    Args:
        conversation_id: ID of the conversation whose embedding should be
            (re)computed.
        engine: SQLAlchemy engine the agent-history tables are bound to.

    Returns:
        True when a row was written; False when the pipeline skipped the
        conversation (disabled, embedder unavailable, conversation missing,
        no usable text, DB error).
    """
    if not settings.embeddings_enabled:
        return False

    embedder = get_embedder()
    if not embedder.available():
        return False

    try:
        with Session(engine) as session:
            username, haystack = _load_conversation_text(session, conversation_id)
            if not username or not haystack:
                return False
            vector = embedder.encode(haystack, task="retrieval.passage")
            if vector is None:
                return False
            existing = session.get(ConversationEmbeddingModel, conversation_id)
            now = datetime.now(UTC)
            fields: dict[str, Any] = {
                "username": username,
                "embedding_summary": vector,
                "summary_text": haystack,
                "embedded_at": now,
            }
            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
            else:
                session.add(
                    ConversationEmbeddingModel(
                        conversation_id=conversation_id,
                        **fields,
                    )
                )
            session.commit()
    except Exception as exc:
        logger.warning(
            "embed_conversation upsert failed for %s: %s", conversation_id, exc
        )
        return False

    logger.info("Conversation embedding indexed for %s", conversation_id)
    return True


def queue_conversation_embed(conversation_id: str, *, engine: Engine) -> None:
    """Embed ``conversation_id`` on a daemon thread; never raises.

    Matches the fire-and-forget shape used by the worker for job summary
    embeddings — the caller (an HTTP handler) returns to the client without
    blocking on the embedding API.

    Args:
        conversation_id: ID of the conversation to embed.
        engine: SQLAlchemy engine the conversation tables are bound to.
    """
    if not settings.embeddings_enabled:
        return
    thread = threading.Thread(
        target=embed_conversation,
        args=(conversation_id,),
        kwargs={"engine": engine},
        name=f"embed-conv-{conversation_id[:8]}",
        daemon=True,
    )
    thread.start()


def _fetch_stale_conversation_ids(engine: Engine) -> list[str]:
    """Return conversation IDs whose embedding is missing or stale.

    Stale means either (a) no row in ``conversation_embeddings``, (b) the
    embedding vector is NULL, or (c) the conversation has been updated
    after its last embed timestamp.

    Args:
        engine: SQLAlchemy engine the agent-history tables are bound to.

    Returns:
        A list of conversation IDs, oldest-stale first so a long-paused
        backfill drains the oldest data before recently-touched threads.
    """
    try:
        with Session(engine) as session:
            rows = (
                session.execute(
                    text(
                        "SELECT c.id "
                        "FROM agent_conversations c "
                        "LEFT JOIN conversation_embeddings e ON e.conversation_id = c.id "
                        "WHERE e.conversation_id IS NULL "
                        "   OR e.embedding_summary IS NULL "
                        "   OR c.updated_at > e.embedded_at "
                        "ORDER BY c.updated_at ASC"
                    )
                )
                .mappings()
                .all()
            )
            return [row["id"] for row in rows]
    except Exception as exc:
        logger.warning("Could not scan for stale conversation embeddings: %s", exc)
        return []


def _drain_conversation_backfill(engine: Engine, ids: list[str]) -> None:
    """Embed each pending conversation sequentially, logging progress.

    Args:
        engine: SQLAlchemy engine forwarded to :func:`embed_conversation`.
        ids: Conversation IDs to embed, in the order returned by
            :func:`_fetch_stale_conversation_ids`.
    """
    total = len(ids)
    if total == 0:
        return
    logger.info(
        "Conversation embedding backfill: starting drain of %d row(s)", total
    )
    ok = 0
    for idx, conversation_id in enumerate(ids, start=1):
        try:
            written = embed_conversation(conversation_id, engine=engine)
        except Exception as exc:
            logger.warning(
                "Conversation embedding backfill: %s raised: %s", conversation_id, exc
            )
            written = False
        if written:
            ok += 1
        logger.info(
            "Conversation embedding backfill: %d/%d processed (%d written)",
            idx,
            total,
            ok,
        )
    logger.info(
        "Conversation embedding backfill: drain complete (%d/%d written)", ok, total
    )


def backfill_missing_conversation_embeddings(engine: Engine) -> int:
    """Scan for conversations whose embedding is missing or stale and queue a drain.

    Args:
        engine: SQLAlchemy engine the agent-history tables are bound to.

    Returns:
        The number of conversations queued (0 when none are stale or the
        scan failed).
    """
    if not settings.embeddings_enabled:
        return 0
    ids = _fetch_stale_conversation_ids(engine)
    if not ids:
        return 0
    thread = threading.Thread(
        target=_drain_conversation_backfill,
        args=(engine, ids),
        name="embed-conv-backfill",
        daemon=True,
    )
    thread.start()
    return len(ids)


def purge_orphan_conversation_embeddings(engine: Engine) -> int:
    """Delete embedding rows whose conversation no longer exists.

    The CASCADE FK on :class:`ConversationEmbeddingModel.conversation_id`
    keeps the table consistent in steady state — this helper covers
    pre-migration orphans and any rare ON DELETE skips.

    Args:
        engine: SQLAlchemy engine the agent-history tables are bound to.

    Returns:
        The number of orphan rows deleted (0 when none or the delete failed).
    """
    try:
        with Session(engine) as session:
            result = session.execute(
                text(
                    "DELETE FROM conversation_embeddings WHERE conversation_id IN ("
                    "SELECT ce.conversation_id FROM conversation_embeddings ce "
                    "LEFT JOIN agent_conversations c "
                    "ON c.id = ce.conversation_id "
                    "WHERE c.id IS NULL"
                    ")"
                )
            )
            session.commit()
            deleted = int(result.rowcount or 0)
            if deleted:
                logger.info(
                    "Conversation embedding sweep: removed %d orphan row(s)", deleted
                )
            return deleted
    except Exception as exc:
        logger.warning("Conversation embedding orphan sweep failed: %s", exc)
        return 0
