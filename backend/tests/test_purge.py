"""Bulk delete cascades DB rows, removes files, and records an audit-log entry."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.purge import purge_submission, purge_test
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.db.orm import GradeResultRow, OperationLogRow, SubmissionRow
from tests.support import at, make_grade, make_question, make_submission, make_test

UowFactory = Callable[[], SqlAlchemyUnitOfWork]


def _rows(uow: SqlAlchemyUnitOfWork, row_type: type[SubmissionRow] | type[GradeResultRow]) -> int:
    return len(uow.session.scalars(select(row_type)).all())


def _audit(uow: SqlAlchemyUnitOfWork) -> list[tuple[str, str]]:
    return [
        (e.operation, e.target_id)
        for e in uow.session.scalars(select(OperationLogRow).order_by(OperationLogRow.occurred_at))
    ]


def _seed(make_uow: UowFactory, store: LocalFileStore) -> None:
    with make_uow() as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question())
        uow.submissions.add(make_submission())
        uow.grades.add(make_grade())
        uow.commit()
    store.write_atomic(store.test_dir("test-1") / "model-answer.pdf", b"x")
    store.write_atomic(store.submission_dir("sub-1") / "source.pdf", b"y")


def test_purge_test_removes_rows_files_and_logs_the_operation(
    make_uow: UowFactory, store: LocalFileStore
) -> None:
    _seed(make_uow, store)

    with make_uow() as uow:
        purge_test(uow, store, test_id="test-1", occurred_at=at(100), detail="year-end cleanup")

    assert not store.test_dir("test-1").exists()
    assert not store.submission_dir("sub-1").exists()
    with make_uow() as uow:
        assert _rows(uow, SubmissionRow) == 0
        assert _rows(uow, GradeResultRow) == 0  # cascaded
        assert _audit(uow) == [("purge_test", "test-1")]


def test_purge_submission_leaves_the_test_intact(
    make_uow: UowFactory, store: LocalFileStore
) -> None:
    _seed(make_uow, store)

    with make_uow() as uow:
        purge_submission(uow, store, submission_id="sub-1", occurred_at=at(200))

    assert not store.submission_dir("sub-1").exists()
    assert store.test_dir("test-1").exists()
    with make_uow() as uow:
        assert uow.tests.get("test-1") is not None
        assert _rows(uow, SubmissionRow) == 0
        assert _rows(uow, GradeResultRow) == 0
        assert _audit(uow) == [("purge_submission", "sub-1")]
