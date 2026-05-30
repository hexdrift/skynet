"""SQLAlchemy ORM models for job storage.

Defines the shared database models used by the PostgreSQL storage backend.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIM = 512
JSON_STORE = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""


class ApiTokenModel(Base):
    """Per-user personal access token (one active token per user).

    Stores only the SHA-256 hash of the issued token; the plaintext is shown
    to the user once at creation and never persisted. ``username`` is the
    primary key, so generating a new token replaces the user's previous one
    (rotation). ``token_hash`` is uniquely indexed for the auth lookup, which
    queries by hash without ever holding the plaintext.
    """

    __tablename__ = "api_tokens"

    username: Mapped[str] = mapped_column(String(255), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    last4: Mapped[str] = mapped_column(String(4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OptimizationShareLinkModel(Base):
    """Per-optimization sharing config keyed by a public link token.

    The ``token`` is the unguessable capability identifier embedded in the
    public ``/share/<token>`` URL. It is stored in plaintext because it IS the
    public identifier (like a ChatGPT share id), not a credential hash. The
    active (``revoked_at IS NULL``) row per optimization holds the sharing
    config; ``general_access`` selects the anonymous-link policy:
    ``'restricted'`` (owner + invited members only) or ``'anyone'`` (anyone
    with the link gets a view-only, inference-free snapshot). Revoking sets
    ``revoked_at`` so the public route returns 404 thereafter. Rows are removed
    when the optimization is deleted.
    """

    __tablename__ = "optimization_share_links"

    token: Mapped[str] = mapped_column(String(48), primary_key=True)
    optimization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    general_access: Mapped[str] = mapped_column(
        String(16), nullable=False, default="restricted", server_default="restricted"
    )


class OptimizationShareGrantModel(Base):
    """A single per-user access grant on a shared optimization.

    Each row invites one ``grantee_username`` to an optimization with a tier
    ``role`` (``'viewer'`` / ``'editor'`` / ``'owner'``). The pair
    ``(optimization_id, grantee_username)`` is the primary key, so re-inviting a
    user replaces their existing grant. ``general_access`` on the link and these
    per-user grants coexist: an anyone-link can be on while named members hold
    higher roles. Rows are removed when the optimization is deleted.
    """

    __tablename__ = "optimization_share_grants"

    optimization_id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)
    grantee_username: Mapped[str] = mapped_column(String(255), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class JobModel(Base):
    """SQLAlchemy model for the jobs table.

    The ``claimed_by`` / ``claimed_at`` / ``lease_expires_at`` triplet implements
    a DB-backed work queue safe for multi-pod horizontal scaling: each worker
    atomically claims a row via ``SELECT ... FOR UPDATE SKIP LOCKED`` and
    extends the lease while it holds the job. A pod that crashes leaves an
    expired lease which any other pod is free to re-claim on its next poll.
    """

    __tablename__ = "jobs"

    optimization_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_remaining_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_metrics: Mapped[dict[str, Any]] = mapped_column(JSON_STORE, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON_STORE, nullable=True)
    payload_overview: Mapped[dict[str, Any]] = mapped_column(JSON_STORE, default=dict)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON_STORE, nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    optimization_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    code_version: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    claimed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set once, by the worker that wins the CAS update inside
    # ``claim_completion_notification`` — guarantees a single Slack/Teams
    # message per job even when orphan recovery re-runs a row.
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Optional client-supplied dedup key; lookups are scoped per submitter so
    # two users may legitimately reuse the same key without colliding.
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_jobs_status_created_at", "status", "created_at"),
        Index("ix_jobs_lease_expires_at", "lease_expires_at"),
        # Lookup index for idempotency dedup; the corresponding PG-only
        # uniqueness guard (partial on idempotency_key IS NOT NULL) lives in
        # the alembic migration so two concurrent submits with the same key
        # cannot both create rows.
        Index("ix_jobs_username_idempotency_key", "username", "idempotency_key"),
    )


class ProgressEventModel(Base):
    """SQLAlchemy model for the job_progress_events table."""

    __tablename__ = "job_progress_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    optimization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    event: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON_STORE, default=dict)

    __table_args__ = (Index("ix_job_progress_events_optimization_timestamp", "optimization_id", "timestamp"),)


class LogEntryModel(Base):
    """SQLAlchemy model for the job_logs table."""

    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    optimization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    logger: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    pair_index: Mapped[int | None] = mapped_column(Integer, nullable=True)


class UserQuotaOverrideModel(Base):
    """SQLAlchemy model for live per-user quota overrides."""

    __tablename__ = "user_quota_overrides"

    username: Mapped[str] = mapped_column(String(255), primary_key=True)
    quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class UserQuotaAuditModel(Base):
    """SQLAlchemy model for quota administration audit events."""

    __tablename__ = "user_quota_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_username: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    old_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class JobEmbeddingModel(Base):
    """Per-job embedding row backing the recommendation service.

    One row is written after a job finishes successfully. Three named
    aspects are embedded independently so a similarity search can
    weigh them separately (``summary`` = LLM-authored task description,
    ``code`` = signature + metric source, ``schema`` = dataset schema
    digest). All use the configured embedding API model,
    MRL-truncated to ``EMBEDDING_DIM``.

    Metadata (``optimization_type``, ``winning_model``, ``winning_rank``)
    is denormalized from ``jobs`` so the search can filter and rerank
    without an extra join per-candidate.
    """

    __tablename__ = "job_embeddings"

    optimization_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    optimization_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    winning_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    winning_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    embedding_summary: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_code: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_schema: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    is_recommendable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
    baseline_metric: Mapped[float | None] = mapped_column(Float, nullable=True)
    optimized_metric: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    optimizer_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    optimizer_kwargs: Mapped[dict[str, Any] | None] = mapped_column(JSON_STORE, nullable=True)
    module_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    task_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    projection_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    projection_y: Mapped[float | None] = mapped_column(Float, nullable=True)


class AgentConversationModel(Base):
    """Persisted generalist-agent conversation header.

    One row per user-owned thread. ``title`` is auto-derived from the first
    user message and may be edited via PATCH. ``pinned`` and ``archived_at``
    are mutually independent — an archived row may still be pinned.
    """

    __tablename__ = "agent_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("ix_agent_conversations_user_updated", "username", "updated_at"),
        Index("ix_agent_conversations_user_pinned", "username", "pinned"),
    )


class AgentMessageModel(Base):
    """Single turn inside an :class:`AgentConversationModel`.

    ``tool_calls`` is the rendered ``AgentToolCall[]`` payload exactly as the
    frontend stores it in React state — kept as JSON rather than normalized
    so the renderer needs no migration when tool shapes change.
    """

    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON_STORE, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Five nullable training-metadata columns feed the training-ground harness
    # (training_ground_SPEC.md §4). Old rows predate the migration and stay
    # NULL; the optimize CLI filters them out via WHERE wizard_state_before IS NOT NULL.
    wizard_state_before: Mapped[dict[str, Any] | None] = mapped_column(JSON_STORE, nullable=True)
    wizard_state_after: Mapped[dict[str, Any] | None] = mapped_column(JSON_STORE, nullable=True)
    allowed_tools: Mapped[list[str] | None] = mapped_column(JSON_STORE, nullable=True)
    tool_schema_hashes: Mapped[dict[str, str] | None] = mapped_column(JSON_STORE, nullable=True)
    router_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON_STORE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )

    __table_args__ = (Index("ix_agent_messages_conv_created", "conversation_id", "created_at"),)


class ConversationEmbeddingModel(Base):
    """Per-conversation embedding row backing the agent-history search.

    Mirrors :class:`JobEmbeddingModel` so the search dispatch and the
    backfill / purge plumbing can be lifted from the optimization corpus
    with a different source table. The ``summary_text`` column holds the
    exact prose that was embedded — concatenated user turns (and a slice
    of assistant replies) capped to a budget — so lexical fallback can hit
    the same text the vector was built from.
    """

    __tablename__ = "conversation_embeddings"

    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    username: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    embedding_summary: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Snapshot of ``conversation.updated_at`` at embed time. Used by the
    # backfill sweep to detect stale rows (conversation got new turns after
    # the last embed) without diffing message content.
    embedded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


# Holds rows the wizard parsed in the browser so the generalist agent can
# submit ``/run`` without re-shipping the dataset through its context. Rows
# live here only between upload and submit; the frontend stages on upload,
# the /run handler dereferences by id, and stale rows are evicted by user/age.
class AgentStagedDatasetModel(Base):
    """Server-side cache of wizard dataset rows for agent-driven submits."""

    __tablename__ = "agent_staged_datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    dataset_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON_STORE, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )

    __table_args__ = (Index("ix_agent_staged_datasets_user_created", "username", "created_at"),)
