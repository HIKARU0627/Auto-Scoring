"""Unit tests for `adapters.test_intake.register_test` (Issue #16)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.atomic import FinalizationError
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf import PdfiumPypdfEngine
from auto_scoring.adapters.test_intake import register_test, repair_incomplete_test_registrations
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_geometry import NormalizedPoint, PageGeometry
from auto_scoring.domain.pdf_intake import PdfCorruptedError, PdfGeometryError
from tests.support import at, make_test

_ENGINE = PdfiumPypdfEngine()


class _BadGeometryPdfEngine:
    """Delegates to a real `PdfEngine`, but `page_geometry` always raises
    `exc` -- standing in for a PDF whose CropBox/MediaBox don't intersect,
    or whose `/Rotate` isn't a multiple of 90 (`PageGeometry.__post_init__`,
    a `ValueError`), or one whose page tree is broken in some other way
    pypdf's own box/rotation lookups surface as a different exception type
    entirely (`KeyError`, `TypeError`, one of pypdf's own parse errors --
    Issue #16 review round 7).
    """

    def __init__(self, delegate: PdfEngine, *, exc: Exception | None = None) -> None:
        self._delegate = delegate
        self._exc = exc or ValueError("crop dimensions must be positive")

    def page_count(self, source: Path) -> int:
        return self._delegate.page_count(source)

    def is_encrypted(self, source: Path) -> bool:
        return self._delegate.is_encrypted(source)

    def page_geometry(self, source: Path, page_index: int) -> PageGeometry:
        raise self._exc

    def render_page_png(self, source: Path, page_index: int, *, scale: float) -> bytes:
        return self._delegate.render_page_png(source, page_index, scale=scale)

    def stamp_markers(
        self,
        source: Path,
        destination: Path,
        markers: Mapping[int, Sequence[NormalizedPoint]],
        *,
        mark_size_pt: float = 8.0,
    ) -> None:
        self._delegate.stamp_markers(source, destination, markers, mark_size_pt=mark_size_pt)


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


def test_rejects_a_pdf_with_invalid_page_geometry(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    """Page count alone doesn't catch a CropBox/MediaBox that don't
    intersect or an invalid `/Rotate` -- without validating geometry at
    intake, registration would persist the test anyway and only discover
    the problem the first time `/profile/analyze` calls `page_geometry`
    and hits an unhandled 500 (Issue #16 review round 4).
    """
    with (
        SqlAlchemyUnitOfWork(session_factory) as uow,
        pytest.raises(PdfGeometryError),
    ):
        register_test(
            uow,
            store,
            _BadGeometryPdfEngine(_ENGINE),
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


@pytest.mark.parametrize("exc", [KeyError("/MediaBox"), TypeError("not a rectangle")])
def test_rejects_a_pdf_whose_geometry_lookup_fails_with_a_non_value_error(
    store: LocalFileStore, session_factory: sessionmaker[Session], exc: Exception
) -> None:
    """`page_geometry` (pypdf) can fail resolving an inherited MediaBox/
    CropBox/rotation through a broken page tree with something other than
    the `ValueError` its own box-validation raises. Before this, such a
    failure sailed past the `except ValueError` guard entirely and
    surfaced as an unhandled 500 from `POST /tests` (Issue #16 review
    round 7).
    """
    with (
        SqlAlchemyUnitOfWork(session_factory) as uow,
        pytest.raises(PdfCorruptedError),
    ):
        register_test(
            uow,
            store,
            _BadGeometryPdfEngine(_ENGINE, exc=exc),
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


def test_rejects_a_pdf_pypdf_accepts_but_pdfium_cannot_extract_text_from(
    store: LocalFileStore,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pypdf can parse -- and silently repair -- a PDF whose structure
    pypdfium2 refuses outright. `generate_profile_candidates` (the first
    thing that actually reads this file's text, once `/profile/analyze` is
    called) uses pypdfium2 directly, not the `PdfEngine` abstraction
    exercised above -- so a file that only pypdfium2 rejects must be
    caught at intake too, before the `Test` row and its PDFs are
    persisted, or the resulting draft has no profile and no documented way
    back in (Issue #16 review round 7).
    """
    import auto_scoring.adapters.test_intake as test_intake_module

    def failing_extract_text_lines(path: Path, page_index: int) -> list[object]:
        raise RuntimeError("simulated pdfium parse failure")

    monkeypatch.setattr(test_intake_module, "extract_text_lines", failing_extract_text_lines)

    with (
        SqlAlchemyUnitOfWork(session_factory) as uow,
        pytest.raises(PdfCorruptedError),
    ):
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
    # `repair_incomplete_test_registrations` relies on this marker to tell a
    # test created through this flow apart from one that predates it
    # entirely (Issue #16 review round 5) -- a normal registration must
    # leave it behind.
    assert (store.test_dir(test.id) / ".registration-marker").is_file()


def test_repair_leaves_a_pre_existing_test_without_the_marker_alone(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    """Migration 0011 backfills `status='draft'` onto every `Test` row that
    predates this Issue's PDF-based registration flow, none of which ever
    went through `register_test` -- so none of them have its registration
    marker, and none of them ever had PDFs to begin with. An earlier version
    of this sweep used "PDFs missing" alone as its trigger, which classified
    every such pre-existing row as an interrupted registration and deleted
    it -- cascading to its Questions and Submissions -- on the first startup
    after upgrading a production database past that migration (Issue #16
    review round 5, data loss).
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test(id="legacy-test"))
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        removed = repair_incomplete_test_registrations(uow, store)

    assert removed == []
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.tests.get("legacy-test") is not None


def test_repair_removes_a_marked_test_left_incomplete_by_a_prior_crash(
    store: LocalFileStore, session_factory: sessionmaker[Session]
) -> None:
    """Unlike the pre-existing-row case above, a test that *does* carry the
    registration marker but is still missing a PDF really did go through
    `register_test` and really was interrupted -- the sweep must still
    catch that (this is `repair_incomplete_test_registrations` itself,
    isolated from the process-crash simulation
    `test_a_finalization_failure_does_not_leave_a_permanently_broken_draft`
    already covers via a failing `write_atomic`).
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        test = register_test(
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
    store.test_manual_pdf_path(test.id).unlink()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        removed = repair_incomplete_test_registrations(uow, store)

    assert removed == [test.id]
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.tests.get(test.id) is None
