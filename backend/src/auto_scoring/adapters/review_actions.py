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
   `RecognitionResult`/`Annotation` set for `edit_question` and
   `grade_question_manually`; a fresh `Job` for `regrade_question`; nothing
   extra for `reject_question`/`approve_question`/`undo_last_review`).
3. Appends the new `Review` row and re-syncs the submission's
   `SubmissionState` (`_sync_submission_review_state`) in the *same*
   transaction, then commits -- all through `_finalize_review`.

The version check in step 1 is a cheap pre-check; the real guard against two
concurrent/duplicate requests both winning is
``uq_reviews_submission_question_version`` (`db.orm.ReviewRow`) -- a
concurrent caller that also passed step 1 (because it read the history before
this transaction committed) hits that constraint's `IntegrityError`. That can
surface as early as `SqlAlchemyReviewRepository.add`'s own immediate
`session.flush()`, not only at the final `uow.commit()` (P2 review) --
`_finalize_review` wraps both in one conflict-handling block, re-raising
either as the same `ReviewVersionConflict` the pre-check would have raised
from a fresh read.
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
    Question,
    RecognitionResult,
    Review,
    ReviewAction,
    Score,
    ScoreOutOfRange,
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


class AiGradeAlreadyExistsError(Exception):
    """`grade_question_manually` refused: this question *does* have an AI
    grade, so it is not the "AI produced nothing" case that route exists for
    (Issue #118).

    Recording a from-scratch human grade here would silently set aside an AI
    attempt the reviewer may never have seen -- the same hazard
    `AiGradeChangedError` guards on ``edit``/``approve``, which is why the
    answer is the same: reload, look at the attempt, and approve or correct
    it.
    """

    def __init__(self, submission_id: str, question_id: str, *, ai_grade_id: str) -> None:
        super().__init__(
            f"{submission_id!r}:{question_id!r} already has an AI grade ({ai_grade_id!r}); "
            "reload and approve or edit it instead"
        )
        self.submission_id = submission_id
        self.question_id = question_id
        self.ai_grade_id = ai_grade_id


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


class AiGradeChangedError(Exception):
    """`edit_question`/`approve_question` refused: the caller's
    ``expected_ai_grade_id`` no longer matches this question's latest AI
    grade (Issue #22 P1 review).

    `regrade_question` completing (`GradingJobProcessor.process` persisting a
    fresh AI `GradeResult`) never appends a `Review` row, so
    ``expected_version``'s own optimistic-concurrency check alone cannot
    detect a regrade that lands after the review screen loaded but before
    this approve/edit reached the server -- without this separate check, an
    approval/correction could silently attach itself to an AI attempt the
    reviewer never actually saw. The caller must reload this question's
    state and decide again against the current attempt.
    """

    def __init__(
        self, submission_id: str, question_id: str, *, expected: str | None, actual: str
    ) -> None:
        super().__init__(
            f"{submission_id!r}:{question_id!r}: expected AI grade {expected!r} but the "
            f"latest AI grade is now {actual!r}; reload and retry"
        )
        self.submission_id = submission_id
        self.question_id = question_id
        self.expected = expected
        self.actual = actual


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
) -> tuple[Submission, Question]:
    """Returns ``(submission, question)`` after validating both exist and
    belong together -- the same three checks every mutating handler in
    `api.recognitions_router` already makes before writing anything."""
    submission = uow.submissions.get(submission_id)
    if submission is None:
        raise LookupError(f"submission {submission_id!r} not found")
    question = uow.questions.get(question_id)
    if question is None:
        raise LookupError(f"question {question_id!r} not found")
    if question.test_id != submission.test_id:
        raise QuestionMismatchError(submission_id, question_id)
    return submission, question


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


#: The states a review action can legitimately have happened against, and so the
#: only ones `_sync_submission_review_state` moves between.
#:
#: `AI_PROCESSED` is here because it is what a *cleanly intaken* submission is
#: (Issue #112): `adapters.submission_intake` only routes on to `NEEDS_REVIEW`
#: when it could not pin the answer areas, which makes `AI_PROCESSED` the normal
#: case rather than a mid-processing one. Leaving it out is why approving every
#: question of an ordinary submission used to record nothing at all.
#:
#: Still excluded: `UNPROCESSED`/`AI_PROCESSING` (nothing to have reviewed yet),
#: `EXPORTED` (reopening an exported submission is a later issue's job) and
#: `ERROR`.
_REVIEWABLE_SUBMISSION_STATES = (
    SubmissionState.AI_PROCESSED,
    SubmissionState.NEEDS_REVIEW,
    SubmissionState.REVIEWED,
)


def _unconfirmed_state(submission: Submission) -> SubmissionState:
    """Where a submission belongs while some question of it is *not* confirmed
    -- which is wherever intake left it (Issue #112).

    ``review_reason`` is the record of that, and the only one there is: intake
    writes it on every outcome through ``mark_intake_outcome`` (a reason when it
    routed the submission to `NEEDS_REVIEW`, ``None`` when it did not), and
    ``set_state`` never touches it. So a non-null reason means intake itself
    flagged this submission, and a null one means intake finished cleanly.

    The distinction matters because `NEEDS_REVIEW` is not a neutral "not done
    yet": it is the one state this app colours as *needing a person*
    (`docs/design-tokens.md` §3.1) and the one ホーム画面 opens first
    (`HomeDashboard._pickResumable`). Undoing one approval on a submission
    whose intake was fine must not manufacture that signal.
    """
    if submission.review_reason is not None:
        return SubmissionState.NEEDS_REVIEW
    return SubmissionState.AI_PROCESSED


def _sync_submission_review_state(uow: SqlAlchemyUnitOfWork, submission: Submission) -> Submission:
    """Move ``submission`` to match whether every one of its questions currently
    has a confirmed effective review -- run inside the same transaction as the
    `Review` row that triggered the recheck, so the two commit atomically
    together.

    Confirmed means `domain.review_workflow.all_questions_confirmed`, and
    nothing else: an ``approved``/``modified`` `Review` that Undo has not since
    reverted. **No Confidence value reaches this decision** (簡易設計書 §25.2) --
    "確認済み" is the record of a person having confirmed, so deriving it from
    what the AI thought would make it stop being evidence that anyone looked.

    Introduced for Issue #22 ("未確認設問が残るSubmissionは出力可能状態にならない")
    as the gate on that, but that is not what it turned out to be: Issue #23 made
    export check the review history itself (`domain.pdf_export`), so what this
    writes is a *mirror* of that same fact, for the screens to count. Which is
    why Issue #112 could widen it to `AI_PROCESSED` without touching export --
    see `docs/review-edit-history.md` §6.

    A no-op outside [_REVIEWABLE_SUBMISSION_STATES].
    """
    if submission.state not in _REVIEWABLE_SUBMISSION_STATES:
        return submission
    # Only the graded questions gate 確認済み (Issue #449): an excluded
    # question must not keep the submission "unconfirmed" forever.
    questions = uow.questions.list_for_test(submission.test_id, scoring_targets_only=True)
    reviews_by_question = {q.id: uow.reviews.history(submission.id, q.id) for q in questions}
    confirmed = all_questions_confirmed((q.id for q in questions), reviews_by_question)
    target = SubmissionState.REVIEWED if confirmed else _unconfirmed_state(submission)
    if target is submission.state:
        return submission
    uow.submissions.set_state(submission.id, target)
    return replace(submission, state=target)


def _finalize_review(
    uow: SqlAlchemyUnitOfWork,
    review: Review,
    submission: Submission,
    *,
    expected_version: int,
) -> Submission:
    """Add ``review``'s row, re-sync ``submission``'s review state, and
    commit -- one conflict-handling block covering both (P2 review):
    `SqlAlchemyReviewRepository.add` flushes immediately, so a concurrent
    writer's `IntegrityError` (the unique constraint on ``version``) can
    surface right there, not only at the final `uow.commit()` a narrower
    ``try`` around just the commit would have missed. Either way it is
    converted into the same `ReviewVersionConflict` a fresh read would have
    raised -- see this module's own docstring, point 3.
    """
    try:
        uow.reviews.add(review)
        submission = _sync_submission_review_state(uow, submission)
        uow.commit()
    except IntegrityError as error:
        uow.rollback()
        raise ReviewVersionConflict(
            review.submission_id,
            review.question_id,
            expected=expected_version,
            actual=expected_version + 1,
        ) from error
    return submission


def _latest_ai_grade(
    uow: SqlAlchemyUnitOfWork, *, submission_id: str, question_id: str
) -> GradeResult:
    grade = uow.grades.latest(submission_id, question_id, GradingSource.AI)
    if grade is None:
        raise NoAiGradeYetError(submission_id, question_id)
    return grade


def _latest_ai_grade_matching(
    uow: SqlAlchemyUnitOfWork,
    *,
    submission_id: str,
    question_id: str,
    expected_ai_grade_id: str | None,
) -> GradeResult:
    """`_latest_ai_grade`, additionally refusing (`AiGradeChangedError`) if
    ``expected_ai_grade_id`` is given and no longer names the latest AI
    grade -- see that error's docstring. ``None`` skips the check entirely
    (a caller that never loaded an AI grade at all -- e.g. an older client --
    has nothing to compare against; this only guards a client that *did*
    display one).
    """
    grade = _latest_ai_grade(uow, submission_id=submission_id, question_id=question_id)
    if expected_ai_grade_id is not None and grade.id != expected_ai_grade_id:
        raise AiGradeChangedError(
            submission_id, question_id, expected=expected_ai_grade_id, actual=grade.id
        )
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
    expected_ai_grade_id: str | None = None,
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
    see that error's docstring. ``expected_ai_grade_id``, if given, must name
    that AI grade or this refuses with `AiGradeChangedError` (Issue #22 P1
    review: a regrade must not let this edit silently record an AI baseline
    the reviewer never actually saw).
    """
    submission, question = _load_submission_and_question(
        uow, submission_id=submission_id, question_id=question_id
    )
    if score_maximum != question.points:
        # A human correction always scores against this question's own,
        # already-registered rubric total -- not a value the caller invents
        # per request. Never simply clamped or otherwise coerced: silently
        # accepting a mismatched maximum would let an out-of-range score
        # flow downstream into a confirmed `GradeResult` (and, through it,
        # into a dependent question's grading context) as if it had been
        # legitimately scored (Issue #22 P2 review, round 2). Mirrors
        # `GradingJobProcessor.process`'s identical
        # ``response.max_score != question.points`` check for an AI
        # response -- validating the client boundary (the Flutter dialog's
        # own `question.points`-based bound) is not enough on its own
        # (AGENTS.md "Security": validate every input crossing a trust
        # boundary).
        raise ScoreOutOfRange(
            f"score_maximum {score_maximum} does not match question {question_id!r}'s "
            f"registered points ({question.points})"
        )
    ai_grade = _latest_ai_grade_matching(
        uow,
        submission_id=submission_id,
        question_id=question_id,
        expected_ai_grade_id=expected_ai_grade_id,
    )
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
    submission = _finalize_review(uow, review, submission, expected_version=expected_version)

    return EditResult(
        review=review,
        grade=grade,
        recognition=recognition,
        annotations=tuple(new_annotations),
        submission=submission,
    )


def grade_question_manually(
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
    """A human's grade for a question the AI never graded -- Issue #118.

    **The gap this fills.** When AI grading fails permanently no
    `GradeResult` is written at all: Issue #97 decided that deliberately, so
    that nothing that looks like a grade exists unless something actually
    produced one, and that decision is not revisited here. But every way a
    person could record their own decision went through the AI's row --
    `approve_question` confirms it, `edit_question` corrects it, both raise
    `NoAiGradeYetError` without one -- so a question the AI could not grade
    could not be graded by a person either, and the answer sheet stopped
    there. On a Friday afternoon with forty of them on the desk, that is the
    whole stack stopping.

    **A separate route, not a relaxed `edit_question`.** Refuses
    (`AiGradeAlreadyExistsError`) if an AI grade *does* exist, so "the AI
    produced nothing" stays something the caller asserts and the server
    checks, rather than something inferred from an omitted
    ``expected_ai_grade_id``. A regrade landing between the screen loading
    and this call arriving therefore surfaces as a conflict, exactly like a
    stale ``expected_ai_grade_id`` does on the other two routes (Issue #22
    P1 review), instead of quietly recording a grade that ignores an attempt
    nobody saw.

    Records `ReviewAction.MODIFIED` with ``ai_grade_result_id=None``: the
    field means *the AI attempt this decision was made against*, and there
    was none. That is what makes the history say "a person graded this from
    scratch" rather than "a person corrected something" -- see
    `domain.models.Review`. Reusing ``MODIFIED`` rather than adding a sixth
    `ReviewAction` is deliberate: every consumer of "this question is
    confirmed" (`domain.review_workflow.all_questions_confirmed` and the
    `Submission.REVIEWED` transition it gates, `domain.pdf_export`'s export
    gate, `resolve_effective_grade`, the review screen's own status
    vocabulary) already treats a ``MODIFIED`` row with a human grade exactly
    the way this one needs to be treated, and a new value would have to be
    taught to each of them one at a time.

    Annotations behave like `edit_question`'s explicit-list case and unlike
    its default: there is no AI attempt whose marks could be carried
    forward, so omitting ``annotations`` records none rather than copying
    anything.
    """
    submission, question = _load_submission_and_question(
        uow, submission_id=submission_id, question_id=question_id
    )
    if score_maximum != question.points:
        # Same trust-boundary check as `edit_question` -- see its comment.
        raise ScoreOutOfRange(
            f"score_maximum {score_maximum} does not match question {question_id!r}'s "
            f"registered points ({question.points})"
        )
    existing_ai_grade = uow.grades.latest(submission_id, question_id, GradingSource.AI)
    if existing_ai_grade is not None:
        raise AiGradeAlreadyExistsError(
            submission_id, question_id, ai_grade_id=existing_ai_grade.id
        )
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
        for a in annotations or ()
    ]
    review = Review(
        id=str(uuid4()),
        submission_id=submission_id,
        question_id=question_id,
        action=ReviewAction.MODIFIED,
        version=version,
        ai_grade_result_id=None,
        human_grade_result_id=grade.id,
        note=note,
        created_at=now,
    )

    uow.grades.add(grade)
    if recognition is not None:
        uow.recognitions.add(recognition)
    for annotation in new_annotations:
        uow.annotations.add(annotation)
    submission = _finalize_review(uow, review, submission, expected_version=expected_version)

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
    submission, _question = _load_submission_and_question(
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
    submission = _finalize_review(uow, review, submission, expected_version=expected_version)
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
    submission, _question = _load_submission_and_question(
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
    submission = _finalize_review(uow, review, submission, expected_version=expected_version)
    return review, job, submission


def approve_question(
    uow: SqlAlchemyUnitOfWork,
    *,
    submission_id: str,
    question_id: str,
    expected_version: int,
    expected_ai_grade_id: str | None = None,
    note: str | None,
    now: datetime,
) -> tuple[Review, Submission]:
    """Confirm the AI's current proposal as-is -- Issue #22's "approve" half
    of "approve-and-next" (the "next" half is pure client-side navigation,
    `app.lib.features.pdf_review.pdf_review_page._approveAndNext`).

    Requires an AI grade to exist (`NoAiGradeYetError` otherwise), mirroring
    the pre-existing Flutter `_canApprove` gate this replaces.
    ``expected_ai_grade_id``, if given, must name that AI grade or this
    refuses with `AiGradeChangedError` -- see that error's docstring (Issue
    #22 P1 review: a regrade completing after the reviewer loaded the screen
    must not let this approval silently confirm an attempt they never saw).
    """
    submission, _question = _load_submission_and_question(
        uow, submission_id=submission_id, question_id=question_id
    )
    ai_grade = _latest_ai_grade_matching(
        uow,
        submission_id=submission_id,
        question_id=question_id,
        expected_ai_grade_id=expected_ai_grade_id,
    )
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
    submission = _finalize_review(uow, review, submission, expected_version=expected_version)
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
    submission, _question = _load_submission_and_question(
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
    submission = _finalize_review(uow, review, submission, expected_version=expected_version)
    return review, submission
