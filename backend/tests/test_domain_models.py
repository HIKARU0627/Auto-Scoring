"""Domain invariants: score ranges, coordinates, state machines, append-only shape."""

from __future__ import annotations

import pytest

from auto_scoring.domain.models import (
    MAX_ORIGINAL_FILENAME_LENGTH,
    MAX_STUDENT_LABEL_LENGTH,
    Annotation,
    AnnotationKind,
    DomainError,
    GradeResult,
    GradingSource,
    InvalidCoordinate,
    InvalidStateTransition,
    JobState,
    NormalizedRect,
    ReviewAction,
    Score,
    ScoreOutOfRange,
    SubmissionState,
    ensure_job_transition,
    ensure_submission_transition,
    reissue_job_for_graph_version,
)
from tests.support import (
    at,
    make_annotation_comment,
    make_grade,
    make_job,
    make_review,
    make_submission,
)


@pytest.mark.parametrize("awarded", [-1, 6])
def test_score_rejects_out_of_range(awarded: int) -> None:
    with pytest.raises(ScoreOutOfRange):
        Score(awarded=awarded, maximum=5)


def test_score_rejects_negative_maximum() -> None:
    with pytest.raises(ScoreOutOfRange):
        Score(awarded=0, maximum=-1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"x": -0.1, "y": 0.0, "width": 0.2, "height": 0.2},
        {"x": 0.0, "y": 0.0, "width": 1.2, "height": 0.2},
        {"x": 0.9, "y": 0.0, "width": 0.2, "height": 0.2},
    ],
)
def test_normalized_rect_rejects_off_page(kwargs: dict[str, float]) -> None:
    with pytest.raises(InvalidCoordinate):
        NormalizedRect(**kwargs)


def test_grade_out_of_range_is_rejected_by_domain() -> None:
    with pytest.raises(ScoreOutOfRange):
        make_grade(score=Score(awarded=99, maximum=5))


def test_submission_state_machine_allows_forward_moves() -> None:
    assert (
        ensure_submission_transition(SubmissionState.UNPROCESSED, SubmissionState.AI_PROCESSING)
        is SubmissionState.AI_PROCESSING
    )


def test_submission_state_machine_rejects_illegal_move() -> None:
    with pytest.raises(InvalidStateTransition):
        ensure_submission_transition(SubmissionState.UNPROCESSED, SubmissionState.EXPORTED)


def test_submission_with_state_rejects_illegal_move() -> None:
    submission = make_submission()
    with pytest.raises(InvalidStateTransition):
        submission.with_state(SubmissionState.REVIEWED)


def test_submission_student_label_length_is_capped() -> None:
    with pytest.raises(DomainError):
        make_submission(student_label="a" * (MAX_STUDENT_LABEL_LENGTH + 1))


def test_submission_student_label_at_the_cap_is_accepted() -> None:
    make_submission(student_label="a" * MAX_STUDENT_LABEL_LENGTH)


def test_submission_original_filename_length_is_capped() -> None:
    with pytest.raises(DomainError):
        make_submission(original_filename="a" * (MAX_ORIGINAL_FILENAME_LENGTH + 1))


def test_submission_original_filename_at_the_cap_is_accepted() -> None:
    make_submission(original_filename="a" * MAX_ORIGINAL_FILENAME_LENGTH)


def test_job_transition_counts_a_run_attempt() -> None:
    job = make_job()
    running = job.transitioned_to(JobState.RUNNING, updated_at=at(1))
    assert running.attempts == 1
    assert running.state is JobState.RUNNING


def test_job_terminal_state_is_final() -> None:
    with pytest.raises(InvalidStateTransition):
        ensure_job_transition(JobState.SUCCEEDED, JobState.QUEUED)


def test_job_rejects_non_positive_dependency_graph_version() -> None:
    with pytest.raises(DomainError):
        make_job(dependency_graph_version=0)


def test_reissue_job_for_graph_version_cancels_and_recreates() -> None:
    """Issue #26: an incomplete job tied to a superseded confirmed graph
    version is cancelled and replaced with a fresh one queued against the
    new version.
    """
    stale = make_job(
        state=JobState.BLOCKED,
        blocked_on_question_id="q-1",
        dependency_graph_version=1,
        attempts=2,
        last_error="waiting",
    )

    cancelled, replacement = reissue_job_for_graph_version(
        stale, new_version=2, new_id="job-2", at=at(10)
    )

    assert cancelled.id == stale.id
    assert cancelled.state is JobState.CANCELLED
    assert cancelled.last_error is not None and "version 2" in cancelled.last_error
    assert cancelled.updated_at == at(10)

    assert replacement.id == "job-2"
    assert replacement.state is JobState.QUEUED
    assert replacement.attempts == 0
    assert replacement.last_error is None
    assert replacement.blocked_on_question_id is None
    assert replacement.dependency_graph_version == 2
    assert replacement.kind == stale.kind
    assert replacement.submission_id == stale.submission_id
    assert replacement.question_id == stale.question_id
    assert replacement.created_at == at(10)


@pytest.mark.parametrize("running_state", [JobState.QUEUED, JobState.RUNNING, JobState.BLOCKED])
def test_reissue_job_for_graph_version_accepts_every_incomplete_state(
    running_state: JobState,
) -> None:
    stale = make_job(state=running_state, dependency_graph_version=1)
    cancelled, _replacement = reissue_job_for_graph_version(
        stale, new_version=2, new_id="job-2", at=at(1)
    )
    assert cancelled.state is JobState.CANCELLED


def test_grade_result_has_no_mutating_api() -> None:
    """Append-only: results are frozen and expose nothing that rewrites them."""
    grade = make_grade()
    with pytest.raises(AttributeError):
        grade.confidence = 0.1  # type: ignore[misc]
    assert not [name for name in dir(GradeResult) if name in {"update", "set_score", "override"}]


def test_comment_annotation_requires_text() -> None:
    with pytest.raises(DomainError):
        Annotation(
            id="a-1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            kind=AnnotationKind.COMMENT,
            created_at=at(),
        )


def test_annotation_comment_length_is_capped() -> None:
    with pytest.raises(DomainError):
        make_annotation_comment(comment="あ" * 121)


def test_approved_review_must_reference_ai_result() -> None:
    with pytest.raises(DomainError):
        make_review(action=ReviewAction.APPROVED, ai_grade_result_id=None)


def test_modified_review_must_reference_both_results() -> None:
    with pytest.raises(DomainError):
        make_review(
            action=ReviewAction.MODIFIED,
            ai_grade_result_id="grade-1",
            human_grade_result_id=None,
        )
