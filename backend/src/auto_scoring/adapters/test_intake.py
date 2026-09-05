"""Validate, store, and register a new test's two PDFs (Issue #16).

Mirrors `adapters.submission_intake`'s validate-then-store shape, but for the
two registration PDFs (model answer + marking manual) instead of one answer
PDF: no OCR/answer-area extraction happens here, only the same PDF-safety
checks (`domain.pdf_intake`) followed by an atomic write of both files plus
the new `Test` row (`adapters.atomic.transactional_operation`: the DB commit
happens before either file is written, so a failure leaves neither a row nor
a file behind).
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from auto_scoring.adapters.atomic import FinalizationError, transactional_operation
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf.text_layout_extraction import extract_text_lines
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.models import ScoringMethod, Test, TestStatus
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_intake import (
    IntakeLimits,
    PdfCorruptedError,
    PdfEncryptedError,
    PdfGeometryError,
    validate_page_count,
    validate_upload_bytes,
)

#: Marks a `Test` directory as having gone through `register_test` at least
#: once -- written before the DB commit, never removed. Its only purpose is
#: to let `repair_incomplete_test_registrations` tell a test created by
#: *this* Issue's PDF-based registration flow apart from one that predates
#: it entirely (migration 0008 backfills `status='draft'` onto every
#: pre-existing row, none of which were ever registered with PDFs -- see
#: that function's own docstring). A permanent tag, not a "still pending"
#: flag: once both PDFs are also on disk, the row is a normal, complete
#: registration regardless of whether this file is still there.
_REGISTRATION_MARKER_FILENAME = ".registration-marker"


def _registration_marker_path(store: LocalFileStore, test_id: str) -> Path:
    return store.test_dir(test_id) / _REGISTRATION_MARKER_FILENAME


def _validate_one_pdf(pdf_engine: PdfEngine, path: Path, limits: IntakeLimits) -> None:
    try:
        encrypted = pdf_engine.is_encrypted(path)
    except Exception as exc:  # pypdf's parse errors are not our concern to enumerate
        raise PdfCorruptedError(f"could not parse PDF: {exc}") from exc
    if encrypted:
        raise PdfEncryptedError("PDF is password protected")
    try:
        page_count = pdf_engine.page_count(path)
    except Exception as exc:
        raise PdfCorruptedError(f"could not parse PDF: {exc}") from exc
    validate_page_count(page_count, limits)
    # Page count alone doesn't catch every malformed PDF: a page whose
    # CropBox/MediaBox don't intersect, or whose /Rotate is not a multiple
    # of 90, makes `PdfEngine.page_geometry` raise a `ValueError` (see
    # `adapters.pdf.pdfium_pypdf_engine.PageGeometry`'s own validation) --
    # but nothing here called it, so registration would persist the test
    # anyway and only discover the problem the first time `/profile/analyze`
    # calls `page_geometry` and gets an unhandled 500, leaving an unusable
    # draft behind (Issue #16 review). Validate every page now, while
    # intake can still reject it as a normal `PdfIntakeError` instead.
    for page_index in range(page_count):
        try:
            pdf_engine.page_geometry(path, page_index)
        except ValueError as exc:
            raise PdfGeometryError(f"page {page_index + 1} has invalid geometry: {exc}") from exc
        except Exception as exc:
            # `page_geometry` (pypdf) can fail in ways other than the
            # `ValueError` its own box-validation raises -- e.g. `KeyError`/
            # `TypeError` resolving an inherited MediaBox/CropBox/rotation
            # through a broken page tree, or one of pypdf's own parse
            # errors. None of those are a "the geometry is invalid" problem
            # this test should carry `PdfGeometryError`'s more specific
            # message; they mean the page itself couldn't be read (Issue
            # #16 review round 7).
            raise PdfCorruptedError(
                f"could not determine page {page_index + 1}'s geometry: {exc}"
            ) from exc
        try:
            # `page_geometry`/`page_count`/`is_encrypted` above are all
            # pypdf-backed, but `generate_profile_candidates` (the first
            # thing that will actually read this file's text, via
            # `_question_blocks`) uses pypdfium2 directly -- pypdf can
            # parse, and silently repair, a PDF whose structure pypdfium2's
            # own stricter parser refuses outright. Without exercising that
            # exact code path here, such a file would pass intake, get
            # persisted, and only fail once `/profile/analyze` calls it,
            # leaving a persisted draft with no profile and no documented
            # way back in (docs/test-registration.md's "不正PDFを安全に
            # 拒否する" contract must hold at intake, not partway through
            # analysis -- Issue #16 review round 7).
            extract_text_lines(path, page_index)
        except Exception as exc:
            raise PdfCorruptedError(
                f"page {page_index + 1} could not be parsed with pdfium: {exc}"
            ) from exc


def register_test(
    uow: SqlAlchemyUnitOfWork,
    store: LocalFileStore,
    pdf_engine: PdfEngine,
    *,
    name: str,
    subject: str | None,
    model_answer_filename: str,
    model_answer_mime: str | None,
    model_answer_data: bytes,
    manual_filename: str,
    manual_mime: str | None,
    manual_data: bytes,
    limits: IntakeLimits | None = None,
    now: datetime,
    id_factory: Callable[[], str] = lambda: uuid4().hex,
) -> Test:
    """Validate both PDFs, then create the `Test` row and store both files.

    Raises a `PdfIntakeError` subclass for either PDF's validation failure --
    neither PDF is stored and no `Test` row is created in that case.
    """
    limits = limits or IntakeLimits()
    validate_upload_bytes(
        filename=model_answer_filename,
        declared_mime=model_answer_mime,
        data=model_answer_data,
        limits=limits,
    )
    validate_upload_bytes(
        filename=manual_filename, declared_mime=manual_mime, data=manual_data, limits=limits
    )

    with tempfile.TemporaryDirectory(prefix="auto-scoring-test-intake-") as scratch_dir:
        model_answer_scratch = Path(scratch_dir) / "model-answer.pdf"
        manual_scratch = Path(scratch_dir) / "manual.pdf"
        model_answer_scratch.write_bytes(model_answer_data)
        manual_scratch.write_bytes(manual_data)

        _validate_one_pdf(pdf_engine, model_answer_scratch, limits)
        _validate_one_pdf(pdf_engine, manual_scratch, limits)

        test = Test(
            id=id_factory(),
            name=name,
            subject=subject,
            default_scoring_method=ScoringMethod.ADDITIVE,
            created_at=now,
        )
        # Written before the DB commit below (and independent of the two
        # PDFs' own staged writes) so it exists even if this attempt gets no
        # further than that commit -- see `_REGISTRATION_MARKER_FILENAME`'s
        # docstring for why `repair_incomplete_test_registrations` needs
        # this signal to exist regardless of whether the PDFs ever reach
        # disk.
        store.write_atomic(_registration_marker_path(store, test.id), b"")
        try:
            with transactional_operation(uow, store) as staged:
                uow.tests.add(test)
                staged.add(store.test_model_answer_pdf_path(test.id), model_answer_data)
                staged.add(store.test_manual_pdf_path(test.id), manual_data)
        except FinalizationError:
            # The Test row already committed (transactional_operation only
            # guarantees "DB commit before file write", not that the write
            # also succeeds) but one or both PDFs failed to reach disk (full
            # disk, permissions, ...). Left alone, this id would linger
            # forever as a `draft` test with missing files -- unusable
            # (neither PDF can be analyzed) and, since the caller never
            # received this id (the request as a whole is about to raise),
            # unreachable for a retry too. Compensate by removing the
            # now-file-less row in a fresh transaction on the same
            # already-committed session, and any partial file (e.g. the
            # model-answer PDF, staged before a failing manual PDF) that did
            # reach disk -- an orphaned file with no owning row would never
            # be cleaned up by anything else. The client's only path forward
            # is to submit the two PDFs again, which mints a fresh id anyway.
            uow.tests.delete(test.id)
            uow.commit()
            store.delete_test(test.id)
            raise

    return test


def repair_incomplete_test_registrations(
    uow: SqlAlchemyUnitOfWork, store: LocalFileStore
) -> list[str]:
    """Delete any `DRAFT` test that went through `register_test` but whose
    registration PDF(s) are missing on disk.

    `register_test`'s own `FinalizationError` handler above already
    compensates for a failed PDF write within the same request/process --
    but a process crash or power loss between `transactional_operation`'s DB
    commit and those file writes completing leaves the same broken state
    with no exception handler ever running to notice, exactly like
    `submission_intake.repair_incomplete_submissions` covers for submissions
    (see its own docstring). Unlike a `Submission`, `Test` has no
    intermediate `error` state to move into: a test missing either
    registration PDF cannot be analyzed at all, so (matching what
    `register_test`'s own compensation above already does) the only usable
    recovery is to delete the row outright -- the client's next step is to
    submit the two PDFs again, which mints a fresh id anyway. Call this once
    at startup (`api/app.py::create_app`), the same way
    `LocalFileStore.sweep_temp`/`repair_incomplete_submissions` catch what a
    prior run left in this state before it could shut down cleanly.

    Gated on `_REGISTRATION_MARKER_FILENAME`, not merely "PDFs missing" --
    migration 0008 backfills `status='draft'` onto every `Test` row that
    predates this Issue's PDF-based registration flow, none of which were
    ever registered with PDFs to begin with. An earlier version of this
    function used "PDFs missing" alone as the trigger, which classified
    every such pre-existing row as an interrupted registration and deleted
    it -- cascading to its Questions and Submissions -- on the first
    startup after upgrading a production database past that migration
    (Issue #16 review round 5, data-loss). Only a row the marker's own
    docstring says went through `register_test` is ever a candidate here.

    Only ever considers `DRAFT` tests: a test cannot reach `READY` without
    both PDFs already having been readable (`/profile/analyze` reads them
    directly), so a `READY` test missing either file would be a different,
    later problem this sweep does not attempt to diagnose.

    Returns the ids removed this way.
    """
    removed: list[str] = []
    for test in uow.tests.list_all():
        if test.status is not TestStatus.DRAFT:
            continue
        if not _registration_marker_path(store, test.id).is_file():
            continue
        expected_paths = (
            store.test_model_answer_pdf_path(test.id),
            store.test_manual_pdf_path(test.id),
        )
        if all(path.is_file() for path in expected_paths):
            continue
        uow.tests.delete(test.id)
        uow.commit()
        store.delete_test(test.id)
        removed.append(test.id)
    return removed
