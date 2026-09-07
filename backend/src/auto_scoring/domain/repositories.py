"""Persistence ports for the MVP entities.

The domain only ever sees these protocols; concrete SQLAlchemy adapters live in
`auto_scoring.adapters` (see `AGENTS.md` "Architecture"). A :class:`UnitOfWork`
owns one transaction boundary: mutations are invisible until :meth:`commit`, and
`__exit__` rolls back anything not committed.

Result repositories (:class:`RecognitionResultRepository`,
:class:`GradeResultRepository`, :class:`ReviewRepository`) are append-only:
``add`` inserts a new row and nothing updates an existing one, so an AI proposal
and the human-confirmed value are always retrievable side by side
(simplified-design-specification.md §19, §35-5).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from auto_scoring.domain.dependency_graph import DependencyGraph
from auto_scoring.domain.models import (
    Annotation,
    AnswerImage,
    Export,
    GradeResult,
    GradingSource,
    Job,
    JobState,
    Question,
    RecognitionResult,
    Review,
    Rubric,
    Submission,
    SubmissionState,
    Test,
)


class TestRepository(Protocol):
    def add(self, test: Test) -> None: ...
    def get(self, test_id: str) -> Test | None: ...
    def list_all(self) -> list[Test]: ...

    def delete(self, test_id: str) -> None:
        """Remove ``test_id`` (a no-op if it doesn't exist).

        Used to compensate for a registration whose `Test` row committed but
        whose PDF files then failed to write to disk
        (``adapters.test_intake.register_test``'s `FinalizationError`
        handling) -- a `draft` test with no confirmed profile yet has no
        `Question`/`Rubric` rows to cascade, so this is always safe to call
        in that situation.
        """
        ...

    def mark_ready(self, test_id: str) -> bool:
        """Atomically move ``test_id`` from ``draft`` to ``ready`` via a
        conditional update (``WHERE status = 'draft'``), not a read-then-write
        -- so two concurrent "complete registration" requests for the same
        test can't both observe ``draft`` and both report success. Returns
        whether this call won the race.
        """
        ...


class QuestionRepository(Protocol):
    def add(self, question: Question) -> None: ...
    def get(self, question_id: str) -> Question | None: ...
    def list_for_test(self, test_id: str) -> list[Question]: ...

    def delete_for_test(self, test_id: str) -> None:
        """Remove every question for ``test_id`` (and, via ``ON DELETE
        CASCADE``, its rubric).

        Used by profile confirmation to reconcile the test's question set
        with a freshly-built one, rather than only inserting ids that don't
        already exist. A profile can only be confirmed once (a
        second `/profile/confirm` on an already-confirmed profile is
        rejected before this would ever run), so no downstream submission
        processing can have started against these rows yet -- it is always
        safe to rebuild them from scratch on a (re)confirm.
        """
        ...


class RubricRepository(Protocol):
    def add(self, rubric: Rubric) -> None: ...
    def get_for_question(self, question_id: str) -> Rubric | None: ...


class SubmissionRepository(Protocol):
    def add(self, submission: Submission) -> None: ...
    def get(self, submission_id: str) -> Submission | None: ...
    def list_for_test(self, test_id: str) -> list[Submission]: ...
    def set_state(self, submission_id: str, state: SubmissionState) -> None: ...
    def find_by_content_hash(self, test_id: str, source_pdf_sha256: str) -> Submission | None: ...

    def mark_intake_outcome(
        self, submission_id: str, state: SubmissionState, review_reason: str | None
    ) -> None:
        """Validated state transition plus ``review_reason``, in one write.

        Used only by the answer-intake pipeline (``adapters.submission_intake``)
        so a retry can both move the submission out of ``ERROR`` and record why
        it did (or didn't) land in ``NEEDS_REVIEW`` again, without a second
        round trip.
        """
        ...

    def claim_for_retry(self, submission_id: str) -> bool:
        """Atomically move ``submission_id`` from ``ERROR`` to ``UNPROCESSED``
        via a conditional update (``WHERE state = 'error'``), not a read-then-
        write -- so two concurrent retries of the same errored submission
        can't both proceed and both commit the full intake pipeline. Returns
        whether this call won the race.
        """
        ...

    def has_downstream_processing(self, submission_id: str) -> bool:
        """Whether any recognition/grade/review/job row references
        ``submission_id`` -- i.e. whether processing already moved past
        intake for it.

        Used by the answer-intake retry decision
        (``domain.submission_intake.decide_reintake``) to keep in-place retry
        limited to intake-stage failures: those tables are append-only
        history (or, for jobs, independently-scheduled work) keyed on
        ``submission_id``/``question_id``, not on a particular attempt's
        answer images. Blindly reprocessing a submission in place once
        something downstream has already touched it would leave that history
        (and any still-queued job) orphaned against a fresh set of
        regenerated answer images.
        """
        ...


class AnswerImageRepository(Protocol):
    def add(self, image: AnswerImage) -> None: ...
    def list_for_submission(self, submission_id: str) -> list[AnswerImage]: ...

    def replace_for_submission(self, submission_id: str, images: Sequence[AnswerImage]) -> None:
        """Delete any answer images already recorded for ``submission_id`` and
        insert ``images`` in their place -- a retry re-runs the whole
        extraction, so the old set (which may reference a since-deleted file
        state) must not linger alongside the new one.
        """
        ...


class RecognitionResultRepository(Protocol):
    """Append-only."""

    def add(self, result: RecognitionResult) -> None: ...
    def get(self, result_id: str) -> RecognitionResult | None: ...
    def history(self, submission_id: str, question_id: str) -> list[RecognitionResult]: ...


class GradeResultRepository(Protocol):
    """Append-only."""

    def add(self, result: GradeResult) -> None: ...
    def get(self, result_id: str) -> GradeResult | None: ...
    def history(self, submission_id: str, question_id: str) -> list[GradeResult]: ...
    def latest(
        self, submission_id: str, question_id: str, source: GradingSource
    ) -> GradeResult | None: ...


class AnnotationRepository(Protocol):
    def add(self, annotation: Annotation) -> None: ...
    def list_for(self, submission_id: str, question_id: str) -> list[Annotation]: ...


class ReviewRepository(Protocol):
    """Append-only operation history."""

    def add(self, review: Review) -> None: ...
    def history(self, submission_id: str, question_id: str) -> list[Review]: ...


class JobRepository(Protocol):
    def add(self, job: Job) -> None: ...
    def get(self, job_id: str) -> Job | None: ...

    def save(
        self,
        job: Job,
        *,
        expected_state: JobState,
        expected_attempts: int | None = None,
        require_usable_unset: bool = False,
    ) -> None:
        """Persist ``job`` iff the row is still in ``expected_state`` -- the
        state the caller itself observed (e.g. from `get`) before deciding on
        this transition, not a value re-read from the row inside `save`
        itself. Re-reading it here would let two callers who both saw the
        same original state both "win": the second call's freshly re-read
        current state would already equal its own target state, skipping the
        transition check and matching its own `WHERE` clause (Issue #26
        review). Raises `auto_scoring.domain.models.JobSaveConflict` if the
        row has moved on from ``expected_state``.

        ``expected_attempts``, if given, also gates the write on ``attempts
        ==`` that value -- ``state`` alone cannot rule out an ABA cycle for
        a non-terminal state like FAILED: a concurrent retry can complete a
        whole FAILED -> QUEUED -> RUNNING -> FAILED cycle (a fresh,
        unreviewed attempt, with its own new ``error_code``/``last_error``)
        between this caller's read and its write, and the state-only CAS
        would match again -- silently overwriting that newer attempt's
        state with this caller's stale one instead of losing the race
        (Issue #18 review round 9, P1). ``attempts`` only ever changes on a
        transition through RUNNING, so it strictly changes across any such
        cycle, the same property `mark_usable`'s own ``expected_attempts``
        already relies on for this exact reason (review round 6, P1).

        ``require_usable_unset``, if set, also gates the write on ``usable
        IS NULL``. ``state`` alone is not always enough to serialize two
        writers: `mark_usable` changes only `usable`, never `state`, so a
        `save` whose *own* precondition is state-only can still commit after
        a concurrent `mark_usable` call, silently discarding an approval the
        caller's own read never saw (Issue #18 review round 5, P1 -- see
        `auto_scoring.jobs.queue.JobQueueService.retry_job`, the one caller
        that passes this).
        """
        ...

    def list_by_state(self, state: JobState) -> list[Job]: ...

    def list_for_submission(self, submission_id: str) -> list[Job]:
        """Every job for ``submission_id`` (any state), for progress display
        (Issue #18: 一覧・進捗API) and for recomputing DAG readiness after one
        question's job finishes (`auto_scoring.domain.job_scheduling.
        question_statuses`).
        """
        ...

    def mark_usable(
        self, job_id: str, *, usable: bool, expected_state: JobState, expected_attempts: int
    ) -> bool:
        """Flip a job's `Job.usable` bit in place, iff the row is still in
        ``expected_state`` (``SUCCEEDED`` or ``FAILED``) with ``attempts``
        still equal to ``expected_attempts`` -- what the caller itself
        observed before deciding to do this, exactly like `save`'s
        compare-and-set. Returns whether the write actually applied.

        Unlike `save`, this does not change ``state`` -- it exists for the
        "a human corrected a low-confidence or failed result and it is now
        usable" resume path (Issue #18 §4.4), which changes only this bit,
        not the job's lifecycle state (a FAILED job stays FAILED; only
        whether its downstream effect may now proceed changes).

        The compare-and-set matters because this call and a concurrent
        `save` (e.g. a manual retry moving the same row FAILED -> QUEUED)
        can race: without pinning the write to the exact state the caller
        read, this could silently mark a job usable (and this call's
        caller could go on to release dependents on that basis) after the
        job has already moved on to being reprocessed, or a racing `save`
        could silently clear a `usable` this call just set (Issue #18
        review round 3, P1 -- AGENTS.md "invariants は UI ではなく実制約で"
        applies to the transaction, not just the column, here). The caller
        is expected to retry from a fresh read on ``False``, the same as
        it would for `JobSaveConflict` from `save`.

        ``expected_attempts`` closes an ABA hole ``state`` alone cannot:
        FAILED is not a dead end (retry can move it FAILED -> QUEUED ->
        RUNNING -> FAILED again), so a concurrent retry that completes a
        whole cycle back to FAILED between this call's read and its write
        would make a state-only CAS match again -- applying an approval
        read for one attempt to a completely different, unreviewed later
        attempt. `attempts` only ever changes on a transition through
        RUNNING, so it strictly changes across any such cycle, the same way
        `auto_scoring.jobs.queue.JobQueueService._requeue_after_backoff`
        already uses it to tell an earlier attempt's stale backoff timer
        apart from a newer one (Issue #18 review round 6, P1).
        """
        ...

    def list_incomplete_for_stale_versions(self, test_id: str, current_version: int) -> list[Job]:
        """Jobs for ``test_id`` still QUEUED/RUNNING/BLOCKED, or FAILED with
        ``usable`` unset, against a `dependency_graph_version` other than
        ``current_version`` (Issue #26: superseded-graph job invalidation).
        Jobs never tagged with a graph version (``dependency_graph_version
        is None``) are not "stale" by this definition and are excluded.

        A FAILED job counts as incomplete because FAILED -> QUEUED is a
        valid retry transition -- left unlisted, it could still be retried
        later and run against the superseded version. A FAILED job whose
        ``usable`` a human already set via `mark_usable` is the exception:
        that approval already released (or will release) a dependent, and
        invalidating it here would silently clear the approval out from
        under that dependent (Issue #18 review round 6, P1).
        """
        ...


class ExportRepository(Protocol):
    """Successful `Export` rows only (Issue #23) -- an in-flight or failed
    attempt lives entirely as a `Job` (kind=``EXPORT``); nothing here ever
    updates a row once added.
    """

    def add(self, export: Export) -> None: ...
    def get(self, export_id: str) -> Export | None: ...

    def list_for_submission(self, submission_id: str) -> list[Export]:
        """Every export for ``submission_id``, oldest first (for "保存先表示"
        / export history display)."""
        ...

    def latest_for_submission(self, submission_id: str) -> Export | None:
        """The most recently created export for ``submission_id``, or
        ``None`` -- what `domain.pdf_export.decide_reexport` compares a fresh
        request's review-version snapshot against.
        """
        ...


class DependencyGraphRepository(Protocol):
    """One test's dependency-graph versions (Issue #26).

    ``save`` upserts on ``(test_id, version)``: a DRAFT row for that version is
    replaced in place (new candidates, or the human's confirm), but a
    CONFIRMED row is immutable -- ``save`` raises rather than overwrite one, so
    changing a confirmed graph always means a new, higher version.
    """

    def save(self, graph: DependencyGraph) -> None: ...
    def get(self, graph_id: str) -> DependencyGraph | None: ...
    def get_latest(self, test_id: str) -> DependencyGraph | None: ...

    def get_latest_confirmed(self, test_id: str) -> DependencyGraph | None:
        """The highest-versioned CONFIRMED graph, regardless of whether a
        newer DRAFT also exists (Issue #26: `confirm` must reject a version
        older than this -- see `auto_scoring.api.dependency_graph_router`).
        """
        ...

    def try_confirm(self, confirmed: DependencyGraph) -> bool:
        """Atomic compare-and-set DRAFT -> CONFIRMED (Issue #26 review).

        Returns ``True`` and replaces the row's edges only if it is still
        DRAFT and no higher version for the same test is already CONFIRMED at
        the moment of the write; returns ``False`` -- unchanged -- otherwise,
        so two concurrent confirms can never both succeed.
        """
        ...

    def list_versions(self, test_id: str) -> list[DependencyGraph]: ...


class UnitOfWork(Protocol):
    """One transaction boundary over every repository."""

    tests: TestRepository
    questions: QuestionRepository
    rubrics: RubricRepository
    submissions: SubmissionRepository
    answer_images: AnswerImageRepository
    recognitions: RecognitionResultRepository
    grades: GradeResultRepository
    annotations: AnnotationRepository
    reviews: ReviewRepository
    jobs: JobRepository
    exports: ExportRepository
    dependency_graphs: DependencyGraphRepository

    def __enter__(self) -> UnitOfWork: ...
    def __exit__(self, *exc_info: object) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
