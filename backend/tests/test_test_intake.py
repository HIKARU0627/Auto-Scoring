"""Unit tests for `adapters.test_intake.register_test` (Issue #16)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.atomic import FinalizationError
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf import PdfiumPypdfEngine
from auto_scoring.adapters.test_intake import register_test
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from tests.support import at

_ENGINE = PdfiumPypdfEngine()


def _pdf_bytes(*, pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_a_finalization_failure_does_not_leave_a_permanently_broken_draft(
    store: LocalFileStore,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulates a disk-full/permissions failure writing one of the two
    registration PDFs, after the `Test` row already committed. Unlike a
    `Submission` (which has an `error` state to retry into), a `Test` has no
    such state -- so the only way to avoid a permanently unusable, file-less
    draft is to compensate by removing the row itself (Issue #16 review).
    """
    real_write_atomic = LocalFileStore.write_atomic

    def failing_write_atomic(self: LocalFileStore, path: Path, data: bytes) -> Path:
        if path.name == "manual.pdf":
            raise OSError("simulated disk-full failure")
        return real_write_atomic(self, path, data)

    monkeypatch.setattr(LocalFileStore, "write_atomic", failing_write_atomic)

    with SqlAlchemyUnitOfWork(session_factory) as uow, pytest.raises(FinalizationError):
        register_test(
            uow,
            store,
            _ENGINE,
            name="国語",
            subject=None,
            model_answer_filename="model-answer.pdf",
            model_answer_mime="application/pdf",
            model_answer_data=_pdf_bytes(),
            manual_filename="manual.pdf",
            manual_mime="application/pdf",
            manual_data=_pdf_bytes(),
            now=at(),
        )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.tests.list_all() == []


def test_a_finalization_failure_does_not_leave_orphaned_files(
    store: LocalFileStore,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model-answer PDF (staged before the failing manual PDF) must not
    be left on disk once the compensating delete removes the `Test` row it
    belonged to -- an orphaned file with no owning row would never be
    cleaned up by anything.
    """
    real_write_atomic = LocalFileStore.write_atomic
    written_test_ids: list[str] = []

    def failing_write_atomic(self: LocalFileStore, path: Path, data: bytes) -> Path:
        if path.name == "manual.pdf":
            raise OSError("simulated disk-full failure")
        if path.name == "model-answer.pdf":
            written_test_ids.append(path.parent.name)
        return real_write_atomic(self, path, data)

    monkeypatch.setattr(LocalFileStore, "write_atomic", failing_write_atomic)

    with SqlAlchemyUnitOfWork(session_factory) as uow, pytest.raises(FinalizationError):
        register_test(
            uow,
            store,
            _ENGINE,
            name="国語",
            subject=None,
            model_answer_filename="model-answer.pdf",
            model_answer_mime="application/pdf",
            model_answer_data=_pdf_bytes(),
            manual_filename="manual.pdf",
            manual_mime="application/pdf",
            manual_data=_pdf_bytes(),
            now=at(),
        )

    assert len(written_test_ids) == 1
    assert not (store.root / "tests" / written_test_ids[0]).exists()


def test_happy_path_registers_a_draft_test(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        test = register_test(
            uow,
            store,
            _ENGINE,
            name="国語",
            subject="国語",
            model_answer_filename="model-answer.pdf",
            model_answer_mime="application/pdf",
            model_answer_data=_pdf_bytes(),
            manual_filename="manual.pdf",
            manual_mime="application/pdf",
            manual_data=_pdf_bytes(),
            now=at(),
        )

    assert store.test_model_answer_pdf_path(test.id).exists()
    assert store.test_manual_pdf_path(test.id).exists()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.tests.get(test.id) is not None
