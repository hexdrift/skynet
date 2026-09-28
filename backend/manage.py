#!/usr/bin/env python3
"""Skynet management CLI.

Usage:
    python manage.py setup    — First-time database setup
    python manage.py check    — Verify database connection
    python manage.py shell    — Open a Python shell with app context
    python manage.py reembed  — Recompute every job's explore search embedding
"""

from __future__ import annotations

import argparse
import code
import sys
from pathlib import Path

from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from alembic import command
from core.config import settings
from core.registry import ServiceRegistry
from core.service_gateway.embedding_pipeline import reembed_all_embeddings
from core.storage.models import Base
from core.storage.remote import RemoteDBJobStore

load_dotenv(Path(__file__).parent / ".env")

ALEMBIC_INI = Path(__file__).parent / "alembic.ini"


def _get_db_url() -> str:
    """Return the remote database URL from settings, exiting if unset.

    Returns:
        The plaintext database URL string.
    """
    if not settings.remote_db_url:
        print("✗ REMOTE_DB_URL not set in .env")
        sys.exit(1)
    return settings.remote_db_url.get_secret_value()


def cmd_check() -> None:
    """Test database connectivity and print the PostgreSQL version."""
    url = _get_db_url()
    try:
        engine = create_engine(url, echo=False, pool_pre_ping=True)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
            print("✓ Connected successfully")
            print(f"  PostgreSQL: {version}")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        sys.exit(1)


def cmd_setup() -> None:
    """Run full first-time setup: test connection, run Alembic, verify tables.

    The canonical schema bootstrap is ``alembic upgrade head``. After the
    revisions apply we still instantiate :class:`RemoteDBJobStore` so the
    idempotent in-``__init__`` ALTERs run too — that keeps SQLite tests and
    local dev working without an explicit migrate step.
    """
    url = _get_db_url()
    masked = url.split("@")[-1] if "@" in url else url
    print(f"\n🔧 Skynet Setup — {masked}\n")

    cmd_check()

    try:
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        print("\n✓ Alembic migrations applied")
    except Exception as e:
        print(f"\n✗ Alembic upgrade failed: {e}")
        sys.exit(1)

    try:
        store = RemoteDBJobStore(url)
        print("\n✓ Tables ready:")
        for name in Base.metadata.tables:
            print(f"  - {name}")
        store.engine.dispose()
    except Exception as e:
        print(f"\n✗ Table verification failed: {e}")
        sys.exit(1)

    print("\n✓ Setup complete. Start the server with: python main.py")


def cmd_shell() -> None:
    """Open an interactive Python shell with ``settings``, ``store`` and ``registry`` available."""
    url = _get_db_url()
    store = RemoteDBJobStore(url)
    registry = ServiceRegistry()

    banner = "Skynet shell — available objects:\n  settings, store (JobStore), registry (ServiceRegistry)\n"
    code.interact(
        banner=banner,
        local={
            "settings": settings,
            "store": store,
            "registry": registry,
        },
    )


def cmd_reembed() -> None:
    """Recompute every successful job's explore summary embedding in place.

    Run this after the summariser's inputs change so the existing corpus is
    re-embedded from the new signal — the periodic repair scan won't, because
    those rows still look fresh. Requires ``SEARCH_BACKEND=semantic`` plus a
    reachable summariser model and embedder; it makes one LLM call per job, so
    it is a deliberate, potentially slow and costly one-off, not part of setup.
    """
    url = _get_db_url()
    store = RemoteDBJobStore(url)
    try:
        count = reembed_all_embeddings(store)
        print(f"✓ Re-embedded {count} job(s)")
    finally:
        store.engine.dispose()


def main() -> None:
    """Parse the command-line argument and dispatch to the chosen subcommand."""
    parser = argparse.ArgumentParser(
        description="Skynet management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Commands:\n"
            "  setup     First-time database setup\n"
            "  check     Verify database connection\n"
            "  shell     Interactive Python shell with app context\n"
            "  reembed   Recompute every job's explore search embedding"
        ),
    )
    parser.add_argument("command", choices=["setup", "check", "shell", "reembed"], help="Command to run")
    args = parser.parse_args()

    {"setup": cmd_setup, "check": cmd_check, "shell": cmd_shell, "reembed": cmd_reembed}[args.command]()


if __name__ == "__main__":
    main()
