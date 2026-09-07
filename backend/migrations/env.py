"""Alembic environment.

Target metadata is ``auto_scoring.db.base.Base.metadata``; importing
``auto_scoring.db.orm`` registers every table on it. The engine comes from
``auto_scoring.db.engine`` so migrations run with the same PRAGMAs (WAL) as
the app, and ``render_as_batch`` keeps future ``ALTER TABLE`` migrations
working on SQLite.

Logging is configured from ``alembic.ini`` only for a bare ``alembic`` CLI
run, never for the programmatic calls the sidecar makes on startup -- see the
comment on the ``fileConfig`` call below.

``foreign_keys`` is deliberately turned back *off* for the migration
connection (see ``run_migrations_online``): SQLite performs an implicit
``DELETE FROM`` -- cascading to any ``ON DELETE CASCADE`` children -- when a
table is ``DROP``ped while foreign key enforcement is on, which is exactly
what Alembic's SQLite batch mode does internally to express an ``ALTER
TABLE`` it can't run directly (e.g. adding a column or a ``CHECK``
constraint). Left on, a batch migration on any table with FK-referencing
children (e.g. ``submissions`` -> recognition_results/grade_results/
annotations/reviews/jobs) would silently delete every one of those rows.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context

from auto_scoring.db import orm as _orm  # noqa: F401  (registers tables on Base)
from auto_scoring.db.base import Base
from auto_scoring.db.engine import create_sqlite_engine

config = context.config
# Configure logging from `alembic.ini` only for a bare `uv run alembic ...`,
# never for a programmatic caller. `db.migrator.alembic_config` marks its own
# Config with `configured_db_url`, and that is the path the *running sidecar*
# takes on startup -- where `fileConfig` is destructive rather than helpful:
#
# * It replaces the root logger's handlers with `alembic.ini`'s console
#   handler, throwing away the ones `api.sidecar.install_log_redaction`
#   installed moments earlier -- both the rotating file log (the only durable
#   record in a distribution, docs/windows-distribution.md §5.5) and, worse,
#   the filter that keeps the session bearer token out of it.
# * It defaults to `disable_existing_loggers=True`, which silences every
#   logger `alembic.ini` does not name -- i.e. every `auto_scoring.*` logger,
#   all of which already exist by then -- for the rest of the process's life.
#   Job outcomes, OCR/AI/PDF failures, the whole of simplified-design-
#   specification.md §28, dropped from the first migration onward.
#
# Found while wiring up the file log in Issue #24.
if config.config_file_name is not None and "configured_db_url" not in config.attributes:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """The database this migration run targets.

    ``auto_scoring.db.migrator.alembic_config`` stashes its ``db_url`` in
    ``config.attributes["configured_db_url"]`` for every *programmatic*
    caller (the sidecar's startup migration, `upgrade`/`downgrade`/tests) --
    that value wins unconditionally, since the caller has already decided
    exactly which database to touch. ``AUTO_SCORING_DB_URL`` only applies to
    a bare ``uv run alembic ...`` invocation, which builds its `Config`
    straight from `alembic.ini` and never sets that attribute. Checking the
    env var first (the previous behaviour) let a stray
    ``AUTO_SCORING_DB_URL`` inherited by the sidecar's process environment
    silently redirect its startup migration to an unrelated database, while
    the sidecar itself went on to open and serve requests against the
    (possibly still unmigrated) ``--app-data-dir`` database -- `/healthz`
    kept succeeding while every dependency-graph request failed on a
    missing table (Issue #26 review).
    """
    configured = config.attributes.get("configured_db_url")
    if configured is not None:
        return str(configured)
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
    engine = create_sqlite_engine(_database_url(), enforce_foreign_keys=False)
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
