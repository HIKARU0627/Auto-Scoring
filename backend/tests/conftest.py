"""Shared fixtures for the persistence tests.

Every fixture uses a real on-disk SQLite database in a per-test temp directory
(WAL needs a file, and the issue asks for tests against real SQLite, not an
in-memory stand-in).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

import auto_scoring.db.orm  # noqa: F401  (registers tables on Base.metadata)
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.db.base import Base
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "database.sqlite"


@pytest.fixture
def db_url(db_path: Path) -> str:
    return sqlite_url(db_path)


@pytest.fixture
def engine(db_url: str) -> Iterator[Engine]:
    eng = create_sqlite_engine(db_url)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def created_schema(engine: Engine) -> Engine:
    """A database with the full head schema created directly from the ORM metadata."""
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session_factory(created_schema: Engine) -> sessionmaker[Session]:
    return build_session_factory(created_schema)


@pytest.fixture
def make_uow(
    session_factory: sessionmaker[Session],
) -> Callable[[], SqlAlchemyUnitOfWork]:
    return lambda: SqlAlchemyUnitOfWork(session_factory)


@pytest.fixture
def store(tmp_path: Path) -> LocalFileStore:
    return LocalFileStore(tmp_path / "app-data")
