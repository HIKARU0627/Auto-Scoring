"""Fault injection: a failed transaction leaves neither DB rows nor files behind."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from auto_scoring.adapters.atomic import transactional_operation
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from tests.support import make_grade, make_question, make_submission, make_test

UowFactory = Callable[[], SqlAlchemyUnitOfWork]


class InjectedFailure(RuntimeError):
    pass


def _seed_parents(make_uow: UowFactory) -> None:
    with make_uow() as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question())
        uow.commit()


def test_success_commits_rows_and_writes_files(make_uow: UowFactory, store: LocalFileStore) -> None:
    _seed_parents(make_uow)
    pdf_path = store.submission_dir("sub-1") / "source.pdf"

    with make_uow() as uow, transactional_operation(uow, store) as files:
        uow.submissions.add(make_submission())
        uow.grades.add(make_grade())
        files.add(pdf_path, b"%PDF-1.7")

    assert pdf_path.read_bytes() == b"%PDF-1.7"
    with make_uow() as uow:
        assert uow.submissions.get("sub-1") is not None
        assert len(uow.grades.history("sub-1", "q-1")) == 1


def test_exception_in_body_rolls_back_and_writes_nothing(
    make_uow: UowFactory, store: LocalFileStore
) -> None:
    _seed_parents(make_uow)
    pdf_path = store.submission_dir("sub-1") / "source.pdf"

    with (
        pytest.raises(InjectedFailure),
        make_uow() as uow,
        transactional_operation(uow, store) as files,
    ):
        uow.submissions.add(make_submission())
        files.add(pdf_path, b"%PDF-1.7")
        raise InjectedFailure

    assert not pdf_path.exists()
    assert list(store.root.rglob("*.part")) == []
    with make_uow() as uow:
        assert uow.submissions.get("sub-1") is None


def test_commit_failure_writes_no_files(
    make_uow: UowFactory, store: LocalFileStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_parents(make_uow)
    pdf_path = store.submission_dir("sub-1") / "source.pdf"

    with make_uow() as uow:

        def fail_commit() -> None:
            raise InjectedFailure("commit failed")

        monkeypatch.setattr(uow, "commit", fail_commit)

        with pytest.raises(InjectedFailure), transactional_operation(uow, store) as files:
            uow.submissions.add(make_submission())
            files.add(pdf_path, b"%PDF-1.7")

    assert not pdf_path.exists()
    with make_uow() as uow:
        assert uow.submissions.get("sub-1") is None
