"""SQLite engine wired for the sidecar: WAL, enforced foreign keys, sane waits.

Every connection gets the same PRAGMAs (docs/technology-stack.md §3.3):

* ``journal_mode=WAL`` — readers do not block the single writer.
* ``foreign_keys=ON`` — SQLite ignores foreign keys unless asked per-connection;
  without this, orphan rows and dangling references would slip through
  (issue #11 acceptance: "孤児 record … を … 拒否する").
* ``busy_timeout`` — wait instead of failing when the writer holds the lock.
* ``synchronous=NORMAL`` — the safe pairing with WAL.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

_BUSY_TIMEOUT_MS = 5_000


def sqlite_url(path: Path | str) -> str:
    """Return a SQLAlchemy URL for a SQLite file at ``path``."""
    return f"sqlite:///{Path(path)}"


def create_sqlite_engine(
    url: str, *, echo: bool = False, enforce_foreign_keys: bool = True
) -> Engine:
    """Create an :class:`~sqlalchemy.Engine` with the sidecar's PRAGMAs applied.

    ``enforce_foreign_keys=False`` is for Alembic's migration connection only
    (see ``migrations/env.py``): SQLite performs an implicit ``DELETE FROM`` --
    cascading to any ``ON DELETE CASCADE`` children -- when a table is
    ``DROP``ped while foreign key enforcement is on, which is exactly what
    Alembic's SQLite batch mode does internally to express an ``ALTER TABLE``
    it can't run directly. The pragma must be set at connect time (a no-op
    once a transaction is open), so this goes through the same connect-event
    hook as the other PRAGMAs rather than a statement run mid-connection.
    """
    engine = create_engine(url, echo=echo, future=True)

    @event.listens_for(engine, "connect")
    def _apply_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA foreign_keys={'ON' if enforce_foreign_keys else 'OFF'}")
            cursor.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()

    return engine


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a ``sessionmaker`` bound to ``engine`` (no autoflush surprises)."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
