"""Unit tests for `domain.pdf_export` (Issue #23)."""

from __future__ import annotations

from datetime import datetime, timedelta

from auto_scoring.domain.models import (
    Annotation,
    AnnotationKind,
    BoundingBox,
    Export,
    GradeResult,
    GradingSource,
    NormalizedRect,
    Question,
    QuestionReviewVersion,
    RecognitionResult,
    Review,
    ReviewAction,
    Score,
)
from auto_scoring.domain.pdf_export import (
    ReexportDecision,
    build_export_marks,
    decide_reexport,
    review_version_snapshot,
    unconfirmed_question_ids,
)

_NOW = datetime(2026, 1, 1)


def _question(**overrides: object) -> Question:
    values: dict[str, object] = {
        "id": "q-1",
        "test_id": "test-1",
        "number": "1",
        "page": 1,
        "points": 5,
    }
    values.update(overrides)
    return Question(**values)  # type: ignore[arg-type]


def _grade(**overrides: object) -> GradeResult:
    values: dict[str, object] = {
        "id": "grade-1",
        "submission_id": "sub-1",
        "question_id": "q-1",
        "source": GradingSource.AI,
        "score": Score(awarded=4, maximum=5),
        "confidence": 0.9,
        "created_at": _NOW,
    }
    values.update(overrides)
    return GradeResult(**values)  # type: ignore[arg-type]


def _review(**overrides: object) -> Review:
    values: dict[str, object] = {
        "id": "review-1",
        "submission_id": "sub-1",
        "question_id": "q-1",
        "action": ReviewAction.APPROVED,
        "version": 1,
        "ai_grade_result_id": "grade-1",
        "created_at": _NOW,
    }
    values.update(overrides)
    return Review(**values)  # type: ignore[arg-type]


class TestUnconfirmedQuestionIds:
    def test_a_question_with_no_review_history_is_unconfirmed(self) -> None:
        assert unconfirmed_question_ids(["q-1"], {}) == ["q-1"]

    def test_an_approved_question_is_confirmed(self) -> None:
        reviews = {"q-1": [_review(action=ReviewAction.APPROVED)]}
        assert unconfirmed_question_ids(["q-1"], reviews) == []

    def test_a_rejected_question_is_unconfirmed(self) -> None:
        reviews = {
            "q-1": [
                Review(
                    id="r1",
                    submission_id="sub-1",
                    question_id="q-1",
                    action=ReviewAction.REJECTED,
                    version=1,
                    created_at=_NOW,
                )
            ]
        }
        assert unconfirmed_question_ids(["q-1"], reviews) == ["q-1"]

    def test_an_undone_approval_reverts_to_unconfirmed(self) -> None:
        approved = _review(id="r1", version=1)
        undone = Review(
            id="r2",
            submission_id="sub-1",
            question_id="q-1",
            action=ReviewAction.UNDONE,
            version=2,
            undone_review_id="r1",
            created_at=_NOW,
        )
        reviews = {"q-1": [approved, undone]}
        assert unconfirmed_question_ids(["q-1"], reviews) == ["q-1"]

    def test_only_the_unconfirmed_ones_are_named(self) -> None:
        reviews = {"q-1": [_review(id="r1")]}
        assert unconfirmed_question_ids(["q-1", "q-2"], reviews) == ["q-2"]


class TestReviewVersionSnapshot:
    def test_version_is_the_history_length_sorted_by_question_id(self) -> None:
        reviews = {
            "q-2": [_review(id="r1", question_id="q-2")],
            "q-1": [
                _review(id="r2", question_id="q-1", version=1),
                _review(
                    id="r3",
                    question_id="q-1",
                    version=2,
                    action=ReviewAction.MODIFIED,
                    human_grade_result_id="grade-human",
                ),
            ],
        }

        snapshot = review_version_snapshot(["q-1", "q-2"], reviews)

        assert snapshot == (
            QuestionReviewVersion(question_id="q-1", version=2),
            QuestionReviewVersion(question_id="q-2", version=1),
        )


class TestDecideReexport:
    def test_accepts_a_new_export_when_none_exists_yet(self) -> None:
        snapshot = (QuestionReviewVersion(question_id="q-1", version=1),)
        assert decide_reexport(None, snapshot) is ReexportDecision.ACCEPT_NEW

    def test_reuses_the_existing_export_when_the_snapshot_is_unchanged(self) -> None:
        snapshot = (QuestionReviewVersion(question_id="q-1", version=1),)
        previous = Export(
            id="export-1",
            submission_id="sub-1",
            job_id="job-1",
            file_path="exports/a_corrected.pdf",
            file_sha256="0" * 64,
            created_at=_NOW,
            review_versions=snapshot,
        )
        assert decide_reexport(previous, snapshot) is ReexportDecision.REUSE_EXISTING

    def test_supersedes_the_existing_export_once_a_question_s_review_history_advances(
        self,
    ) -> None:
        previous_snapshot = (QuestionReviewVersion(question_id="q-1", version=1),)
        current_snapshot = (QuestionReviewVersion(question_id="q-1", version=2),)
        previous = Export(
            id="export-1",
            submission_id="sub-1",
            job_id="job-1",
            file_path="exports/a_corrected.pdf",
            file_sha256="0" * 64,
            created_at=_NOW,
            review_versions=previous_snapshot,
        )
        assert (
            decide_reexport(previous, current_snapshot) is ReexportDecision.ACCEPT_NEW_SUPERSEDING
        )


class TestBuildExportMarks:
    def test_score_kind_draws_the_confirmed_grade_s_score_not_the_annotation_s_own_comment(
        self,
    ) -> None:
        grade = _grade(score=Score(awarded=3, maximum=5))
        annotation = Annotation(
            id="a1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            kind=AnnotationKind.SCORE,
            comment="stale AI label: 4/5",
            created_at=_NOW,
        )

        marks = build_export_marks(
            question=_question(score_area=NormalizedRect(x=0.8, y=0.0, width=0.2, height=0.05)),
            grade=grade,
            annotations=[annotation],
            recognitions=[],
        )

        assert len(marks) == 1
        assert marks[0].text == "3/5"

    def test_comment_kind_draws_the_annotation_s_own_comment_text(self) -> None:
        grade = _grade()
        annotation = Annotation(
            id="a1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            kind=AnnotationKind.COMMENT,
            comment="理由の説明が不足しています。",
            created_at=_NOW,
        )

        marks = build_export_marks(
            question=_question(comment_area=NormalizedRect(x=0.0, y=0.9, width=1.0, height=0.1)),
            grade=grade,
            annotations=[annotation],
            recognitions=[],
        )

        assert len(marks) == 1
        assert marks[0].text == "理由の説明が不足しています。"

    def test_falls_back_to_comment_area_when_the_mark_has_no_other_resolvable_position(
        self,
    ) -> None:
        grade = _grade()
        comment_area = NormalizedRect(x=0.0, y=0.9, width=1.0, height=0.1)
        annotation = Annotation(
            id="a1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.HUMAN,
            kind=AnnotationKind.COMMENT,
            comment="コメント",
            created_at=_NOW,
        )

        marks = build_export_marks(
            question=_question(comment_area=comment_area),
            grade=grade,
            annotations=[annotation],
            recognitions=[],
        )

        assert marks[0].rect == comment_area

    def test_a_mark_with_no_resolvable_position_at_all_is_skipped_not_crashed_on(
        self,
    ) -> None:
        grade = _grade()
        annotation = Annotation(
            id="a1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.HUMAN,
            kind=AnnotationKind.COMMENT,
            comment="コメント",
            created_at=_NOW,
        )

        marks = build_export_marks(
            question=_question(comment_area=None),
            grade=grade,
            annotations=[annotation],
            recognitions=[],
        )

        assert marks == []

    def test_only_annotations_and_recognitions_from_the_grade_s_own_attempt_are_used(
        self,
    ) -> None:
        grade = _grade(created_at=_NOW + timedelta(seconds=10))
        stale_annotation = Annotation(
            id="a-stale",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            kind=AnnotationKind.UNDERLINE,
            anchor_text="行く",
            created_at=_NOW,
        )
        current_annotation = Annotation(
            id="a-current",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            kind=AnnotationKind.UNDERLINE,
            anchor_text="行く",
            created_at=_NOW + timedelta(seconds=10),
        )
        stale_recognition = RecognitionResult(
            id="rec-stale",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            text="",
            confidence=0.9,
            created_at=_NOW,
            boxes=(
                BoundingBox(text="行く", rect=NormalizedRect(x=0.0, y=0.0, width=0.1, height=0.1)),
            ),
        )
        current_recognition = RecognitionResult(
            id="rec-current",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            text="",
            confidence=0.9,
            created_at=_NOW + timedelta(seconds=10),
            boxes=(
                BoundingBox(text="行く", rect=NormalizedRect(x=0.5, y=0.5, width=0.1, height=0.1)),
            ),
        )

        marks = build_export_marks(
            question=_question(),
            grade=grade,
            annotations=[stale_annotation, current_annotation],
            recognitions=[stale_recognition, current_recognition],
        )

        assert len(marks) == 1
        assert marks[0].rect == NormalizedRect(x=0.5, y=0.5, width=0.1, height=0.1)
