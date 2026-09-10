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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from auto_scoring.adapters.atomic import FinalizationError, StagedFiles, transactional_operation
from auto_scoring.adapters.image.ink import ink_coverage
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
    TestStatus,
)
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_intake import (
    IntakeLimits,
    PdfCorruptedError,
    PdfEncryptedError,
    validate_page_count,
    validate_render_dimensions,
    validate_upload_bytes,
)
from auto_scoring.domain.submission_intake import (
    NEARLY_BLANK_CROP_REASON,
    PageCoverage,
    ReintakeDecision,
    decide_reintake,
    describe_coverage_issue,
    is_nearly_blank_crop,
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


class TestNotReadyError(Exception):
    """The test exists but has not completed registration (Issue #16).

    A `draft` test's profile and/or dependency graph may still be
    unconfirmed or incomplete -- accepting submissions against it would let
    answer processing start before the lifecycle Issue #16 defines actually
    permits it (`docs/test-registration.md` "ready になる条件").
    """

    def __init__(self, test_id: str) -> None:
        super().__init__(f"test {test_id!r} is not ready to accept submissions yet")
        self.test_id = test_id


class SubmissionRetryConflictError(Exception):
    """Another request already claimed this errored submission for retry.

    ``decide_reintake``'s RETRY_EXISTING check and the actual claim
    (``SubmissionRepository.claim_for_retry``) aren't the same operation, so
    two concurrent retries of the same submission can both decide "this is
    retryable" before either claims it. Only one ``claim_for_retry`` call can
    ever return ``True`` (it's a conditional ``UPDATE ... WHERE state =
    'error'``); the loser raises this instead of running the full pipeline
    against a submission someone else is already reprocessing.
    """

    def __init__(self, submission_id: str) -> None:
        super().__init__(
            f"submission {submission_id!r} is already being retried by another request"
        )
        self.submission_id = submission_id


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
    if test.status is not TestStatus.READY:
        raise TestNotReadyError(test_id)

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

        # A page's declared MediaBox/CropBox can be enormous even in a tiny,
        # few-page file; render_page_png below allocates a raster sized from
        # it at RENDER_SCALE, so an absurd declared size must be rejected
        # *before* ever rendering, not discovered via an out-of-memory crash.
        for page in range(1, page_count + 1):
            try:
                geometry = pdf_engine.page_geometry(scratch_path, page - 1)
            except Exception as exc:
                raise PdfCorruptedError(f"could not parse PDF: {exc}") from exc
            validate_render_dimensions(
                geometry.displayed_width * RENDER_SCALE,
                geometry.displayed_height * RENDER_SCALE,
                limits,
            )

        content_hash = hashlib.sha256(data).hexdigest()
        existing = uow.submissions.find_by_content_hash(test_id, content_hash)
        has_downstream_processing = (
            existing is not None and uow.submissions.has_downstream_processing(existing.id)
        )
        decision = decide_reintake(existing, has_downstream_processing=has_downstream_processing)
        if decision is ReintakeDecision.REJECT_DUPLICATE:
            assert existing is not None
            raise DuplicateSubmissionError(existing.id)

        is_retry = decision is ReintakeDecision.RETRY_EXISTING
        submission_id = existing.id if is_retry and existing is not None else id_factory()

        questions = uow.questions.list_for_test(test_id)
        expected_pages = tuple(sorted({q.page for q in questions}))
        coverage = PageCoverage(expected_pages=expected_pages, actual_page_count=page_count)
        coverage_issue = describe_coverage_issue(coverage)
        # When coverage has an issue (e.g. extra_pages or missing_pages),
        # extracting answer images is skipped to present the whole page to a human.
        # Under Issue #215, grading jobs are not queued for such submissions,
        # keeping them in NEEDS_REVIEW waiting for human intervention.
        should_extract = bool(questions) and coverage_issue is None

        questions_by_page: dict[int, list[Question]] = {}
        if should_extract:
            for question in questions:
                questions_by_page.setdefault(question.page, []).append(question)

        try:
            final, answer_images = _write_submission(
                uow=uow,
                store=store,
                pdf_engine=pdf_engine,
                image_preprocessor=image_preprocessor,
                scratch_path=scratch_path,
                submission_id=submission_id,
                test_id=test_id,
                content_hash=content_hash,
                page_count=page_count,
                data=data,
                student_label=student_label,
                filename=filename,
                is_retry=is_retry,
                questions=questions,
                questions_by_page=questions_by_page,
                coverage_issue=coverage_issue,
                id_factory=id_factory,
                now=now,
                limits=limits,
            )
        except IntegrityError as exc:
            # Two concurrent requests can both see "no existing submission for
            # this hash" from find_by_content_hash above and both reach this
            # insert; the DB's own uq_submissions_test_content_hash constraint
            # (not just that earlier lookup) is what actually prevents two
            # rows, so the loser here reports the winner as a normal duplicate
            # rather than a raw DB error.
            if is_retry:
                raise
            winner = uow.submissions.find_by_content_hash(test_id, content_hash)
            if winner is None:
                raise
            raise DuplicateSubmissionError(winner.id) from exc
        except FinalizationError:
            # _write_submission's own transaction already committed the
            # submission as ai_processed/needs_review before this file write
            # failed (disk full, permissions, ...) -- that can't be rolled
            # back, so the row is otherwise stuck: decide_reintake would see
            # a non-error state and report a future re-upload of the same
            # PDF as REJECT_DUPLICATE, with no way to ever finish writing the
            # files that are missing. Move it to ERROR in a fresh commit so
            # the next upload of the same content is recognized as
            # RETRY_EXISTING instead -- which, unlike a normal retry, must be
            # able to re-stage *every* file including source.pdf, since any
            # one of them (not just the ones a normal retry re-renders) could
            # be the one that never made it to disk (see is_retry handling in
            # _write_submission).
            uow.submissions.mark_intake_outcome(
                submission_id, SubmissionState.ERROR, "finalization_failed"
            )
            uow.commit()
            raise

        return SubmissionIntakeResult(
            submission=final, answer_images=tuple(answer_images), is_retry=is_retry
        )


def _write_submission(
    *,
    uow: SqlAlchemyUnitOfWork,
    store: LocalFileStore,
    pdf_engine: PdfEngine,
    image_preprocessor: ImagePreprocessor,
    scratch_path: Path,
    submission_id: str,
    test_id: str,
    content_hash: str,
    page_count: int,
    data: bytes,
    student_label: str | None,
    filename: str,
    is_retry: bool,
    questions: list[Question],
    questions_by_page: dict[int, list[Question]],
    coverage_issue: str | None,
    id_factory: Callable[[], str],
    now: datetime,
    limits: IntakeLimits,
) -> tuple[Submission, list[AnswerImage]]:
    """Render every page, extract answer images, and commit the submission row.

    Split out of :func:`intake_submission` so its caller can wrap exactly this
    (the part that touches the DB and staged files) in one try/except for the
    concurrent-insert race -- see the ``IntegrityError`` handling there.
    """
    with transactional_operation(
        uow, store, max_staged_bytes=limits.max_staged_output_bytes
    ) as staged:
        # One page's raw raster lives at a time -- not the whole PDF's worth --
        # so a large page count doesn't multiply the sidecar's memory use.
        answer_images: list[AnswerImage] = []
        for page in range(1, page_count + 1):
            # A page can have a page tree and geometry pypdf/page_geometry
            # (both checked earlier) consider entirely valid, yet still carry
            # a malformed or unsupported content stream that only PDFium's
            # renderer actually rejects. Left uncaught, that surfaces as an
            # unhandled 500 instead of the documented bad-PDF rejection.
            try:
                raw_png = pdf_engine.render_page_png(scratch_path, page - 1, scale=RENDER_SCALE)
            except Exception as exc:
                raise PdfCorruptedError(f"could not render page {page}: {exc}") from exc
            preview = image_preprocessor.preprocess_page(raw_png)
            staged.add(store.submission_page_image_path(submission_id, page), preview.png_bytes)
            for question in questions_by_page.get(page, ()):
                answer_images.append(
                    _build_answer_image(
                        question=question,
                        raw_png=raw_png,
                        submission_id=submission_id,
                        store=store,
                        staged=staged,
                        id_factory=id_factory,
                        now=now,
                    )
                )

        if not questions:
            submission_state = SubmissionState.NEEDS_REVIEW
            submission_review_reason = "no_questions_registered"
        elif coverage_issue is not None:
            submission_state = SubmissionState.NEEDS_REVIEW
            submission_review_reason = coverage_issue
        else:
            any_needs_review = any(
                image.status is AnswerImageStatus.NEEDS_REVIEW for image in answer_images
            )
            if any_needs_review:
                submission_state = SubmissionState.NEEDS_REVIEW
                # Grouped by the per-image reason rather than all filed under
                # ``answer_area_undefined``: since Issue #122 a flagged image
                # can also mean "the crop came out blank", which is a
                # different thing for the reviewer to go and look at, and a
                # reason string that named the wrong one would send them to
                # the registration screen for a problem that is not there.
                submission_review_reason = _describe_flagged_images(answer_images)
            else:
                submission_state = SubmissionState.AI_PROCESSED
                submission_review_reason = None

        source_pdf_full_path = store.submission_source_pdf_path(submission_id)
        source_pdf_path = str(source_pdf_full_path.relative_to(store.root)).replace("\\", "/")
        # A retry reuses the exact bytes already on disk for this submission
        # (the reintake decision only allows RETRY_EXISTING for an identical
        # content hash) -- Issue #17's reintake policy never rewrites the
        # source PDF, so a normal retry skips re-staging it. But a retry can
        # also be *healing* a prior attempt whose file finalization partially
        # failed (see FinalizationError handling in intake_submission), in
        # which case source.pdf specifically -- unlike the page previews and
        # question crops below, which every retry unconditionally
        # re-renders and re-stages anyway -- might never have reached disk at
        # all. Stage it whenever it's actually missing, retry or not, so
        # that case can still be fully repaired.
        if not is_retry or not source_pdf_full_path.is_file():
            staged.add(source_pdf_full_path, data)

        if is_retry:
            # Conditional UPDATE (WHERE state = 'error'), not a read-then-write:
            # two concurrent retries of the same submission can both have
            # decided RETRY_EXISTING before either claims it, and only one
            # claim_for_retry() can ever return True. The loser raises here,
            # inside the same try/except that rolls back and discards this
            # request's staged files -- it never commits a redundant pipeline
            # run against a submission another request is already reprocessing.
            if not uow.submissions.claim_for_retry(submission_id):
                raise SubmissionRetryConflictError(submission_id)
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
            # This is the statement a concurrent duplicate insert fails on --
            # SqlAlchemySubmissionRepository.add() flushes immediately, so the
            # uq_submissions_test_content_hash violation surfaces here, still
            # inside transactional_operation's try/except (which rolls back and
            # discards any staged files before re-raising).
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

    return final, answer_images


#: `AnswerImage.reason` values that keep their historical spelling in
#: `Submission.review_reason`. ``no_answer_area_defined`` and
#: ``answer_area_zero_area`` have both been reported as
#: ``answer_area_undefined:<ids>`` since Issue #17, and the intake screen and
#: `docs/answer-intake-and-preprocessing.md` §3 both name that string.
_SUBMISSION_REASON_BY_IMAGE_REASON = {
    "no_answer_area_defined": "answer_area_undefined",
    "answer_area_zero_area": "answer_area_undefined",
    NEARLY_BLANK_CROP_REASON: NEARLY_BLANK_CROP_REASON,
}


def _describe_flagged_images(answer_images: Sequence[AnswerImage]) -> str:
    """``<reason>:<question-id,...>`` for every reason that flagged at least
    one image, joined by ``;`` -- the same shape `describe_coverage_issue`
    produces, so one parser handles both."""
    grouped: dict[str, list[str]] = {}
    for image in answer_images:
        if image.status is not AnswerImageStatus.NEEDS_REVIEW:
            continue
        reason = _SUBMISSION_REASON_BY_IMAGE_REASON.get(image.reason or "", "answer_area_undefined")
        grouped.setdefault(reason, []).append(image.question_id)
    return ";".join(f"{reason}:{','.join(ids)}" for reason, ids in sorted(grouped.items()))


def _build_answer_image(
    *,
    question: Question,
    raw_png: bytes,
    submission_id: str,
    store: LocalFileStore,
    staged: StagedFiles,
    id_factory: Callable[[], str],
    now: datetime,
) -> AnswerImage:
    """Crop one question's answer area from its (already-rendered) page raster.

    A question with no confirmed ``answer_area`` (test registration hasn't
    defined one yet) falls back to the full page preview image, marked
    ``NEEDS_REVIEW`` -- simplified-design-spec.md §24 "回答欄検出失敗は…元画像
    を人間へ提示する". A crop that *was* taken but came out as good as blank
    is marked the same way (`domain.submission_intake.is_nearly_blank_crop`,
    Issue #122): a detected box can land in the margin, and grading paper
    produced "0点・確信度 0.95" rather than anything a reviewer could
    question. The domain model currently allows a zero-``width``/
    ``height`` ``NormalizedRect`` through, and ``crop_normalized_rect``'s own
    clamp would silently turn that into a meaningless 1x1px crop marked "OK"
    rather than failing; treated the same as "not defined" here instead, so a
    degenerate answer area still reaches a human, not a submission that
    quietly landed on ``ai_processed`` with unusable answer data.
    """
    zero_area = question.answer_area is not None and (
        question.answer_area.width <= 0 or question.answer_area.height <= 0
    )
    if question.answer_area is None or zero_area:
        image_path = store.submission_page_image_path(submission_id, question.page)
        status = AnswerImageStatus.NEEDS_REVIEW
        reason: str | None = "answer_area_zero_area" if zero_area else "no_answer_area_defined"
    else:
        cropped = crop_normalized_rect(raw_png, question.answer_area)
        image_path = store.submission_question_image_path(submission_id, question.id)
        # Staged either way, unlike the two branches above: this crop is
        # exactly what would have been sent to be graded, so it is the one
        # thing a person needs to look at to see that the box is in the
        # wrong place (Issue #122). The other branches have no crop to show
        # and fall back to the page.
        staged.add(image_path, cropped)
        if is_nearly_blank_crop(ink_coverage(cropped)):
            status = AnswerImageStatus.NEEDS_REVIEW
            reason = NEARLY_BLANK_CROP_REASON
        else:
            status = AnswerImageStatus.OK
            reason = None
    return AnswerImage(
        id=id_factory(),
        submission_id=submission_id,
        question_id=question.id,
        page=question.page,
        image_path=str(image_path.relative_to(store.root)).replace("\\", "/"),
        status=status,
        reason=reason,
        created_at=now,
    )


def repair_incomplete_submissions(uow: SqlAlchemyUnitOfWork, store: LocalFileStore) -> list[str]:
    """Move any submission whose expected files are missing on disk back to
    ``error``, so a re-upload of the same PDF is recognized as a retry
    instead of ``REJECT_DUPLICATE``. Returns the ids repaired this way.

    ``FinalizationError`` (``adapters.atomic``) catches a *raised* write
    failure and does exactly this at the call site -- but a process crash or
    power loss between ``transactional_operation``'s DB commit and the file
    writes that follow it leaves a submission recorded as
    ``ai_processed``/``needs_review`` with some files missing, with no
    exception handler ever running to notice. Call this once at startup
    (``api/app.py::create_app``), the same way ``LocalFileStore.sweep_temp``
    cleans up interrupted writes' leftover ``*.part`` files, to catch what a
    prior run left in that state before it could shut down cleanly.

    This only ever *detects* the problem and makes it retryable again -- it
    never regenerates a file itself. The user still has to re-upload the
    same PDF (the sidecar keeps no other durable copy of the upload bytes
    between requests) for the normal retry path to actually rewrite
    whatever's missing.
    """
    repaired: list[str] = []
    for test in uow.tests.list_all():
        for submission in uow.submissions.list_for_test(test.id):
            if submission.state not in (SubmissionState.AI_PROCESSED, SubmissionState.NEEDS_REVIEW):
                continue
            expected_paths = [
                store.submission_source_pdf_path(submission.id),
                *(
                    store.submission_page_image_path(submission.id, page)
                    for page in range(1, submission.page_count + 1)
                ),
                *(
                    store.root / image.image_path
                    for image in uow.answer_images.list_for_submission(submission.id)
                ),
            ]
            if all(path.is_file() for path in expected_paths):
                continue
            uow.submissions.mark_intake_outcome(
                submission.id, SubmissionState.ERROR, "finalization_failed"
            )
            uow.commit()
            repaired.append(submission.id)
    return repaired
