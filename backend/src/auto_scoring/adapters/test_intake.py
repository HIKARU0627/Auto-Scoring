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

from auto_scoring.adapters.atomic import transactional_operation
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.models import ScoringMethod, Test
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_intake import (
    IntakeLimits,
    PdfCorruptedError,
    PdfEncryptedError,
    validate_page_count,
    validate_upload_bytes,
)


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
        with transactional_operation(uow, store) as staged:
            uow.tests.add(test)
            staged.add(store.test_model_answer_pdf_path(test.id), model_answer_data)
            staged.add(store.test_manual_pdf_path(test.id), manual_data)

    return test
