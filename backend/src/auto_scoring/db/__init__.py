"""SQLite persistence: engine, SQLAlchemy ORM tables, and the Alembic migrator.

This package may import SQLAlchemy and Alembic; the domain may not. The Flutter
app never opens the database file — it goes through the Python sidecar's API
(docs/technology-stack.md §1.1 "DB の所有者").
"""

from auto_scoring.db.base import Base
from auto_scoring.db.engine import (
    build_session_factory,
    create_sqlite_engine,
    sqlite_url,
)

__all__ = [
    "Base",
    "build_session_factory",
    "create_sqlite_engine",
    "sqlite_url",
]
