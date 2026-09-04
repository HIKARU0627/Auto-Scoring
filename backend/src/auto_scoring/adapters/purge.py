"""Bulk delete for a test or a single submission, with an audit-log entry.

Business rules require a bulk-delete feature whose unit is test / submission /
everything, that removes the source PDF, generated files, DB rows and related AI
logs together, and that records the delete operation itself in the audit log
(business-rules-and-evaluation-data.md §2 (11)).

Order of operations: write the audit row and delete the DB rows in one
transaction (foreign keys cascade to questions, submissions, results,
annotations, reviews and jobs), then delete the files. If the file delete is
interrupted, the DB rows are already gone and the leftover directory is inert;
re-running the purge (or deleting the directory by hand) finishes the job. The
recovery procedure is in `docs/data-model-and-local-storage.md`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.db.orm import OperationLogRow, SubmissionRow, TestRow


def _audit(
    uow: SqlAlchemyUnitOfWork,
    *,
    occurred_at: datetime,
    operation: str,
    target_kind: str,
    target_id: str,
    detail: str | None,
) -> None:
    uow.session.add(
        OperationLogRow(
            id=uuid4().hex,
            occurred_at=occurred_at,
            operation=operation,
            target_kind=target_kind,
            target_id=target_id,
            detail=detail,
        )
    )


def purge_test(
    uow: SqlAlchemyUnitOfWork,
    store: LocalFileStore,
    *,
    test_id: str,
    occurred_at: datetime,
    detail: str | None = None,
) -> None:
    """Delete a test, its questions/submissions/results/logs, and its files."""
    session = uow.session
    row = session.get(TestRow, test_id)
    if row is None:
        raise LookupError(f"test {test_id!r} not found")
    submission_ids = list(
        session.scalars(select(SubmissionRow.id).where(SubmissionRow.test_id == test_id))
    )
    _audit(
        uow,
        occurred_at=occurred_at,
        operation="purge_test",
        target_kind="test",
        target_id=test_id,
        detail=detail,
    )
    session.delete(row)
    uow.commit()

    store.delete_test(test_id)
    for submission_id in submission_ids:
        store.delete_submission(submission_id)


def purge_submission(
    uow: SqlAlchemyUnitOfWork,
    store: LocalFileStore,
    *,
    submission_id: str,
    occurred_at: datetime,
    detail: str | None = None,
) -> None:
    """Delete one submission, its results/annotations/reviews/jobs, and its files."""
    session = uow.session
    row = session.get(SubmissionRow, submission_id)
    if row is None:
        raise LookupError(f"submission {submission_id!r} not found")
    _audit(
        uow,
        occurred_at=occurred_at,
        operation="purge_submission",
        target_kind="submission",
        target_id=submission_id,
        detail=detail,
    )
    session.delete(row)
    uow.commit()

    store.delete_submission(submission_id)
