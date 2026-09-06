"""Fault injection: a failed transaction leaves neither DB rows nor files behind."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from auto_scoring.adapters.atomic import transactional_operation
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.pdf_intake import StagedOutputTooLargeError
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


def test_max_staged_bytes_bounds_the_running_total_not_just_one_add(
    make_uow: UowFactory, store: LocalFileStore
) -> None:
    """Two 6-byte adds under an 8-byte cap: neither call alone is too big, but
    their running total is, so the second call must be the one that raises --
    proving the cap tracks the cumulative size in memory, not a single write.
    """
    _seed_parents(make_uow)

    with (
        pytest.raises(StagedOutputTooLargeError) as excinfo,
        make_uow() as uow,
        transactional_operation(uow, store, max_staged_bytes=8) as files,
    ):
        uow.submissions.add(make_submission())
        files.add(store.submission_dir("sub-1") / "a.png", b"a" * 6)
        files.add(store.submission_dir("sub-1") / "b.png", b"b" * 6)

    assert excinfo.value.total_bytes == 12
    assert excinfo.value.limit_bytes == 8
    assert list(store.root.rglob("*.png")) == []
    with make_uow() as uow:
        assert uow.submissions.get("sub-1") is None


def test_max_staged_bytes_none_means_unbounded(make_uow: UowFactory, store: LocalFileStore) -> None:
    _seed_parents(make_uow)
    pdf_path = store.submission_dir("sub-1") / "source.pdf"

    with make_uow() as uow, transactional_operation(uow, store, max_staged_bytes=None) as files:
        uow.submissions.add(make_submission())
        files.add(pdf_path, b"x" * 10_000)

    assert pdf_path.read_bytes() == b"x" * 10_000
