"""`JobProcessor` for the annotated-PDF export job (Issue #23, parent #3).

Framework-adjacent, not domain (same place as `jobs.grading_processor` in the
architecture): the concrete boundary between `domain.job_execution.
JobProcessor` and the `domain.pdf_export`/`domain.pdf_engine` ports it
composes. See `docs/pdf-export.md` for the full design record.
"""

from __future__ import annotations

import hashlib
import tempfile
from asyncio import to_thread
from pathlib import Path
from threading import Lock

from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.atomic import transactional_operation
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.job_execution import ProcessingOutcome, ProcessingResult
from auto_scoring.domain.models import ErrorCategory, Export, Job
from auto_scoring.domain.pdf_engine import AnnotationMark, PdfEngine
from auto_scoring.domain.pdf_export import (
    build_export_marks,
    review_version_snapshot,
    unconfirmed_question_ids,
)
from auto_scoring.domain.review_workflow import resolve_effective_grade
from auto_scoring.jobs.clock import Clock, SystemClock


def export_id(job: Job) -> str:
    """Deterministic id for the `Export` a successful run of ``job``
    produces -- same idempotent-replay reasoning as `jobs.grading_processor.
    grade_result_id`: a crash-recovery re-run of the same, already-succeeded
    job must not regenerate the file or insert a second row.
    """
    return f"export:{job.id}"


class ExportGenerationError(Exception):
    """Something about producing or verifying the candidate PDF failed.

    Never carries answer text (AGENTS.md "Security") -- only page counts and
    exception class names from this module's own generation/verification
    steps.
    """


class ExportJobProcessor:
    """Renders one submission's confirmed reviews onto a fresh, annotated
    copy of its source PDF.

    ``pdfium_lock`` is the same lock `api.app.create_app` already serializes
    submission intake's PDFium calls with -- pypdfium2 is not safe to call
    concurrently from multiple threads, and this processor's verification
    step (`PdfEngine.page_count` on the freshly-written candidate) uses it
    too. Holding it for this method's *entire* body (not just the PDFium
    calls) also closes a second, unrelated race: two export jobs for
    submissions that happen to share an ``original_filename`` stem calling
    `LocalFileStore.allocate_export_path` concurrently could otherwise both
    observe the same free filename and one atomic write would silently
    clobber the other's freshly-written output (docs/pdf-export.md "同時実行
    とファイル名衝突").
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        store: LocalFileStore,
        engine: PdfEngine,
        pdfium_lock: Lock,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._store = store
        self._engine = engine
        self._lock = pdfium_lock
        self._clock = clock or SystemClock()

    async def process(self, job: Job) -> ProcessingResult:
        # CPU/IO-bound (PDF rendering + a full page-count verification pass);
        # offloaded exactly like `GradingJobProcessor`'s AI provider call, so
        # it doesn't block the event loop for the duration.
        return await to_thread(self._process_sync, job)

    def _process_sync(self, job: Job) -> ProcessingResult:
        with self._lock:
            return self._generate(job)

    def _generate(self, job: Job) -> ProcessingResult:
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            if uow.exports.get(export_id(job)) is not None:
                # Idempotent replay: a prior run of this same job already
                # succeeded (crash-recovery re-enqueue after the RUNNING ->
                # SUCCEEDED write, or a duplicate dispatch signal). Never
                # regenerate or insert a second row.
                return ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=True)

            submission = uow.submissions.get(job.submission_id)
            if submission is None:
                return self._failed("submission not found")

            questions = uow.questions.list_for_test(submission.test_id)
            question_ids = [question.id for question in questions]
            reviews_by_question = {
                question_id: uow.reviews.history(job.submission_id, question_id)
                for question_id in question_ids
            }
            missing = unconfirmed_question_ids(question_ids, reviews_by_question)
            if missing:
                return self._failed(
                    f"{len(missing)} question(s) not yet confirmed: {', '.join(sorted(missing))}"
                )

            marks_by_page: dict[int, list[AnnotationMark]] = {}
            for question in questions:
                grades = uow.grades.history(job.submission_id, question.id)
                grade = resolve_effective_grade(reviews_by_question[question.id], grades)
                if grade is None:
                    # Unreachable: the confirmed-gate above already requires
                    # an effective review, and a confirmed review always
                    # names a grade (`Review.__post_init__`).
                    continue
                annotations = uow.annotations.list_for(job.submission_id, question.id)
                recognitions = uow.recognitions.history(job.submission_id, question.id)
                marks = build_export_marks(
                    question=question,
                    grade=grade,
                    annotations=annotations,
                    recognitions=recognitions,
                )
                marks_by_page.setdefault(question.page - 1, []).extend(marks)

            snapshot = review_version_snapshot(question_ids, reviews_by_question)
            source_path = self._store.root / submission.source_pdf_path

            try:
                data = self._render_and_verify(source_path, marks_by_page)
            except ExportGenerationError as error:
                return self._failed(str(error))

            destination = self._store.allocate_export_path(
                submission.original_filename or f"{submission.id}.pdf"
            )
            relative_path = str(destination.relative_to(self._store.root)).replace("\\", "/")
            export = Export(
                id=export_id(job),
                submission_id=job.submission_id,
                job_id=job.id,
                file_path=relative_path,
                file_sha256=hashlib.sha256(data).hexdigest(),
                created_at=self._clock.now(),
                review_versions=snapshot,
            )
            with transactional_operation(uow, self._store) as staged:
                uow.exports.add(export)
                staged.add(destination, data)

        return ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=True)

    def _render_and_verify(
        self, source_path: Path, marks_by_page: dict[int, list[AnnotationMark]]
    ) -> bytes:
        """Render into a scratch temp file (outside ``app-data/``, per
        ``docs/answer-intake-and-preprocessing.md`` §1's same convention),
        verify it, and return its bytes -- never touches ``app-data/`` or the
        database itself; only a successfully-verified result reaches
        `_generate`'s ``transactional_operation`` call. A generation or
        verification failure here leaves the source PDF and every prior
        successful export completely untouched (Issue #23 acceptance).
        """
        expected_pages = self._engine.page_count(source_path)
        with tempfile.TemporaryDirectory(prefix="auto-scoring-export-") as scratch:
            candidate_path = Path(scratch) / "candidate.pdf"
            try:
                self._engine.render_annotations(source_path, candidate_path, marks_by_page)
                actual_pages = self._engine.page_count(candidate_path)
            except Exception as error:
                raise ExportGenerationError(
                    f"PDF generation failed: {type(error).__name__}: {error}"
                ) from error
            if actual_pages != expected_pages:
                raise ExportGenerationError(
                    f"generated PDF has {actual_pages} page(s), expected {expected_pages}"
                )
            return candidate_path.read_bytes()

    def _failed(self, message: str) -> ProcessingResult:
        return ProcessingResult(
            outcome=ProcessingOutcome.FAILED,
            error_category=ErrorCategory.PERMANENT,
            error_message=message,
        )
