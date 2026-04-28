"""Alembic environment — wires REMOTE_DB_URL into the migration runner.

Reads the database URL from the ``REMOTE_DB_URL`` env var (the same env
the application uses) so the same secret feeds both the migrate Job and
the running pods. Falls back to the value in ``alembic.ini`` if the env
var is unset (useful for local ``alembic revision --autogenerate``).
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from core.storage.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

env_url = os.environ.get("REMOTE_DB_URL")
if env_url:
    config.set_main_option("sqlalchemy.url", env_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in offline mode (emit SQL to stdout, no connection).

    Useful for pre-rendering the migration SQL into a review-able artifact
    before running it against a managed database.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
