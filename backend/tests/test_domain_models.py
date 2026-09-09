"""Domain invariants: score ranges, coordinates, state machines, append-only shape."""

from __future__ import annotations

import pytest

from auto_scoring.domain.models import (
    MAX_COMMENT_CHARS,
    MAX_ORIGINAL_FILENAME_LENGTH,
    MAX_STUDENT_LABEL_LENGTH,
    MAX_TEST_NAME_LENGTH,
    MAX_TEST_SUBJECT_LENGTH,
    Annotation,
    AnnotationKind,
    AnswerImageFinding,
    DomainError,
    GradeResult,
    GradeResultContextEntry,
    GradingSource,
    InvalidCoordinate,
    InvalidStateTransition,
    JobState,
    NormalizedRect,
    ReviewAction,
    Score,
    ScoreOutOfRange,
    SubmissionState,
    TestStatus,
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
    make_test,
)


def test_new_test_starts_as_draft() -> None:
    assert make_test().status is TestStatus.DRAFT


def test_mark_ready_transitions_a_draft_test() -> None:
    ready = make_test().mark_ready()
    assert ready.status is TestStatus.READY


def test_mark_ready_is_one_way() -> None:
    """Issue #16: registration completion is a one-way move -- a test that
    is already `ready` cannot be "re-completed" (that would silently no-op
    what should be a caller bug, e.g. calling complete-registration twice).
    """
    ready = make_test().mark_ready()
    with pytest.raises(InvalidStateTransition):
        ready.mark_ready()


def test_test_name_length_is_capped() -> None:
    """An authenticated caller of `POST /tests` can send `name` as a
    multipart form field up to the whole request's own size limit; it is
    stored verbatim and returned on every test-registration list response
    (Issue #16 review round 8).
    """
    with pytest.raises(DomainError):
        make_test(name="a" * (MAX_TEST_NAME_LENGTH + 1))


def test_test_name_at_the_cap_is_accepted() -> None:
    assert make_test(name="a" * MAX_TEST_NAME_LENGTH).name == "a" * MAX_TEST_NAME_LENGTH


def test_test_subject_length_is_capped() -> None:
    with pytest.raises(DomainError):
        make_test(subject="a" * (MAX_TEST_SUBJECT_LENGTH + 1))


def test_test_subject_at_the_cap_is_accepted() -> None:
    subject = "a" * MAX_TEST_SUBJECT_LENGTH
    assert make_test(subject=subject).subject == subject


def test_test_subject_may_be_none() -> None:
    assert make_test(subject=None).subject is None


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


def test_a_cleanly_intaken_submission_can_reach_reviewed_directly() -> None:
    """簡易設計書 §25.1 / Issue #112: 要確認は関門ではなく、取込が立てる旗である。

    Intake leaves an ordinary submission at `AI_PROCESSED` and only routes on to
    `NEEDS_REVIEW` when it could not pin the answer areas. So a person
    confirming every question of an ordinary submission has to be able to
    complete it without a detour through the state that means "intake failed".
    """
    assert (
        ensure_submission_transition(SubmissionState.AI_PROCESSED, SubmissionState.REVIEWED)
        is SubmissionState.REVIEWED
    )


def test_a_completed_submission_can_go_back_to_ai_processed() -> None:
    """Issue #112: Undo で完了が外れたとき、取込が置いた場所へ戻れること。

    The counterpart of the transition above: without it the only way out of
    `REVIEWED` would be `NEEDS_REVIEW`, which would flag a submission whose
    intake was fine -- and nothing would ever unflag it.
    """
    assert (
        ensure_submission_transition(SubmissionState.REVIEWED, SubmissionState.AI_PROCESSED)
        is SubmissionState.AI_PROCESSED
    )


def test_widening_the_reviewed_transitions_did_not_open_the_processing_ones() -> None:
    """Issue #112 widened two edges; these stayed shut.

    A submission still being processed has nothing a person could have
    confirmed, so it must not be able to claim completion.
    """
    for source in (SubmissionState.UNPROCESSED, SubmissionState.AI_PROCESSING):
        with pytest.raises(InvalidStateTransition):
            ensure_submission_transition(source, SubmissionState.REVIEWED)


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


def test_grade_result_comment_length_is_capped() -> None:
    with pytest.raises(DomainError):
        make_grade(comment="a" * (MAX_COMMENT_CHARS + 1))


def test_grade_result_comment_at_the_cap_is_accepted() -> None:
    make_grade(comment="a" * MAX_COMMENT_CHARS)


def test_grade_result_ai_metadata_must_be_set_together() -> None:
    with pytest.raises(DomainError):
        make_grade(provider="gemini", model=None, prompt_version="v1")


def test_grade_result_ai_metadata_rejects_blank_values() -> None:
    with pytest.raises(DomainError):
        make_grade(provider="   ", model="m", prompt_version="v1")


def test_grade_result_accepts_the_full_ai_metadata_triple() -> None:
    grade = make_grade(provider="gemini", model="gemini-2.5-flash", prompt_version="v1")
    assert grade.provider == "gemini"
    assert grade.model == "gemini-2.5-flash"
    assert grade.prompt_version == "v1"


def test_grade_result_refuses_to_exist_for_an_image_that_is_not_the_answer() -> None:
    """Issue #136: a score computed from a crop the grader itself said is not
    this question's answer must not be storable at all.

    That row is the whole defect -- on screen it is "0 / 20 点・採点信頼度
    100%", indistinguishable from a correct 0. `jobs.grading_processor`
    routes the case to a human instead of building one; this invariant (and
    the matching DB trigger, migration 0017) is what stops a later code path
    from building one anyway.
    """
    with pytest.raises(DomainError):
        make_grade(answer_image_finding=AnswerImageFinding.NOT_THE_ANSWER)


def test_grade_result_records_the_other_answer_image_findings() -> None:
    """``blank`` is storable and changes nothing about the grade: a question
    a student left empty is an ordinary answer sheet. It is kept so the
    frequency of that case can be counted from stored data later."""
    assert (
        make_grade(answer_image_finding=AnswerImageFinding.BLANK).answer_image_finding
        is AnswerImageFinding.BLANK
    )
    assert (
        make_grade(answer_image_finding=AnswerImageFinding.ANSWER).answer_image_finding
        is AnswerImageFinding.ANSWER
    )
    assert make_grade().answer_image_finding is None


def test_grade_result_rejects_non_positive_dependency_graph_version() -> None:
    with pytest.raises(DomainError):
        make_grade(dependency_graph_version=0)


def test_grade_result_context_entry_requires_at_least_one_result_reference() -> None:
    with pytest.raises(DomainError):
        GradeResultContextEntry(question_id="q-0")


def test_grade_result_rejects_duplicate_context_question_ids() -> None:
    with pytest.raises(DomainError):
        make_grade(
            context=(
                GradeResultContextEntry(question_id="q-0", recognition_result_id="rec-0"),
                GradeResultContextEntry(question_id="q-0", grade_result_id="grade-0"),
            )
        )


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


def test_modified_review_may_omit_the_ai_grade_it_corrected() -> None:
    """Issue #118: a person grading a question AI could not grade at all has
    no AI grade to have corrected, and inventing one would be exactly the
    fabricated result Issue #97 refuses to persist.

    ``APPROVED`` still requires one -- there is nothing to approve otherwise
    -- so this is not "the invariant went away", it is "``ai_grade_result_id``
    means *the AI attempt this correction was based on*, and sometimes there
    was none". A ``modified`` row with it unset is the record of that, and
    the one the review screen reads to say so.
    """
    review = make_review(
        action=ReviewAction.MODIFIED,
        ai_grade_result_id=None,
        human_grade_result_id="grade-human",
    )
    assert review.ai_grade_result_id is None
    assert review.human_grade_result_id == "grade-human"


def test_review_version_must_be_positive() -> None:
    with pytest.raises(DomainError):
        make_review(version=0)


def test_regrade_requested_review_must_reference_a_job() -> None:
    with pytest.raises(DomainError):
        make_review(
            action=ReviewAction.REGRADE_REQUESTED,
            ai_grade_result_id=None,
            regrade_job_id=None,
        )


def test_regrade_requested_review_may_omit_the_ai_grade() -> None:
    """Regrading is exactly how a reviewer recovers from "AI never produced
    a grade at all" -- unlike APPROVED/MODIFIED, it must not require one."""
    review = make_review(
        action=ReviewAction.REGRADE_REQUESTED,
        ai_grade_result_id=None,
        regrade_job_id="job-1",
    )
    assert review.regrade_job_id == "job-1"


def test_undone_review_must_reference_the_review_it_undoes() -> None:
    with pytest.raises(DomainError):
        make_review(
            action=ReviewAction.UNDONE,
            ai_grade_result_id=None,
            undone_review_id=None,
        )


def test_review_note_length_is_capped() -> None:
    with pytest.raises(DomainError):
        make_review(note="あ" * 121)
