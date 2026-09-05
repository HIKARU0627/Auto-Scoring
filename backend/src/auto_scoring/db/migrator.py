"""Thin wrapper around the Alembic CLI so code and tests migrate the same way.

``AUTO_SCORING_DB_URL`` in the environment overrides the target for a bare
``uv run alembic ...`` invocation; these helpers set it explicitly.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

#: `auto_scoring/`, i.e. this module's own package directory. `pyproject.toml`
#: force-includes `migrations/` (and `alembic.ini`, for parity) here in the
#: built wheel, so an installed `auto-scoring-sidecar` console script finds
#: them without the `backend/` source tree existing at all.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent

#: `backend/` in a source checkout, where `migrations/` and `alembic.ini`
#: physically live during development (three levels above this file:
#: `auto_scoring/db/migrator.py` -> `auto_scoring` -> `src` -> `backend`).
_SOURCE_BACKEND_ROOT = Path(__file__).resolve().parents[3]


def _migrations_root() -> Path:
    """The directory holding ``env.py`` and ``versions/``.

    Tries the packaged (installed-wheel) location first, then falls back to
    the source-checkout location -- whichever actually exists, since the two
    never coexist for the same install (Issue #26 review: previously this
    only ever looked at the source-checkout path, so a wheel install -- which
    packages `src/auto_scoring` only, not the `backend/` sibling directory --
    had no migrations to find, and `auto-scoring-sidecar` exited before
    Uvicorn ever started).
    """
    packaged = _PACKAGE_ROOT / "migrations"
    if packaged.is_dir():
        return packaged
    return _SOURCE_BACKEND_ROOT / "migrations"


def _alembic_ini_path() -> Path | None:
    """The `alembic.ini` to hand `Config`, or ``None`` if neither location has one.

    Not strictly required for the programmatic `upgrade`/`downgrade`/
    `current_revision` calls below (`script_location` and `sqlalchemy.url`
    are set explicitly regardless), but keeps `Config` consistent with a
    developer's ``uv run alembic ...`` invocation from `backend/`, which does
    read it.
    """
    for candidate in (_PACKAGE_ROOT / "alembic.ini", _SOURCE_BACKEND_ROOT / "alembic.ini"):
        if candidate.is_file():
            return candidate
    return None


def alembic_config(db_url: str) -> Config:
    """An Alembic :class:`Config` pointed at this repo's migrations and ``db_url``.

    ``db_url`` is also stashed in ``config.attributes`` (in addition to the
    ``sqlalchemy.url`` main option) so ``migrations/env.py`` can prefer it
    unconditionally over ``AUTO_SCORING_DB_URL`` -- a caller of this
    function has decided which database to touch (e.g. the sidecar's
    ``--app-data-dir``), and that decision must not be silently overridden
    by an environment variable meant for a bare, un-parameterized
    ``uv run alembic ...`` invocation. Without this, a stray
    ``AUTO_SCORING_DB_URL`` inherited by the sidecar's process environment
    would make it migrate a completely different database than the one it
    then opens and serves requests against (Issue #26 review).
    """
    ini_path = _alembic_ini_path()
    config = Config(str(ini_path) if ini_path is not None else None)
    config.set_main_option("script_location", str(_migrations_root()))
    config.set_main_option("sqlalchemy.url", db_url)
    config.attributes["configured_db_url"] = db_url
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
