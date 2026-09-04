"""Answer-PDF intake pipeline (Issue #17): validate -> store -> preprocess.

Orchestrates the domain rules in ``domain.pdf_intake`` / ``domain.submission_intake``
with the concrete ``PdfEngine`` / ``ImagePreprocessor`` adapters, the SQLite
``UnitOfWork`` and ``LocalFileStore`` -- following the same shape as
``adapters/purge.py``: a plain function the API layer calls with its
dependencies, not a class hierarchy.

Ordering guarantee (Issue #17 acceptance: "不正/暗号化/破損PDFを安全に拒否し、
中途半端なDB/fileを残さない"):

1. Everything checkable from the raw bytes (filename, mime, size, magic bytes)
   is validated *before* any I/O.
2. The upload is written to a scratch temp file (outside ``app-data/``) so
   ``PdfEngine`` can open it to check encryption/page count/corruption.
3. Only once every check has passed does anything reach ``app-data/`` or the
   database, and even then via ``adapters.atomic.transactional_operation``:
   files are staged in memory and written only after the DB transaction
   commits, so a failure anywhere leaves neither a partial DB row nor a
   partial file.
"""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from auto_scoring.adapters.atomic import StagedFiles, transactional_operation
from auto_scoring.adapters.image.opencv_preprocessor import crop_normalized_rect
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.image_preprocess import ImagePreprocessor
from auto_scoring.domain.models import (
    AnswerImage,
    AnswerImageStatus,
    Question,
    Submission,
    SubmissionState,
)
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_intake import (
    IntakeLimits,
    PdfCorruptedError,
    PdfEncryptedError,
    validate_page_count,
    validate_upload_bytes,
)
from auto_scoring.domain.submission_intake import (
    PageCoverage,
    ReintakeDecision,
    decide_reintake,
    describe_coverage_issue,
)

#: Rasterization scale (pixels per PDF point) for both the preview image and
#: the answer-area crop source. Matches simplified-design-spec.md §7.1's
#: "拡大縮小補正": every page is normalized to the same scale regardless of
#: its physical size, rather than post-hoc resizing a variably-sized raster.
RENDER_SCALE = 2.0


class DuplicateSubmissionError(Exception):
    """The same PDF bytes were already submitted for this test (Issue #17
    "同一PDFの再取込方針" -- see ``docs/answer-intake-and-preprocessing.md`` §2)."""

    def __init__(self, existing_submission_id: str) -> None:
        super().__init__(
            f"an identical PDF was already submitted as submission {existing_submission_id!r}"
        )
        self.existing_submission_id = existing_submission_id


@dataclass(frozen=True, kw_only=True)
class SubmissionIntakeResult:
    submission: Submission
    answer_images: tuple[AnswerImage, ...]
    is_retry: bool


def intake_submission(
    uow: SqlAlchemyUnitOfWork,
    store: LocalFileStore,
    pdf_engine: PdfEngine,
    image_preprocessor: ImagePreprocessor,
    *,
    test_id: str,
    filename: str,
    declared_mime: str | None,
    data: bytes,
    student_label: str | None = None,
    limits: IntakeLimits | None = None,
    now: datetime,
    id_factory: Callable[[], str] = lambda: uuid4().hex,
) -> SubmissionIntakeResult:
    """Validate, store and preprocess one answer PDF for ``test_id``.

    Raises :class:`~auto_scoring.domain.pdf_intake.PdfIntakeError` subclasses
    for a bad upload, :class:`LookupError` when ``test_id`` doesn't exist, and
    :class:`DuplicateSubmissionError` when the same content already exists for
    this test in a non-retryable state. None of these leave a DB row or a file
    behind.
    """
    limits = limits or IntakeLimits()
    validate_upload_bytes(filename=filename, declared_mime=declared_mime, data=data, limits=limits)

    test = uow.tests.get(test_id)
    if test is None:
        raise LookupError(f"test {test_id!r} not found")

    with tempfile.TemporaryDirectory(prefix="auto-scoring-intake-") as scratch_dir:
        scratch_path = Path(scratch_dir) / "upload.pdf"
        scratch_path.write_bytes(data)

        try:
            encrypted = pdf_engine.is_encrypted(scratch_path)
        except Exception as exc:  # pypdf's parse errors are not our concern to enumerate
            raise PdfCorruptedError(f"could not parse PDF: {exc}") from exc
        if encrypted:
            raise PdfEncryptedError("PDF is password protected")

        try:
            page_count = pdf_engine.page_count(scratch_path)
        except Exception as exc:
            raise PdfCorruptedError(f"could not parse PDF: {exc}") from exc
        validate_page_count(page_count, limits)

        content_hash = hashlib.sha256(data).hexdigest()
        existing = uow.submissions.find_by_content_hash(test_id, content_hash)
        decision = decide_reintake(existing)
        if decision is ReintakeDecision.REJECT_DUPLICATE:
            assert existing is not None
            raise DuplicateSubmissionError(existing.id)

        is_retry = decision is ReintakeDecision.RETRY_EXISTING
        submission_id = existing.id if is_retry and existing is not None else id_factory()

        questions = uow.questions.list_for_test(test_id)
        expected_pages = tuple(sorted({q.page for q in questions}))
        coverage = PageCoverage(expected_pages=expected_pages, actual_page_count=page_count)
        coverage_issue = describe_coverage_issue(coverage)

        with transactional_operation(uow, store) as staged:
            raw_png_cache: dict[int, bytes] = {}

            def raw_page_png(page: int) -> bytes:
                if page not in raw_png_cache:
                    raw_png_cache[page] = pdf_engine.render_page_png(
                        scratch_path, page - 1, scale=RENDER_SCALE
                    )
                return raw_png_cache[page]

            for page in range(1, page_count + 1):
                preview = image_preprocessor.preprocess_page(raw_page_png(page))
                staged.add(store.submission_page_image_path(submission_id, page), preview.png_bytes)

            answer_images: list[AnswerImage] = []
            if not questions:
                submission_state = SubmissionState.NEEDS_REVIEW
                submission_review_reason = "no_questions_registered"
            elif coverage_issue is not None:
                submission_state = SubmissionState.NEEDS_REVIEW
                submission_review_reason = coverage_issue
            else:
                answer_images = _extract_answer_images(
                    questions=questions,
                    submission_id=submission_id,
                    raw_page_png=raw_page_png,
                    store=store,
                    staged=staged,
                    id_factory=id_factory,
                    now=now,
                )
                any_needs_review = any(
                    image.status is AnswerImageStatus.NEEDS_REVIEW for image in answer_images
                )
                if any_needs_review:
                    submission_state = SubmissionState.NEEDS_REVIEW
                    flagged = ",".join(
                        image.question_id
                        for image in answer_images
                        if image.status is AnswerImageStatus.NEEDS_REVIEW
                    )
                    submission_review_reason = f"answer_area_undefined:{flagged}"
                else:
                    submission_state = SubmissionState.AI_PROCESSED
                    submission_review_reason = None

            source_pdf_full_path = store.submission_source_pdf_path(submission_id)
            source_pdf_path = str(source_pdf_full_path.relative_to(store.root)).replace("\\", "/")
            staged.add(source_pdf_full_path, data)

            if is_retry:
                uow.submissions.mark_intake_outcome(
                    submission_id, SubmissionState.UNPROCESSED, None
                )
            else:
                new_submission = Submission(
                    id=submission_id,
                    test_id=test_id,
                    source_pdf_path=source_pdf_path,
                    source_pdf_sha256=content_hash,
                    page_count=page_count,
                    created_at=now,
                    state=SubmissionState.UNPROCESSED,
                    student_label=student_label,
                    original_filename=filename,
                )
                uow.submissions.add(new_submission)

            # UNPROCESSED -> AI_PROCESSING -> AI_PROCESSED: image preprocessing/answer-area
            # extraction *is* the "AI_PROCESSING" phase of the state machine (§25) -- OCR/AI
            # grading (a later issue) continues from AI_PROCESSED. Only then can the state
            # machine reach NEEDS_REVIEW, so a coverage/extraction problem takes one more hop.
            uow.submissions.mark_intake_outcome(submission_id, SubmissionState.AI_PROCESSING, None)
            uow.submissions.mark_intake_outcome(submission_id, SubmissionState.AI_PROCESSED, None)
            if submission_state is SubmissionState.NEEDS_REVIEW:
                uow.submissions.mark_intake_outcome(
                    submission_id, SubmissionState.NEEDS_REVIEW, submission_review_reason
                )

            uow.answer_images.replace_for_submission(submission_id, answer_images)

            final = uow.submissions.get(submission_id)
            assert final is not None

        return SubmissionIntakeResult(
            submission=final, answer_images=tuple(answer_images), is_retry=is_retry
        )


def _extract_answer_images(
    *,
    questions: list[Question],
    submission_id: str,
    raw_page_png: Callable[[int], bytes],
    store: LocalFileStore,
    staged: StagedFiles,
    id_factory: Callable[[], str],
    now: datetime,
) -> list[AnswerImage]:
    """Crop each question's answer area from the untouched page raster.

    A question with no confirmed ``answer_area`` (test registration hasn't
    defined one yet) falls back to the full page preview image, marked
    ``NEEDS_REVIEW`` -- simplified-design-spec.md §24 "回答欄検出失敗は…元画像
    を人間へ提示する".
    """
    images: list[AnswerImage] = []
    for question in questions:
        if question.answer_area is None:
            image_path = store.submission_page_image_path(submission_id, question.page)
            status = AnswerImageStatus.NEEDS_REVIEW
            reason: str | None = "no_answer_area_defined"
        else:
            cropped = crop_normalized_rect(raw_page_png(question.page), question.answer_area)
            image_path = store.submission_question_image_path(submission_id, question.id)
            staged.add(image_path, cropped)
            status = AnswerImageStatus.OK
            reason = None
        images.append(
            AnswerImage(
                id=id_factory(),
                submission_id=submission_id,
                question_id=question.id,
                page=question.page,
                image_path=str(image_path.relative_to(store.root)).replace("\\", "/"),
                status=status,
                reason=reason,
                created_at=now,
            )
        )
    return images
