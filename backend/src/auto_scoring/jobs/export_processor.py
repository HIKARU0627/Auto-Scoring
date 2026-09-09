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
from auto_scoring.adapters.local_storage import LocalFileStore, file_matches_sha256
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.job_execution import ProcessingOutcome, ProcessingResult
from auto_scoring.domain.models import (
    ErrorCategory,
    Export,
    Job,
    JobState,
    QuestionReviewVersion,
    Review,
    Submission,
)
from auto_scoring.domain.pdf_engine import AnnotationMark, PdfEngine
from auto_scoring.domain.pdf_export import (
    build_export_marks,
    fallback_score_areas,
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


def _truncate_to_snapshot(
    reviews_by_question: dict[str, list[Review]],
    snapshot: tuple[QuestionReviewVersion, ...],
) -> dict[str, list[Review]]:
    """Reconstruct each question's review history exactly as it stood at
    ``snapshot`` (an `Export.review_versions`) -- the repair path's way of
    regenerating from the past, not the present (P2 review, round 2).

    ``ReviewRepository.history`` is oldest-first and
    ``QuestionReviewVersion.version`` is that history's length at snapshot
    time (`domain.review_workflow.next_review_version`'s own invariant), so
    keeping only the first ``version`` rows for each question reconstructs
    precisely what `domain.review_workflow.effective_latest_review` would
    have resolved to back then -- any review recorded since is simply not
    there to be seen.
    """
    versions = {entry.question_id: entry.version for entry in snapshot}
    return {
        question_id: reviews[: versions.get(question_id, len(reviews))]
        for question_id, reviews in reviews_by_question.items()
    }


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
        # it doesn't block the event loop for the duration. Cancelling the
        # awaiting task (`JobQueueService.cancel_running_task`) does not stop
        # this underlying thread -- `_generate` re-checks the job's own state
        # immediately before publishing anything, precisely to guard against
        # that (see its docstring, P2 review).
        return await to_thread(self._process_sync, job)

    def _process_sync(self, job: Job) -> ProcessingResult:
        with self._lock:
            return self._generate(job)

    def _generate(self, job: Job) -> ProcessingResult:
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            existing = uow.exports.get(export_id(job))
            if existing is not None and self._existing_file_is_intact(existing):
                # Idempotent replay: a prior run of this same job already
                # succeeded and its file is still there, byte-for-byte, as
                # recorded. Never regenerate or insert a second row.
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

            if existing is not None:
                # Repair path (P2 review, round 2): regenerate strictly from
                # the snapshot already recorded on `existing`, not whatever
                # the review state happens to be *now* -- a reviewer may
                # have edited/regraded/undone a question between the
                # original (lost) file and this retry, and the row must
                # keep describing exactly what was true when it was first
                # produced, not silently attribute a newer PDF to an older
                # `review_versions`/`created_at`. Truncating each question's
                # history to its recorded version count reconstructs that
                # exact past state (`ReviewRepository.history` is
                # oldest-first, and `QuestionReviewVersion.version` is that
                # history's length at snapshot time -- the same invariant
                # `domain.review_workflow.next_review_version` relies on).
                # The confirmed-gate below is skipped: this exact snapshot
                # already passed it the first time this job ran.
                reviews_by_question = _truncate_to_snapshot(
                    reviews_by_question, existing.review_versions
                )
                snapshot = existing.review_versions
            else:
                missing = unconfirmed_question_ids(question_ids, reviews_by_question)
                if missing:
                    return self._failed(
                        f"{len(missing)} question(s) not yet confirmed: "
                        f"{', '.join(sorted(missing))}"
                    )
                snapshot = review_version_snapshot(question_ids, reviews_by_question)

            # Issue #150: where each question with no `score_area` of its
            # own gets its score written instead. Allocated once for the
            # whole submission, not per question, because the slices are
            # shared out across a page's questions and two questions must
            # not be handed the same slice.
            fallback_areas = fallback_score_areas(questions)

            marks_by_page: dict[int, list[AnnotationMark]] = {}
            for question in questions:
                grades = uow.grades.history(job.submission_id, question.id)
                grade = resolve_effective_grade(reviews_by_question[question.id], grades)
                if grade is None:
                    # Unreachable: the confirmed-gate (fresh generation) or
                    # the original run's own confirmed-gate (repair, whose
                    # truncated history reproduces exactly what already
                    # passed it) always leaves an effective review naming a
                    # grade (`Review.__post_init__`).
                    continue
                annotations = uow.annotations.list_for(job.submission_id, question.id)
                recognitions = uow.recognitions.history(job.submission_id, question.id)
                marks = build_export_marks(
                    question=question,
                    grade=grade,
                    annotations=annotations,
                    recognitions=recognitions,
                    fallback_score_area=fallback_areas.get(question.id),
                )
                marks_by_page.setdefault(question.page - 1, []).extend(marks)

            source_path = self._store.root / submission.source_pdf_path

            try:
                data = self._render_and_verify(source_path, marks_by_page)
            except ExportGenerationError as error:
                return self._failed(str(error))

            # As late as possible before publishing anything: a job cancelled
            # (`POST /jobs/{id}/cancel`) while this render was in flight only
            # requests cancellation of the *await* on this thread (P2
            # review) -- the thread itself, and this whole `_generate` call,
            # keeps running to completion regardless. The queue's own
            # `_finalize_cancelled` may already have written CANCELLED to
            # this job's row by now (from the coroutine side noticing the
            # cancellation); re-reading it here is the only way this thread
            # can find out and refuse to publish a result for a job that is
            # no longer RUNNING. A perfect race is not achievable this way
            # (the row could still flip between this check and the commit
            # below), but it narrows the window from "the entire render"
            # down to a couple of DB round-trips, matching
            # `jobs.queue.JobQueueService._finalize_result`'s own re-check
            # of the same field for the same reason.
            if not self._job_is_still_running(uow, job.id):
                return self._failed("job was cancelled before the export could be published")

            if existing is not None:
                return self._repair_existing_export(uow, existing, data)
            return self._create_new_export(uow, job, submission, snapshot, data)

    def _job_is_still_running(self, uow: SqlAlchemyUnitOfWork, job_id: str) -> bool:
        current = uow.jobs.get(job_id)
        return current is not None and current.state is JobState.RUNNING

    def _existing_file_is_intact(self, export: Export) -> bool:
        """Whether ``export``'s recorded file actually exists and still
        matches its recorded hash.

        Guards the idempotent-replay fast path (P1 review): a bare "does an
        `Export` row exist" check is not enough -- a crash between this
        row's commit and the file write that follows it (`adapters.atomic`'s
        own documented risk) leaves exactly that: a committed row naming a
        file that was never written. Treating that as "already done" would
        let every later export request for this submission resolve to
        `reuse_existing` against a file that does not exist.
        """
        return file_matches_sha256(self._store.root / export.file_path, export.file_sha256)

    def _repair_existing_export(
        self, uow: SqlAlchemyUnitOfWork, existing: Export, data: bytes
    ) -> ProcessingResult:
        """Rewrite ``existing``'s file from freshly-rendered ``data`` (P1
        review): reached only when `_existing_file_is_intact` found the
        previously-committed row's file missing or corrupted. Never inserts
        a second `Export` row (``job_id`` is unique) -- corrects
        ``file_sha256`` in place via `ExportRepository.repair_file_hash` if
        the fresh render's hash differs from what was originally recorded
        (a fresh render is not guaranteed byte-identical to the lost one).
        """
        output_path = self._store.root / existing.file_path
        self._store.write_atomic(output_path, data)
        new_sha256 = hashlib.sha256(data).hexdigest()
        if new_sha256 != existing.file_sha256:
            uow.exports.repair_file_hash(existing.id, new_sha256)
            uow.commit()
        return ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=True)

    def _create_new_export(
        self,
        uow: SqlAlchemyUnitOfWork,
        job: Job,
        submission: Submission,
        snapshot: tuple[QuestionReviewVersion, ...],
        data: bytes,
    ) -> ProcessingResult:
        # Every path any Export row anywhere already names is off-limits,
        # not just what's currently on disk (P1 review, round 3) and not
        # just this submission's own rows (P1 review, round 4): export
        # filenames are derived from the source file's stem alone, with no
        # submission id in the path, so two different submissions that
        # happen to share an original filename share the same export-path
        # namespace. A row whose own file write failed after its DB commit
        # (the exact scenario `_existing_file_is_intact`/
        # `_repair_existing_export` exist for) still reserves its
        # `file_path` -- nothing has freed it just because there is nothing
        # there to see yet. Handing that same path to a *different*,
        # unrelated new export (for this submission or another one) here
        # would let this write occupy it, and a later repair-retry of the
        # original job would then overwrite this one's file out from under
        # it.
        destination = self._store.allocate_export_path(
            submission.original_filename or f"{submission.id}.pdf",
            reserved=uow.exports.all_file_paths(),
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
        `_generate`'s publish step. A generation or verification failure
        here leaves the source PDF and every prior successful export
        completely untouched (Issue #23 acceptance).
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
