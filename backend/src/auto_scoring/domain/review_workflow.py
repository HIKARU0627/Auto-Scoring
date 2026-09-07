"""Pure rules for the review operation history (Issue #22, parent #3).

Framework-free (`AGENTS.md` "Architecture"): everything here is plain
functions over `Review`/`GradeResult` sequences already read by the caller
(`adapters.review_actions`) -- no repository, no SQLAlchemy, no FastAPI.

Three concerns live here, all specific to *reasoning about* the append-only
`Review` table `domain.models` already defines, not to any one HTTP action:

* Optimistic concurrency (`next_review_version`): the version token a new
  `Review` row must carry, and the conflict that reports when a caller's
  belief about the current version is stale.
* Undo (`effective_latest_review`): which `Review` row is "in effect" once
  some suffix of the history may have been reverted by a later ``undone``
  row, without ever deleting anything.
* Submission-level completeness (`all_questions_confirmed`): whether every
  question of a submission currently has a confirmed (``approved``/
  ``modified``) outcome in effect, gating the `Submission.REVIEWED`
  transition (Issue #22 acceptance: "未確認設問が残るSubmissionは出力可能状態
  にならない").

See `docs/review-edit-history.md` for the full design record these
implement.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from auto_scoring.domain.models import (
    CONFIRMED_REVIEW_ACTIONS,
    DomainError,
    GradeResult,
    GradingSource,
    RecognitionResult,
    Review,
    ReviewAction,
)


class ReviewVersionConflict(DomainError):
    """A review action's ``expected_version`` no longer matches this
    ``(submission_id, question_id)``'s actual history length -- another
    request (a concurrent action, or a duplicate retry of this same one)
    already appended a row since the caller last read the history.

    Raised here as a cheap, in-process pre-check before ever touching the
    database; `db.orm.ReviewRow`'s own
    ``uq_reviews_submission_question_version`` unique constraint is the real
    guard against two *concurrent* requests both passing this check with the
    same stale belief (AGENTS.md "invariants は…実制約で") -- see
    `adapters.review_actions` for how a resulting `IntegrityError` is turned
    into this same error.
    """

    def __init__(self, submission_id: str, question_id: str, *, expected: int, actual: int) -> None:
        super().__init__(
            f"{submission_id!r}:{question_id!r}: expected version {expected} but the review "
            f"history is already at {actual}; reload and retry"
        )
        self.submission_id = submission_id
        self.question_id = question_id
        self.expected = expected
        self.actual = actual


def next_review_version(
    existing_reviews: Sequence[Review],
    *,
    expected_version: int,
    submission_id: str,
    question_id: str,
) -> int:
    """The version the next `Review` row for this pair must carry.

    ``expected_version`` is what the caller (a review-screen client) last
    observed as this pair's history length -- ``0`` if it has never loaded
    any review for this question. Raises `ReviewVersionConflict` if that no
    longer matches ``len(existing_reviews)``.
    """
    actual = len(existing_reviews)
    if actual != expected_version:
        raise ReviewVersionConflict(
            submission_id, question_id, expected=expected_version, actual=actual
        )
    return actual + 1


def effective_latest_review(reviews: Sequence[Review]) -> Review | None:
    """The `Review` row currently "in effect" for one submission-question,
    accounting for any ``undone`` rows -- without ever removing anything
    from ``reviews`` itself (append-only).

    ``reviews`` must be oldest-first (every `ReviewRepository.history` result
    already is). An ``undone`` row and the row it names
    (``Review.undone_review_id``) are both excluded from consideration; the
    latest remaining row (by position) is the effective one, or ``None`` if
    every row has been undone (or there are no rows at all) -- meaning this
    question is back to its plain, unconfirmed AI-proposal state.

    Redo is out of scope for Issue #22 (its own "実施内容" only asks for
    undoing "直前の人間操作", not redoing an undo) -- see
    `docs/review-edit-history.md` "Undo/Redo". Without it, an ``undone`` row
    and its target always form a simple, non-overlapping pair, so a plain
    exclusion set is sufficient; nothing here needs to reconstruct the exact
    order operations happened in.
    """
    excluded: set[str] = set()
    for review in reviews:
        if review.action is ReviewAction.UNDONE:
            excluded.add(review.id)
            assert review.undone_review_id is not None  # Review.__post_init__ already requires this
            excluded.add(review.undone_review_id)
    for review in reversed(reviews):
        if review.id not in excluded:
            return review
    return None


def is_confirmed(review: Review | None) -> bool:
    """Whether ``review`` (typically `effective_latest_review`'s result)
    represents a confirmed grade -- ``approved`` or ``modified``, and not
    since undone.
    """
    return review is not None and review.action in CONFIRMED_REVIEW_ACTIONS


def all_questions_confirmed(
    question_ids: Iterable[str], reviews_by_question: Mapping[str, Sequence[Review]]
) -> bool:
    """Whether every id in ``question_ids`` currently has a confirmed
    (`is_confirmed`) effective review -- the gate for a `Submission`'s
    ``REVIEWED`` transition (Issue #22 acceptance: "未確認設問が残る
    Submissionは出力可能状態にならない"). A question missing from
    ``reviews_by_question`` entirely (never reviewed at all) is unconfirmed.
    """
    return all(
        is_confirmed(effective_latest_review(reviews_by_question.get(question_id, ())))
        for question_id in question_ids
    )


def resolve_effective_grade(
    reviews: Sequence[Review], grades: Sequence[GradeResult]
) -> GradeResult | None:
    """The `GradeResult` currently "in effect" for one question, given its
    full review history and full grade history -- the domain twin of the
    Flutter review screen's own `QuestionReviewState.displayGrade` (Issue #22
    P1 review: a downstream consumer picking "the latest human grade by
    timestamp" instead of resolving through the review history keeps using a
    correction Undo has already reverted).

    `effective_latest_review(reviews)`'s ``modified`` -> its own
    ``human_grade_result_id``; ``approved`` -> its own ``ai_grade_result_id``;
    anything else (``rejected``/``regrade_requested``, or nothing reviewed
    yet) -> the latest AI-sourced grade, so a fresh AI attempt after a
    rejection/regrade still resolves once it lands, matching `displayGrade`'s
    own ``default`` branch.
    """
    review = effective_latest_review(reviews)
    grade_by_id = {grade.id: grade for grade in grades}
    if review is not None:
        target_id = (
            review.human_grade_result_id
            if review.action is ReviewAction.MODIFIED
            else review.ai_grade_result_id
            if review.action is ReviewAction.APPROVED
            else None
        )
        if target_id is not None:
            grade = grade_by_id.get(target_id)
            if grade is not None:
                return grade
    ai_grades = [grade for grade in grades if grade.source is GradingSource.AI]
    return ai_grades[-1] if ai_grades else None


def resolve_effective_recognition(
    reviews: Sequence[Review],
    grades: Sequence[GradeResult],
    recognitions: Sequence[RecognitionResult],
) -> RecognitionResult | None:
    """The `RecognitionResult` currently "in effect" for one question -- the
    domain twin of the Flutter review screen's own
    `QuestionReviewState.effectiveHumanRecognition` fallback chain (Issue #22
    P1 review, same reasoning as `resolve_effective_grade`).

    A ``modified`` review in effect shows the human recognition sharing its
    own human grade's ``created_at`` (`adapters.review_actions.edit_question`
    persists both from the same clock read, the same signal
    `QuestionReviewState.annotationsForDisplayedAttempt` already relies on),
    falling back to the latest AI-sourced recognition if that edit did not
    touch the recognized text at all (or once Undo reverts back past it) --
    the AI branch naturally picks the *grading*-stage recognition over the
    earlier *OCR*-stage one for the same attempt, since
    `GradingJobProcessor.process` always commits the OCR-stage row first.
    """
    review = effective_latest_review(reviews)
    if (
        review is not None
        and review.action is ReviewAction.MODIFIED
        and review.human_grade_result_id is not None
    ):
        grade_by_id = {grade.id: grade for grade in grades}
        human_grade = grade_by_id.get(review.human_grade_result_id)
        if human_grade is not None:
            human_recognitions = [
                recognition
                for recognition in recognitions
                if recognition.source is GradingSource.HUMAN
                and recognition.created_at == human_grade.created_at
            ]
            if human_recognitions:
                return human_recognitions[-1]
    ai_recognitions = [
        recognition for recognition in recognitions if recognition.source is GradingSource.AI
    ]
    return ai_recognitions[-1] if ai_recognitions else None
