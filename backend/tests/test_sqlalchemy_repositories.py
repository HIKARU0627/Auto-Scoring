"""Repository round-trips and the invariants they must uphold against real SQLite."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy.exc import IntegrityError

from auto_scoring.adapters import sqlalchemy_repositories
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.models import (
    GradingSource,
    InvalidStateTransition,
    JobSaveConflict,
    JobState,
    Score,
    SubmissionState,
    ensure_job_transition,
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


def test_has_downstream_processing_is_false_for_a_fresh_submission(
    seeded: UowFactory,
) -> None:
    with seeded() as uow:
        uow.submissions.add(make_submission())
        uow.commit()

    with seeded() as uow:
        assert uow.submissions.has_downstream_processing("sub-1") is False


def _seed_review(uow: SqlAlchemyUnitOfWork) -> None:
    # An approved review must reference an AI grade result, so seed one first.
    uow.grades.add(make_grade())
    uow.reviews.add(make_review())


@pytest.mark.parametrize(
    "seed_row",
    [
        lambda uow: uow.recognitions.add(make_recognition()),
        lambda uow: uow.grades.add(make_grade()),
        _seed_review,
        lambda uow: uow.jobs.add(make_job()),
    ],
    ids=["recognition", "grade", "review", "job"],
)
def test_has_downstream_processing_is_true_once_any_downstream_row_exists(
    seeded: UowFactory, seed_row: Callable[[SqlAlchemyUnitOfWork], None]
) -> None:
    with seeded() as uow:
        uow.submissions.add(make_submission())
        seed_row(uow)
        uow.commit()

    with seeded() as uow:
        assert uow.submissions.has_downstream_processing("sub-1") is True


def test_job_save_rejects_illegal_transition(seeded: UowFactory) -> None:
    with seeded() as uow:
        uow.submissions.add(make_submission())
        uow.jobs.add(make_job())
        uow.commit()

    with seeded() as uow, pytest.raises(InvalidStateTransition):
        uow.jobs.save(make_job(state=JobState.SUCCEEDED), expected_state=JobState.QUEUED)


def test_job_save_raises_conflict_when_the_row_changes_between_read_and_write(
    seeded: UowFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates the race directly: another transaction commits a state
    change to this job in the narrow window between `save()`'s own read (plus
    its in-Python transition check) and its atomic write. A plain ORM update
    (PK-only ``WHERE``) would silently overwrite that already-committed
    change; the compare-and-set must instead detect it and raise (Issue #26
    review: e.g. `/confirm` cancelling a job the instant before a worker
    reports it succeeded).
    """
    with seeded() as uow:
        uow.submissions.add(make_submission())
        uow.jobs.add(make_job(state=JobState.RUNNING))
        uow.commit()

    injected = {"done": False}

    def _cancel_concurrently_then_check(current: JobState, target: JobState) -> JobState:
        result = ensure_job_transition(current, target)
        if not injected["done"]:
            injected["done"] = True
            with seeded() as concurrent_uow:
                stale = concurrent_uow.jobs.get("job-1")
                assert stale is not None
                concurrent_uow.jobs.save(
                    stale.transitioned_to(JobState.CANCELLED, updated_at=at(5)),
                    expected_state=stale.state,
                )
                concurrent_uow.commit()
        return result

    monkeypatch.setattr(
        sqlalchemy_repositories, "ensure_job_transition", _cancel_concurrently_then_check
    )

    with seeded() as uow:
        job = uow.jobs.get("job-1")
        assert job is not None
        completed = job.transitioned_to(JobState.SUCCEEDED, updated_at=at(10))
        with pytest.raises(JobSaveConflict):
            uow.jobs.save(completed, expected_state=job.state)

    with seeded() as uow:
        final = uow.jobs.get("job-1")
    assert final is not None
    assert final.state is JobState.CANCELLED


def test_job_save_rejects_the_second_of_two_workers_racing_to_claim_the_same_job(
    seeded: UowFactory,
) -> None:
    """Two workers both read the same QUEUED job and both decide to move it
    to RUNNING. By the time the second worker's `save()` executes, the row
    already holds RUNNING -- coincidentally the very state the second worker
    is also trying to write. A `save()` that re-reads "current state" from
    the row itself (rather than using what the caller actually observed)
    would see its own target state already matching that re-read value, skip
    the transition check, and match its own ``WHERE state = 'running'``
    against the first worker's write -- silently letting both workers claim
    the same job (Issue #26 review). Passing each worker's own
    `expected_state` (QUEUED, what it actually read) keeps the second
    worker's ``WHERE state = 'queued'`` from matching the now-RUNNING row.
    """
    with seeded() as uow:
        uow.submissions.add(make_submission())
        uow.jobs.add(make_job(state=JobState.QUEUED))
        uow.commit()

    with seeded() as uow_a:
        job_a = uow_a.jobs.get("job-1")
    with seeded() as uow_b:
        job_b = uow_b.jobs.get("job-1")
    assert job_a is not None and job_b is not None

    with seeded() as uow_a:
        uow_a.jobs.save(
            job_a.transitioned_to(JobState.RUNNING, updated_at=at(5)),
            expected_state=job_a.state,
        )
        uow_a.commit()

    with seeded() as uow_b, pytest.raises(JobSaveConflict):
        uow_b.jobs.save(
            job_b.transitioned_to(JobState.RUNNING, updated_at=at(6)),
            expected_state=job_b.state,
        )

    with seeded() as uow:
        final = uow.jobs.get("job-1")
    assert final is not None
    assert final.attempts == 1  # only the winner's transitioned_to() attempt was recorded


def test_list_incomplete_for_stale_versions_filters_correctly(seeded: UowFactory) -> None:
    """QUEUED/RUNNING/BLOCKED/FAILED jobs tagged with a *different* graph
    version count as stale (Issue #26); untagged and truly-terminal
    (SUCCEEDED/CANCELLED) jobs do not. FAILED counts as incomplete because
    FAILED -> QUEUED is a valid retry transition -- a stale FAILED job left
    out here could still be retried later against the superseded graph
    version (Issue #26 review).
    """
    with seeded() as uow:
        uow.submissions.add(make_submission())
        uow.jobs.add(
            make_job(id="job-stale-queued", state=JobState.QUEUED, dependency_graph_version=1)
        )
        uow.jobs.add(
            make_job(id="job-stale-blocked", state=JobState.BLOCKED, dependency_graph_version=1)
        )
        uow.jobs.add(
            make_job(id="job-stale-failed", state=JobState.FAILED, dependency_graph_version=1)
        )
        uow.jobs.add(make_job(id="job-current", state=JobState.QUEUED, dependency_graph_version=2))
        uow.jobs.add(
            make_job(id="job-no-version", state=JobState.QUEUED, dependency_graph_version=None)
        )
        uow.jobs.add(make_job(id="job-done", state=JobState.SUCCEEDED, dependency_graph_version=1))
        uow.jobs.add(
            make_job(id="job-cancelled", state=JobState.CANCELLED, dependency_graph_version=1)
        )
        uow.commit()

    with seeded() as uow:
        stale = uow.jobs.list_incomplete_for_stale_versions("test-1", current_version=2)
    assert {job.id for job in stale} == {
        "job-stale-queued",
        "job-stale-blocked",
        "job-stale-failed",
    }


def test_list_incomplete_for_stale_versions_is_scoped_to_the_test(make_uow: UowFactory) -> None:
    with make_uow() as uow:
        uow.tests.add(make_test(id="test-1"))
        uow.tests.add(make_test(id="test-2", name="別テスト"))
        uow.questions.add(make_question(id="q-1", test_id="test-1"))
        uow.questions.add(make_question(id="q-2", test_id="test-2"))
        uow.submissions.add(make_submission(id="sub-1", test_id="test-1"))
        uow.submissions.add(make_submission(id="sub-2", test_id="test-2"))
        uow.jobs.add(
            make_job(
                id="job-test-1",
                submission_id="sub-1",
                state=JobState.QUEUED,
                dependency_graph_version=1,
            )
        )
        uow.jobs.add(
            make_job(
                id="job-test-2",
                submission_id="sub-2",
                state=JobState.QUEUED,
                dependency_graph_version=1,
            )
        )
        uow.commit()

    with make_uow() as uow:
        stale = uow.jobs.list_incomplete_for_stale_versions("test-1", current_version=2)
    assert {job.id for job in stale} == {"job-test-1"}


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
