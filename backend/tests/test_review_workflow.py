"""Unit tests for `auto_scoring.domain.review_workflow` (Issue #22, parent #3).

Pure-function tests: no database, no HTTP -- see `tests/test_review_api.py`
for the integration tests that exercise the same rules through the API.
"""

from __future__ import annotations

import pytest

from auto_scoring.domain.models import GradingSource, ReviewAction
from auto_scoring.domain.review_workflow import (
    ReviewVersionConflict,
    all_questions_confirmed,
    effective_latest_review,
    is_confirmed,
    next_review_version,
    resolve_effective_grade,
    resolve_effective_recognition,
)
from tests.support import at, make_grade, make_recognition, make_review


def test_next_review_version_starts_at_one() -> None:
    version = next_review_version([], expected_version=0, submission_id="sub-1", question_id="q-1")
    assert version == 1


def test_next_review_version_matches_history_length() -> None:
    existing = [make_review(id="r1"), make_review(id="r2", version=2, created_at=at(1))]
    version = next_review_version(
        existing, expected_version=2, submission_id="sub-1", question_id="q-1"
    )
    assert version == 3


def test_next_review_version_rejects_a_stale_expectation() -> None:
    existing = [make_review(id="r1")]
    with pytest.raises(ReviewVersionConflict) as excinfo:
        next_review_version(existing, expected_version=0, submission_id="sub-1", question_id="q-1")
    assert excinfo.value.expected == 0
    assert excinfo.value.actual == 1


def test_effective_latest_review_is_none_for_empty_history() -> None:
    assert effective_latest_review([]) is None


def test_effective_latest_review_is_the_last_row_when_nothing_is_undone() -> None:
    reviews = [
        make_review(id="r1", action=ReviewAction.APPROVED),
        make_review(id="r2", version=2, action=ReviewAction.REJECTED, created_at=at(1)),
    ]
    result = effective_latest_review(reviews)
    assert result is not None
    assert result.id == "r2"


def test_effective_latest_review_skips_an_undone_row_and_its_target() -> None:
    reviews = [
        make_review(id="r1", action=ReviewAction.APPROVED),
        make_review(
            id="r2",
            version=2,
            action=ReviewAction.UNDONE,
            ai_grade_result_id=None,
            undone_review_id="r1",
            created_at=at(1),
        ),
    ]
    assert effective_latest_review(reviews) is None


def test_effective_latest_review_reverts_to_an_earlier_action_after_undo() -> None:
    """Undo(edit) reverts to whatever was in effect before the edit -- here,
    an earlier `approved` row, not "nothing" (Issue #22 P1: Undo must be able
    to fall back further than one step)."""
    reviews = [
        make_review(id="r1", action=ReviewAction.APPROVED),
        make_review(
            id="r2",
            version=2,
            action=ReviewAction.MODIFIED,
            human_grade_result_id="grade-human",
            created_at=at(1),
        ),
        make_review(
            id="r3",
            version=3,
            action=ReviewAction.UNDONE,
            ai_grade_result_id=None,
            undone_review_id="r2",
            created_at=at(2),
        ),
    ]
    result = effective_latest_review(reviews)
    assert result is not None
    assert result.id == "r1"


def test_is_confirmed_true_only_for_approved_or_modified() -> None:
    assert is_confirmed(make_review(action=ReviewAction.APPROVED)) is True
    assert (
        is_confirmed(make_review(action=ReviewAction.MODIFIED, human_grade_result_id="g-human"))
        is True
    )
    assert is_confirmed(make_review(action=ReviewAction.REJECTED, ai_grade_result_id=None)) is False
    assert is_confirmed(None) is False


def test_all_questions_confirmed_requires_every_question_to_have_a_confirmed_review() -> None:
    reviews_by_question = {
        "q-1": [make_review(question_id="q-1", action=ReviewAction.APPROVED)],
        "q-2": [
            make_review(question_id="q-2", action=ReviewAction.REJECTED, ai_grade_result_id=None)
        ],
    }
    assert all_questions_confirmed(["q-1", "q-2"], reviews_by_question) is False
    assert all_questions_confirmed(["q-1"], reviews_by_question) is True


def test_all_questions_confirmed_treats_a_missing_question_as_unconfirmed() -> None:
    assert all_questions_confirmed(["q-1"], {}) is False


def test_resolve_effective_grade_is_the_latest_ai_grade_when_nothing_is_reviewed() -> None:
    grades = [make_grade(id="g-ai-1"), make_grade(id="g-ai-2", created_at=at(1))]
    assert resolve_effective_grade([], grades) is grades[-1]


def test_resolve_effective_grade_follows_a_modified_reviews_own_human_grade() -> None:
    grades = [make_grade(id="g-ai"), make_grade(id="g-human", source=GradingSource.HUMAN)]
    reviews = [
        make_review(
            action=ReviewAction.MODIFIED,
            ai_grade_result_id="g-ai",
            human_grade_result_id="g-human",
        )
    ]
    result = resolve_effective_grade(reviews, grades)
    assert result is not None
    assert result.id == "g-human"


def test_resolve_effective_grade_follows_an_approved_reviews_own_ai_grade() -> None:
    grades = [make_grade(id="g-ai-1"), make_grade(id="g-ai-2", created_at=at(1))]
    reviews = [make_review(action=ReviewAction.APPROVED, ai_grade_result_id="g-ai-1")]
    result = resolve_effective_grade(reviews, grades)
    assert result is not None
    assert result.id == "g-ai-1"


def test_resolve_effective_grade_reverts_to_the_latest_ai_grade_after_undo() -> None:
    """Issue #22 P1 review: a downstream consumer resolving "the" grade for
    a question must stop seeing a `modified` review's human correction once
    Undo reverts it -- the same guarantee `QuestionReviewState.displayGrade`
    already gives the review screen itself."""
    grades = [make_grade(id="g-ai"), make_grade(id="g-human", source=GradingSource.HUMAN)]
    modified = make_review(
        id="r1",
        action=ReviewAction.MODIFIED,
        ai_grade_result_id="g-ai",
        human_grade_result_id="g-human",
    )
    reviews = [
        modified,
        make_review(
            id="r2",
            version=2,
            action=ReviewAction.UNDONE,
            ai_grade_result_id=None,
            undone_review_id="r1",
            created_at=at(1),
        ),
    ]
    result = resolve_effective_grade(reviews, grades)
    assert result is not None
    assert result.id == "g-ai"


def test_resolve_effective_recognition_is_the_latest_ai_recognition_by_default() -> None:
    recognitions = [
        make_recognition(id="rec-ai-1"),
        make_recognition(id="rec-ai-2", created_at=at(1)),
    ]
    assert resolve_effective_recognition([], [], recognitions) is recognitions[-1]


def test_resolve_effective_recognition_follows_a_modified_reviews_own_human_edit() -> None:
    """`edit_question` persists the human `GradeResult` and (if the edit
    touched the text) `RecognitionResult` from the same clock read -- the
    shared `created_at` is what ties them together."""
    grades = [
        make_grade(id="g-ai"),
        make_grade(id="g-human", source=GradingSource.HUMAN, created_at=at(5)),
    ]
    recognitions = [
        make_recognition(id="rec-ai"),
        make_recognition(
            id="rec-human", source=GradingSource.HUMAN, text="人による修正", created_at=at(5)
        ),
    ]
    reviews = [
        make_review(
            action=ReviewAction.MODIFIED,
            ai_grade_result_id="g-ai",
            human_grade_result_id="g-human",
        )
    ]
    result = resolve_effective_recognition(reviews, grades, recognitions)
    assert result is not None
    assert result.id == "rec-human"


def test_resolve_effective_recognition_falls_back_to_ai_when_the_edit_did_not_touch_text() -> None:
    """An edit that only changed the score (no `recognized_text`) never
    creates a human `RecognitionResult` at all -- the effective recognition
    must still fall back to the latest AI one, not disappear."""
    grades = [
        make_grade(id="g-ai"),
        make_grade(id="g-human", source=GradingSource.HUMAN, created_at=at(5)),
    ]
    recognitions = [make_recognition(id="rec-ai")]
    reviews = [
        make_review(
            action=ReviewAction.MODIFIED,
            ai_grade_result_id="g-ai",
            human_grade_result_id="g-human",
        )
    ]
    result = resolve_effective_recognition(reviews, grades, recognitions)
    assert result is not None
    assert result.id == "rec-ai"


def test_resolve_effective_recognition_reverts_to_ai_after_undo() -> None:
    grades = [
        make_grade(id="g-ai"),
        make_grade(id="g-human", source=GradingSource.HUMAN, created_at=at(5)),
    ]
    recognitions = [
        make_recognition(id="rec-ai"),
        make_recognition(
            id="rec-human", source=GradingSource.HUMAN, text="人による修正", created_at=at(5)
        ),
    ]
    modified = make_review(
        id="r1",
        action=ReviewAction.MODIFIED,
        ai_grade_result_id="g-ai",
        human_grade_result_id="g-human",
    )
    reviews = [
        modified,
        make_review(
            id="r2",
            version=2,
            action=ReviewAction.UNDONE,
            ai_grade_result_id=None,
            undone_review_id="r1",
            created_at=at(6),
        ),
    ]
    result = resolve_effective_recognition(reviews, grades, recognitions)
    assert result is not None
    assert result.id == "rec-ai"


def test_resolve_effective_recognition_keeps_a_standalone_manual_correction() -> None:
    """A human `RecognitionResult` created via `POST .../recognitions`
    (Issue #19) is never tied to any `Review` at all -- it must not be
    discarded just because there is no review history whatsoever for this
    question (Issue #22 P2 review, round 3): the previous "no modified
    review's own recognition matches -> fall straight to AI" rule treated
    every unmatched human row as if it did not exist."""
    recognitions = [
        make_recognition(id="rec-ai"),
        make_recognition(
            id="rec-human-manual",
            source=GradingSource.HUMAN,
            text="手動で訂正した文字",
            created_at=at(5),
        ),
    ]
    result = resolve_effective_recognition([], [], recognitions)
    assert result is not None
    assert result.id == "rec-human-manual"


def test_resolve_effective_recognition_keeps_a_standalone_correction_alongside_an_undone_edit() -> (
    None
):
    """An independent manual correction (unrelated to the review workflow)
    must survive even when *some* edit for this same question was undone --
    only the undone edit's *own* recognition (matched by its human grade's
    `created_at`) is excluded, not every human row that fails to match the
    currently effective review (Issue #22 P2 review, round 3)."""
    grades = [
        make_grade(id="g-ai"),
        make_grade(id="g-human-edit", source=GradingSource.HUMAN, created_at=at(5)),
    ]
    recognitions = [
        make_recognition(id="rec-ai"),
        # Belongs to the edit below, undone -- must be excluded.
        make_recognition(
            id="rec-human-edit",
            source=GradingSource.HUMAN,
            text="undoされた訂正",
            created_at=at(5),
        ),
        # A later, independent manual correction -- must survive.
        make_recognition(
            id="rec-human-manual",
            source=GradingSource.HUMAN,
            text="手動で訂正した文字",
            created_at=at(10),
        ),
    ]
    modified = make_review(
        id="r1",
        action=ReviewAction.MODIFIED,
        ai_grade_result_id="g-ai",
        human_grade_result_id="g-human-edit",
    )
    reviews = [
        modified,
        make_review(
            id="r2",
            version=2,
            action=ReviewAction.UNDONE,
            ai_grade_result_id=None,
            undone_review_id="r1",
            created_at=at(6),
        ),
    ]
    result = resolve_effective_recognition(reviews, grades, recognitions)
    assert result is not None
    assert result.id == "rec-human-manual"
