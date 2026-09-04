"""Repository round-trips and the invariants they must uphold against real SQLite."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.exc import IntegrityError

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.models import (
    GradingSource,
    InvalidStateTransition,
    JobState,
    Score,
    SubmissionState,
)
from tests.support import (
    at,
    make_grade,
    make_job,
    make_question,
    make_recognition,
    make_review,
    make_rubric,
    make_submission,
    make_test,
)

UowFactory = Callable[[], SqlAlchemyUnitOfWork]


@pytest.fixture
def seeded(make_uow: UowFactory) -> UowFactory:
    """A test + question already committed, so child rows have parents."""
    with make_uow() as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question())
        uow.commit()
    return make_uow


def test_test_and_question_round_trip(make_uow: UowFactory) -> None:
    with make_uow() as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(points=7, number="問3"))
        uow.commit()

    with make_uow() as uow:
        assert uow.tests.get("test-1") == make_test()
        questions = uow.questions.list_for_test("test-1")
    assert [q.number for q in questions] == ["問3"]
    assert questions[0].points == 7


def test_rubric_round_trips_with_ordered_criteria(seeded: UowFactory) -> None:
    with seeded() as uow:
        uow.rubrics.add(make_rubric())
        uow.commit()

    with seeded() as uow:
        rubric = uow.rubrics.get_for_question("q-1")
    assert rubric is not None
    assert [c.id for c in rubric.criteria] == ["c-1", "c-2"]


def test_ai_and_human_grades_coexist_as_separate_rows(seeded: UowFactory) -> None:
    with seeded() as uow:
        uow.submissions.add(make_submission())
        uow.grades.add(
            make_grade(id="g-ai", source=GradingSource.AI, score=Score(awarded=4, maximum=5))
        )
        uow.grades.add(
            make_grade(
                id="g-human",
                source=GradingSource.HUMAN,
                score=Score(awarded=3, maximum=5),
                created_at=at(10),
            )
        )
        uow.commit()

    with seeded() as uow:
        history = uow.grades.history("sub-1", "q-1")
        ai_latest = uow.grades.latest("sub-1", "q-1", GradingSource.AI)
        human_latest = uow.grades.latest("sub-1", "q-1", GradingSource.HUMAN)

    assert [g.id for g in history] == ["g-ai", "g-human"]
    assert ai_latest is not None and ai_latest.score.awarded == 4
    assert human_latest is not None and human_latest.score.awarded == 3


def test_recognition_history_is_append_only(seeded: UowFactory) -> None:
    with seeded() as uow:
        uow.submissions.add(make_submission())
        uow.recognitions.add(make_recognition(id="r-ai", source=GradingSource.AI))
        uow.recognitions.add(
            make_recognition(
                id="r-human",
                source=GradingSource.HUMAN,
                text="光合成により酸素発生",
                confidence=1.0,
                created_at=at(5),
            )
        )
        uow.commit()

    with seeded() as uow:
        history = uow.recognitions.history("sub-1", "q-1")
    assert [r.source for r in history] == [GradingSource.AI, GradingSource.HUMAN]


def test_review_history_preserves_every_decision(seeded: UowFactory) -> None:
    with seeded() as uow:
        uow.submissions.add(make_submission())
        uow.grades.add(make_grade(id="g-ai"))
        uow.reviews.add(make_review(id="rev-1", ai_grade_result_id="g-ai"))
        uow.reviews.add(make_review(id="rev-2", ai_grade_result_id="g-ai", created_at=at(20)))
        uow.commit()

    with seeded() as uow:
        assert [r.id for r in uow.reviews.history("sub-1", "q-1")] == ["rev-1", "rev-2"]


def test_source_pdf_grades_reviews_are_retrievable_independently(
    seeded: UowFactory,
) -> None:
    with seeded() as uow:
        uow.submissions.add(make_submission(source_pdf_path="submissions/sub-1/source.pdf"))
        uow.grades.add(make_grade(id="g-ai", source=GradingSource.AI))
        uow.grades.add(make_grade(id="g-human", source=GradingSource.HUMAN, created_at=at(9)))
        uow.reviews.add(make_review(id="rev-1", ai_grade_result_id="g-ai"))
        uow.commit()

    with seeded() as uow:
        submission = uow.submissions.get("sub-1")
        ai = uow.grades.latest("sub-1", "q-1", GradingSource.AI)
        human = uow.grades.latest("sub-1", "q-1", GradingSource.HUMAN)
        reviews = uow.reviews.history("sub-1", "q-1")

    assert submission is not None and submission.source_pdf_path.endswith("source.pdf")
    assert ai is not None and human is not None and ai.id != human.id
    assert [r.id for r in reviews] == ["rev-1"]


def test_set_state_rejects_illegal_transition(seeded: UowFactory) -> None:
    with seeded() as uow:
        uow.submissions.add(make_submission())
        uow.commit()

    with seeded() as uow, pytest.raises(InvalidStateTransition):
        uow.submissions.set_state("sub-1", SubmissionState.EXPORTED)


def test_set_state_allows_a_legal_transition(seeded: UowFactory) -> None:
    with seeded() as uow:
        uow.submissions.add(make_submission())
        uow.commit()

    with seeded() as uow:
        uow.submissions.set_state("sub-1", SubmissionState.AI_PROCESSING)
        uow.commit()

    with seeded() as uow:
        submission = uow.submissions.get("sub-1")
    assert submission is not None
    assert submission.state is SubmissionState.AI_PROCESSING


def test_claim_for_retry_succeeds_from_error_and_updates_state(seeded: UowFactory) -> None:
    with seeded() as uow:
        uow.submissions.add(make_submission(state=SubmissionState.ERROR))
        uow.commit()

    with seeded() as uow:
        claimed = uow.submissions.claim_for_retry("sub-1")
        assert claimed is True
        uow.commit()

    with seeded() as uow:
        submission = uow.submissions.get("sub-1")
    assert submission is not None
    assert submission.state is SubmissionState.UNPROCESSED


def test_claim_for_retry_fails_when_not_in_error_state(seeded: UowFactory) -> None:
    with seeded() as uow:
        uow.submissions.add(make_submission(state=SubmissionState.UNPROCESSED))
        uow.commit()

    with seeded() as uow:
        claimed = uow.submissions.claim_for_retry("sub-1")
        assert claimed is False
        uow.commit()

    with seeded() as uow:
        submission = uow.submissions.get("sub-1")
    assert submission is not None
    assert submission.state is SubmissionState.UNPROCESSED  # unchanged


def test_claim_for_retry_only_the_first_of_two_concurrent_claims_wins(
    seeded: UowFactory,
) -> None:
    """Simulates two "concurrent" retries racing for the same errored
    submission: only the first conditional UPDATE (WHERE state = 'error')
    can match, so a second attempt against the same still-open transaction's
    view -- or, as here, sequentially after the first already moved the row
    out of 'error' -- must lose.
    """
    with seeded() as uow:
        uow.submissions.add(make_submission(state=SubmissionState.ERROR))
        uow.commit()

    with seeded() as first_uow:
        assert first_uow.submissions.claim_for_retry("sub-1") is True
        first_uow.commit()

    with seeded() as second_uow:
        assert second_uow.submissions.claim_for_retry("sub-1") is False
        second_uow.commit()

    with seeded() as uow:
        submission = uow.submissions.get("sub-1")
    assert submission is not None
    assert submission.state is SubmissionState.UNPROCESSED


def test_job_save_rejects_illegal_transition(seeded: UowFactory) -> None:
    with seeded() as uow:
        uow.submissions.add(make_submission())
        uow.jobs.add(make_job())
        uow.commit()

    with seeded() as uow, pytest.raises(InvalidStateTransition):
        uow.jobs.save(make_job(state=JobState.SUCCEEDED))


def test_orphan_row_is_rejected_by_foreign_key(make_uow: UowFactory) -> None:
    with pytest.raises(IntegrityError), make_uow() as uow:
        uow.questions.add(make_question(test_id="does-not-exist"))
        uow.commit()


def test_out_of_range_score_is_rejected_by_check_constraint(
    seeded: UowFactory,
) -> None:
    """The domain blocks this too; here we prove the DB is a second line of defence."""
    from auto_scoring.db.orm import GradeResultRow

    with pytest.raises(IntegrityError), seeded() as uow:
        uow.submissions.add(make_submission())
        uow.session.add(
            GradeResultRow(
                id="bad",
                submission_id="sub-1",
                question_id="q-1",
                source=GradingSource.AI,
                awarded=9,
                maximum=5,
                confidence=0.5,
                criteria=[],
                created_at=at(),
            )
        )
        uow.commit()


def test_unique_constraint_blocks_duplicate_question_number(
    make_uow: UowFactory,
) -> None:
    with pytest.raises(IntegrityError), make_uow() as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(id="q-a", number="問1"))
        uow.questions.add(make_question(id="q-b", number="問1"))
        uow.commit()
