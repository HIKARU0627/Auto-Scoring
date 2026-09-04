"""Defer file writes until the database transaction commits successfully.

``transactional_operation`` yields a :class:`StagedFiles` buffer. File bytes
handed to it are held in memory until *after* the Unit of Work commits; only
then are they written (each one atomically, via
:meth:`LocalFileStore.write_atomic`). If the body raises, or the commit fails,
the Unit of Work is rolled back and nothing is written — so a failed
database transaction leaves neither half-inserted rows nor stray files (issue
#11 verification, fault injection). SQLite and the filesystem do not share a
transaction: a file-write failure after the commit is propagated for recovery,
but cannot roll the committed database transaction back.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork


@dataclass
class StagedFiles:
    """Collects ``(path, bytes)`` to write only once the DB commit succeeds."""

    store: LocalFileStore
    _pending: list[tuple[Path, bytes]] = field(default_factory=list)

    def add(self, path: Path, data: bytes) -> None:
        self._pending.append((path, data))

    def _finalize(self) -> list[Path]:
        return [self.store.write_atomic(path, data) for path, data in self._pending]

    def _discard(self) -> None:
        self._pending.clear()


@contextmanager
def transactional_operation(
    uow: SqlAlchemyUnitOfWork, store: LocalFileStore
) -> Iterator[StagedFiles]:
    staged = StagedFiles(store)
    try:
        yield staged
        uow.commit()
    except BaseException:
        uow.rollback()
        staged._discard()
        raise
    staged._finalize()
