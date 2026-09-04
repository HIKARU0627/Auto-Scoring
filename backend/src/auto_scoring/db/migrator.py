"""Thin wrapper around the Alembic CLI so code and tests migrate the same way.

``AUTO_SCORING_DB_URL`` in the environment overrides the target for a bare
``uv run alembic ...`` invocation; these helpers set it explicitly.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

_BACKEND_ROOT = Path(__file__).resolve().parents[3]


def alembic_config(db_url: str) -> Config:
    """An Alembic :class:`Config` pointed at this repo's migrations and ``db_url``."""
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def upgrade(db_url: str, revision: str = "head") -> None:
    """Apply migrations up to ``revision`` (default: latest)."""
    command.upgrade(alembic_config(db_url), revision)


def downgrade(db_url: str, revision: str) -> None:
    """Roll migrations back to ``revision`` (e.g. ``"base"`` or ``"0001"``)."""
    command.downgrade(alembic_config(db_url), revision)


def current_revision(db_url: str) -> str | None:
    """Return the revision stamped in ``db_url``'s ``alembic_version`` table."""
    from alembic.runtime.migration import MigrationContext

    from auto_scoring.db.engine import create_sqlite_engine

    engine = create_sqlite_engine(db_url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()
