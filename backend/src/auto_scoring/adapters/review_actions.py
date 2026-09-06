"""Orchestrates the review screen's edit/reject/regrade/approve/undo actions
(Issue #22, parent #3) over the domain rules in `domain.review_workflow` and
the concrete `SqlAlchemyUnitOfWork` -- same shape as `adapters.submission_intake`
/ `adapters.test_intake`: plain functions the API layer (`api.review_router`)
calls with its dependencies, not a class hierarchy.

Every function:

1. Reads this ``(submission_id, question_id)``'s review history and computes
   the next `Review.version` via `domain.review_workflow.next_review_version`
   (raises `ReviewVersionConflict` -- caught by the caller as 409 -- if the
   client's ``expected_version`` is already stale).
2. Performs its own action-specific writes (a new human `GradeResult`/
   `RecognitionResult`/`Annotation` set for `edit_question`; a fresh `Job`
   for `regrade_question`; nothing extra for `reject_question`/
   `approve_question`/`undo_last_review`).
3. Appends the new `Review` row and re-syncs the submission's
   `SubmissionState` (`_sync_submission_review_state`) in the *same*
   transaction, then commits.

The version check in step 1 is a cheap pre-check; the real guard against two
concurrent/duplicate requests both winning is
``uq_reviews_submission_question_version`` (`db.orm.ReviewRow`) -- a
concurrent caller that also passed step 1 (because it read the history before
this transaction committed) hits that constraint's `IntegrityError` at
`uow.commit()`, which every function here re-raises as the same
`ReviewVersionConflict` the pre-check would have raised from a fresh read.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.models import (
    Annotation,
    AnnotationKind,
    CriterionOutcome,
    CriterionResult,
    GradeResult,
    GradingSource,
    Job,
    JobKind,
    JobState,
    NormalizedRect,
    RecognitionResult,
    Review,
    ReviewAction,
    Score,
    Submission,
    SubmissionState,
)
from auto_scoring.domain.review_workflow import (
    ReviewVersionConflict,
    all_questions_confirmed,
    effective_latest_review,
    next_review_version,
)


class NoAiGradeYetError(Exception):
    """`edit_question`/`approve_question` refused: no AI grade exists yet for
    this question to confirm or correct (mirrors the Flutter review screen's
    own `_canApprove` gate, Issue #21 P1 review -- a confirmed review must
    reference one, `Review.__post_init__`). The reviewer must wait for AI
    processing (or trigger `regrade_question`) first.
    """

    def __init__(self, submission_id: str, question_id: str) -> None:
        super().__init__(
            f"{submission_id!r}:{question_id!r} has no AI grade yet; wait for AI processing "
            "or request a regrade first"
        )


class NothingToUndoError(Exception):
    """`undo_last_review` refused: every review row for this question has
    already been undone, or none exists at all -- there is nothing left in
    effect to revert."""

    def __init__(self, submission_id: str, question_id: str) -> None:
        super().__init__(f"{submission_id!r}:{question_id!r} has no review action left to undo")


class QuestionMismatchError(Exception):
    """``question_id`` exists but does not belong to ``submission_id``'s test."""

    def __init__(self, submission_id: str, question_id: str) -> None:
        super().__init__(
            f"question {question_id!r} does not belong to submission {submission_id!r}'s test"
        )


@dataclass(frozen=True, kw_only=True)
class AnnotationInput:
    """One annotation a human wants recorded as part of `edit_question`."""

    kind: AnnotationKind
    rect: NormalizedRect | None = None
    anchor_text: str | None = None
    comment: str | None = None


@dataclass(frozen=True, kw_only=True)
class CriterionInput:
    criterion_id: str
    outcome: CriterionOutcome
    confidence: float | None = None


@dataclass(frozen=True, kw_only=True)
class EditResult:
    review: Review
    grade: GradeResult
    recognition: RecognitionResult | None
    annotations: tuple[Annotation, ...]
    submission: Submission


def _load_submission_and_question(
    uow: SqlAlchemyUnitOfWork, *, submission_id: str, question_id: str
) -> tuple[Submission, str]:
    """Returns ``(submission, question.test_id)`` after validating both exist
    and belong together -- the same three checks every mutating handler in
    `api.recognitions_router` already makes before writing anything."""
    submission = uow.submissions.get(submission_id)
    if submission is None:
        raise LookupError(f"submission {submission_id!r} not found")
    question = uow.questions.get(question_id)
    if question is None:
        raise LookupError(f"question {question_id!r} not found")
    if question.test_id != submission.test_id:
        raise QuestionMismatchError(submission_id, question_id)
    return submission, question.test_id


def _next_version(
    uow: SqlAlchemyUnitOfWork, *, submission_id: str, question_id: str, expected_version: int
) -> tuple[int, Sequence[Review]]:
    existing = uow.reviews.history(submission_id, question_id)
    version = next_review_version(
        existing,
        expected_version=expected_version,
        submission_id=submission_id,
        question_id=question_id,
    )
    return version, existing


def _sync_submission_review_state(uow: SqlAlchemyUnitOfWork, submission: Submission) -> Submission:
    """Move ``submission`` between ``NEEDS_REVIEW``/``REVIEWED`` to match
    whether every one of its questions currently has a confirmed effective
    review (Issue #22 acceptance: "未確認設問が残るSubmissionは出力可能状態
    にならない") -- run inside the same transaction as the `Review` row that
    triggered the recheck, so the two commit atomically together.

    A no-op for any other `SubmissionState` (still processing, exported,
    errored): reopening an exported submission for correction is a later
    issue's job, and a submission still mid-processing has nothing for a
    review action to have legitimately happened against in the first place.
    """
    if submission.state not in (SubmissionState.NEEDS_REVIEW, SubmissionState.REVIEWED):
        return submission
    questions = uow.questions.list_for_test(submission.test_id)
    reviews_by_question = {q.id: uow.reviews.history(submission.id, q.id) for q in questions}
    confirmed = all_questions_confirmed((q.id for q in questions), reviews_by_question)
    target = SubmissionState.REVIEWED if confirmed else SubmissionState.NEEDS_REVIEW
    if target is submission.state:
        return submission
    uow.submissions.set_state(submission.id, target)
    return replace(submission, state=target)


def _commit_or_conflict(
    uow: SqlAlchemyUnitOfWork, *, submission_id: str, question_id: str, expected_version: int
) -> None:
    """Commit the review action's transaction, converting the unique
    constraint's `IntegrityError` (a concurrent writer's `Review` row won the
    same ``version`` first) into the same `ReviewVersionConflict` a fresh
    read would have raised -- see this module's own docstring, point 3.
    """
    try:
        uow.commit()
    except IntegrityError as error:
        uow.rollback()
        raise ReviewVersionConflict(
            submission_id, question_id, expected=expected_version, actual=expected_version + 1
        ) from error


def _latest_ai_grade(
    uow: SqlAlchemyUnitOfWork, *, submission_id: str, question_id: str
) -> GradeResult:
    grade = uow.grades.latest(submission_id, question_id, GradingSource.AI)
    if grade is None:
        raise NoAiGradeYetError(submission_id, question_id)
    return grade


def _carry_forward_annotations(
    uow: SqlAlchemyUnitOfWork,
    *,
    submission_id: str,
    question_id: str,
    based_on_created_at: datetime,
    now: datetime,
) -> list[Annotation]:
    """Re-insert the AI attempt's own annotations (matched by shared
    ``created_at``, the same signal `QuestionReviewState.
    annotationsForDisplayedAttempt` uses client-side -- Issue #21 P2 review)
    as fresh rows at ``now``, the new human `GradeResult`'s own timestamp.

    Used when `edit_question` is not given an explicit ``annotations`` list:
    without this, a human editing only the score/comment would silently make
    every AI-proposed mark disappear from the overlay the moment
    `QuestionReviewState.displayGrade` switches to the new human grade
    (nothing would share its `created_at` any more). Graphically *replacing*
    marks (moving/deleting one) is out of scope for Issue #22 -- see
    ``docs/review-edit-history.md`` "Annotationの修正range" -- so this is
    "keep exactly what the AI proposed" by default; passing an explicit
    ``annotations`` list overrides it entirely.
    """
    existing = uow.annotations.list_for(submission_id, question_id)
    carried = [a for a in existing if a.created_at == based_on_created_at]
    copies = [
        Annotation(
            id=str(uuid4()),
            submission_id=submission_id,
            question_id=question_id,
            source=annotation.source,
            kind=annotation.kind,
            rect=annotation.rect,
            anchor_text=annotation.anchor_text,
            comment=annotation.comment,
            created_at=now,
        )
        for annotation in carried
    ]
    for copy in copies:
        uow.annotations.add(copy)
    return copies


def edit_question(
    uow: SqlAlchemyUnitOfWork,
    *,
    submission_id: str,
    question_id: str,
    expected_version: int,
    score_awarded: int,
    score_maximum: int,
    confidence: float = 1.0,
    criteria: Sequence[CriterionInput] = (),
    rationale: str | None = None,
    comment: str | None = None,
    recognized_text: str | None = None,
    annotations: Sequence[AnnotationInput] | None = None,
    note: str | None = None,
    now: datetime,
) -> EditResult:
    """A human's corrected score/comment (and, optionally, recognized text
    and annotations) for one question -- Issue #22's "edit" use case.

    Always confirms in the same step (`ReviewAction.MODIFIED`): a human who
    corrects a value has, in the same motion, decided it is now final --
    matching how the Flutter review screen's single "修正" action has never
    had a separate follow-up confirm step (Issue #21's `_focusEdit`/note
    field). The original AI `GradeResult` this correction is based on stays
    retrievable unmodified (append-only; Issue #22 acceptance: "AI値を修正し
    て承認しても元AI値が参照できる").

    Requires an AI grade to already exist (`NoAiGradeYetError` otherwise) --
    see that error's docstring.
    """
    submission, _test_id = _load_submission_and_question(
        uow, submission_id=submission_id, question_id=question_id
    )
    ai_grade = _latest_ai_grade(uow, submission_id=submission_id, question_id=question_id)
    version, _existing = _next_version(
        uow,
        submission_id=submission_id,
        question_id=question_id,
        expected_version=expected_version,
    )

    grade = GradeResult(
        id=str(uuid4()),
        submission_id=submission_id,
        question_id=question_id,
        source=GradingSource.HUMAN,
        score=Score(awarded=score_awarded, maximum=score_maximum),
        confidence=confidence,
        criteria=tuple(
            CriterionResult(criterion_id=c.criterion_id, outcome=c.outcome, confidence=c.confidence)
            for c in criteria
        ),
        rationale=rationale,
        comment=comment,
        created_at=now,
    )
    recognition: RecognitionResult | None = None
    if recognized_text is not None:
        recognition = RecognitionResult(
            id=str(uuid4()),
            submission_id=submission_id,
            question_id=question_id,
            source=GradingSource.HUMAN,
            text=recognized_text,
            confidence=1.0,
            created_at=now,
        )

    if annotations is not None:
        new_annotations = [
            Annotation(
                id=str(uuid4()),
                submission_id=submission_id,
                question_id=question_id,
                source=GradingSource.HUMAN,
                kind=a.kind,
                rect=a.rect,
                anchor_text=a.anchor_text,
                comment=a.comment,
                created_at=now,
            )
            for a in annotations
        ]
    else:
        new_annotations = []

    review = Review(
        id=str(uuid4()),
        submission_id=submission_id,
        question_id=question_id,
        action=ReviewAction.MODIFIED,
        version=version,
        ai_grade_result_id=ai_grade.id,
        human_grade_result_id=grade.id,
        note=note,
        created_at=now,
    )

    uow.grades.add(grade)
    if recognition is not None:
        uow.recognitions.add(recognition)
    for annotation in new_annotations:
        uow.annotations.add(annotation)
    if annotations is None:
        new_annotations = _carry_forward_annotations(
            uow,
            submission_id=submission_id,
            question_id=question_id,
            based_on_created_at=ai_grade.created_at,
            now=now,
        )
    uow.reviews.add(review)
    submission = _sync_submission_review_state(uow, submission)
    _commit_or_conflict(
        uow, submission_id=submission_id, question_id=question_id, expected_version=expected_version
    )

    return EditResult(
        review=review,
        grade=grade,
        recognition=recognition,
        annotations=tuple(new_annotations),
        submission=submission,
    )


def reject_question(
    uow: SqlAlchemyUnitOfWork,
    *,
    submission_id: str,
    question_id: str,
    expected_version: int,
    reason: str | None,
    now: datetime,
) -> tuple[Review, Submission]:
    """Record that the AI's current proposal is unusable -- Issue #22's
    "reject" use case. Never requires an AI grade to exist (rejecting a
    question AI could not process at all -- e.g. a permanently FAILED job --
    is a legitimate outcome, matching `Review.__post_init__`'s own rule that
    only `APPROVED`/`MODIFIED` need one).
    """
    submission, _test_id = _load_submission_and_question(
        uow, submission_id=submission_id, question_id=question_id
    )
    ai_grade = uow.grades.latest(submission_id, question_id, GradingSource.AI)
    version, _existing = _next_version(
        uow,
        submission_id=submission_id,
        question_id=question_id,
        expected_version=expected_version,
    )
    review = Review(
        id=str(uuid4()),
        submission_id=submission_id,
        question_id=question_id,
        action=ReviewAction.REJECTED,
        version=version,
        ai_grade_result_id=ai_grade.id if ai_grade is not None else None,
        note=reason,
        created_at=now,
    )
    uow.reviews.add(review)
    submission = _sync_submission_review_state(uow, submission)
    _commit_or_conflict(
        uow, submission_id=submission_id, question_id=question_id, expected_version=expected_version
    )
    return review, submission


def regrade_question(
    uow: SqlAlchemyUnitOfWork,
    *,
    submission_id: str,
    question_id: str,
    expected_version: int,
    reason: str | None,
    now: datetime,
) -> tuple[Review, Job, Submission]:
    """Create (but do not enqueue -- see the return value) a fresh AI attempt
    for this question -- Issue #22's "regrade" use case. The caller
    (`api.review_router`) is responsible for handing the returned `Job.id` to
    `jobs.queue.JobQueueService.enqueue` *after* this call's transaction has
    committed, the same ordering `JobQueueService.submit_submission` itself
    uses -- this module stays free of any dependency on the `jobs` package
    (`AGENTS.md` "Architecture": keep a single, explicit dependency
    direction), and enqueuing only an already-committed job avoids a worker
    picking it up before its row is even visible to other readers.

    Creates a brand-new `Job` (kind GRADING, own uuid) rather than
    reusing or mutating any existing one: this question's prior attempt(s)
    may already be SUCCEEDED/FAILED (a terminal `JobState` nothing can
    transition out of, `models.ensure_job_transition`), and the append-only
    history model means a redo is simply one more attempt, not a correction
    to the old one.

    ``dependency_graph_version`` is deliberately left ``None`` (unlike a
    `submit_submission`-created job): this is a single, manually-triggered
    re-attempt, not part of the automatic per-submission DAG scheduling
    `JobQueueService.submit_submission` owns, and giving it a real graph
    version would collide with that DAG's own idempotency key
    (``uq_jobs_submission_question_graph_version`` -- SQLite's "NULL is
    distinct from everything" is exactly what lets a second, third, ... redo
    for the same question all coexist here, same reasoning as that
    constraint's own docstring). `GradingJobProcessor.process` reads the
    test's confirmed graph independently by id, not from this field, so
    grading itself is unaffected.

    Like `reject_question`, does not require an AI grade to already exist
    (regrading is exactly how a reviewer recovers from "AI never produced
    one").
    """
    submission, _test_id = _load_submission_and_question(
        uow, submission_id=submission_id, question_id=question_id
    )
    ai_grade = uow.grades.latest(submission_id, question_id, GradingSource.AI)
    version, _existing = _next_version(
        uow,
        submission_id=submission_id,
        question_id=question_id,
        expected_version=expected_version,
    )
    job = Job(
        id=str(uuid4()),
        kind=JobKind.GRADING,
        submission_id=submission_id,
        question_id=question_id,
        created_at=now,
        updated_at=now,
        state=JobState.QUEUED,
        dependency_graph_version=None,
    )
    review = Review(
        id=str(uuid4()),
        submission_id=submission_id,
        question_id=question_id,
        action=ReviewAction.REGRADE_REQUESTED,
        version=version,
        ai_grade_result_id=ai_grade.id if ai_grade is not None else None,
        regrade_job_id=job.id,
        note=reason,
        created_at=now,
    )
    uow.jobs.add(job)
    uow.reviews.add(review)
    submission = _sync_submission_review_state(uow, submission)
    _commit_or_conflict(
        uow, submission_id=submission_id, question_id=question_id, expected_version=expected_version
    )
    return review, job, submission


def approve_question(
    uow: SqlAlchemyUnitOfWork,
    *,
    submission_id: str,
    question_id: str,
    expected_version: int,
    note: str | None,
    now: datetime,
) -> tuple[Review, Submission]:
    """Confirm the AI's current proposal as-is -- Issue #22's "approve" half
    of "approve-and-next" (the "next" half is pure client-side navigation,
    `app.lib.features.pdf_review.pdf_review_page._approveAndNext`).

    Requires an AI grade to exist (`NoAiGradeYetError` otherwise), mirroring
    the pre-existing Flutter `_canApprove` gate this replaces.
    """
    submission, _test_id = _load_submission_and_question(
        uow, submission_id=submission_id, question_id=question_id
    )
    ai_grade = _latest_ai_grade(uow, submission_id=submission_id, question_id=question_id)
    version, _existing = _next_version(
        uow,
        submission_id=submission_id,
        question_id=question_id,
        expected_version=expected_version,
    )
    review = Review(
        id=str(uuid4()),
        submission_id=submission_id,
        question_id=question_id,
        action=ReviewAction.APPROVED,
        version=version,
        ai_grade_result_id=ai_grade.id,
        note=note,
        created_at=now,
    )
    uow.reviews.add(review)
    submission = _sync_submission_review_state(uow, submission)
    _commit_or_conflict(
        uow, submission_id=submission_id, question_id=question_id, expected_version=expected_version
    )
    return review, submission


def undo_last_review(
    uow: SqlAlchemyUnitOfWork,
    *,
    submission_id: str,
    question_id: str,
    expected_version: int,
    now: datetime,
) -> tuple[Review, Submission]:
    """Revert the currently-effective human review action as a *new* row
    (Ctrl+Z, Issue #22 "実施内容": "直前の人間操作を履歴上の新操作として取り
    消し、監査履歴自体は削除しない"). Never deletes or mutates
    ``target``'s row -- see `domain.review_workflow.effective_latest_review`,
    which is what makes the reverted row still show up, clearly, in this
    question's full history.

    Raises `NothingToUndoError` if every row has already been undone (or
    none exists). Redo is out of scope for Issue #22 -- see
    `domain.review_workflow.effective_latest_review`'s docstring.
    """
    submission, _test_id = _load_submission_and_question(
        uow, submission_id=submission_id, question_id=question_id
    )
    version, existing = _next_version(
        uow,
        submission_id=submission_id,
        question_id=question_id,
        expected_version=expected_version,
    )
    target = effective_latest_review(existing)
    if target is None:
        raise NothingToUndoError(submission_id, question_id)
    review = Review(
        id=str(uuid4()),
        submission_id=submission_id,
        question_id=question_id,
        action=ReviewAction.UNDONE,
        version=version,
        undone_review_id=target.id,
        created_at=now,
    )
    uow.reviews.add(review)
    submission = _sync_submission_review_state(uow, submission)
    _commit_or_conflict(
        uow, submission_id=submission_id, question_id=question_id, expected_version=expected_version
    )
    return review, submission
