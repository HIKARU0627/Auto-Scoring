"""Unit tests for `auto_scoring.domain.review_workflow` (Issue #22, parent #3).

Pure-function tests: no database, no HTTP -- see `tests/test_review_api.py`
for the integration tests that exercise the same rules through the API.
"""

from __future__ import annotations

import pytest

from auto_scoring.domain.models import ReviewAction
from auto_scoring.domain.review_workflow import (
    ReviewVersionConflict,
    all_questions_confirmed,
    effective_latest_review,
    is_confirmed,
    next_review_version,
)
from tests.support import at, make_review


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
