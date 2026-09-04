"""Alembic environment.

Target metadata is ``auto_scoring.db.base.Base.metadata``; importing
``auto_scoring.db.orm`` registers every table on it. The engine comes from
``auto_scoring.db.engine`` so migrations run with the same PRAGMAs (WAL,
``foreign_keys=ON``) as the app, and ``render_as_batch`` keeps future
``ALTER TABLE`` migrations working on SQLite.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context

from auto_scoring.db import orm as _orm  # noqa: F401  (registers tables on Base)
from auto_scoring.db.base import Base
from auto_scoring.db.engine import create_sqlite_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return (
        os.environ.get("AUTO_SCORING_DB_URL")
        or config.get_main_option("sqlalchemy.url")
        or "sqlite:///app-data/database.sqlite"
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_sqlite_engine(_database_url())
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
