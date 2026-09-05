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
from auto_scoring.domain.pdf_intake import StagedOutputTooLargeError


@dataclass
class StagedFiles:
    """Collects ``(path, bytes)`` to write only once the DB commit succeeds.

    ``max_total_bytes``, when set, bounds the running total of every ``data``
    handed to :meth:`add` -- not just one call's size -- since these bytes all
    sit in memory together until the commit that triggers :meth:`_finalize`
    (see :class:`~auto_scoring.domain.pdf_intake.StagedOutputTooLargeError`).
    """

    store: LocalFileStore
    max_total_bytes: int | None = None
    _pending: list[tuple[Path, bytes]] = field(default_factory=list)
    _total_bytes: int = 0

    def add(self, path: Path, data: bytes) -> None:
        self._total_bytes += len(data)
        if self.max_total_bytes is not None and self._total_bytes > self.max_total_bytes:
            raise StagedOutputTooLargeError(self._total_bytes, self.max_total_bytes)
        self._pending.append((path, data))

    def _finalize(self) -> list[Path]:
        return [self.store.write_atomic(path, data) for path, data in self._pending]

    def _discard(self) -> None:
        self._pending.clear()


@contextmanager
def transactional_operation(
    uow: SqlAlchemyUnitOfWork, store: LocalFileStore, *, max_staged_bytes: int | None = None
) -> Iterator[StagedFiles]:
    staged = StagedFiles(store, max_total_bytes=max_staged_bytes)
    try:
        yield staged
        uow.commit()
    except BaseException:
        uow.rollback()
        staged._discard()
        raise
    staged._finalize()
