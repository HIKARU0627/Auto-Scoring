"""Translation between domain dataclasses and SQLAlchemy rows.

Kept in one place so the repositories stay short and the JSON shapes for
normalized rects, OCR boxes and criterion results have a single definition.
"""

from __future__ import annotations

from typing import Any

from auto_scoring.db.orm import (
    AnnotationRow,
    AnswerImageRow,
    DependencyEdgeRow,
    DependencyGraphRow,
    GradeResultRow,
    JobRow,
    QuestionRow,
    RecognitionResultRow,
    ReviewRow,
    RubricCriterionRow,
    RubricRow,
    SubmissionRow,
    TestRow,
)
from auto_scoring.domain.dependency_graph import (
    DependencyEdge,
    DependencyGraph,
    DependencyGraphStatus,
    DependencyProvision,
    UnresolvedQuestion,
)
from auto_scoring.domain.models import (
    Annotation,
    AnnotationKind,
    AnswerImage,
    AnswerImageStatus,
    BoundingBox,
    CriterionOutcome,
    CriterionResult,
    ErrorCategory,
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
    Rubric,
    RubricCriterion,
    Score,
    ScoringMethod,
    Submission,
    SubmissionState,
    Test,
)


def rect_to_json(rect: NormalizedRect | None) -> dict[str, float] | None:
    if rect is None:
        return None
    return {"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height}


def rect_from_json(data: dict[str, Any] | None) -> NormalizedRect | None:
    if data is None:
        return None
    return NormalizedRect(x=data["x"], y=data["y"], width=data["width"], height=data["height"])


def _box_to_json(box: BoundingBox) -> dict[str, Any]:
    return {"text": box.text, "rect": rect_to_json(box.rect)}


def _box_from_json(data: dict[str, Any]) -> BoundingBox:
    rect = rect_from_json(data["rect"])
    assert rect is not None  # a box always carries a rect
    return BoundingBox(text=data["text"], rect=rect)


def _criterion_to_json(result: CriterionResult) -> dict[str, Any]:
    return {
        "criterion_id": result.criterion_id,
        "outcome": result.outcome.value,
        "confidence": result.confidence,
    }


def _criterion_from_json(data: dict[str, Any]) -> CriterionResult:
    return CriterionResult(
        criterion_id=data["criterion_id"],
        outcome=CriterionOutcome(data["outcome"]),
        confidence=data.get("confidence"),
    )


# --------------------------------------------------------------------------- #
# Test
# --------------------------------------------------------------------------- #
def test_to_row(test: Test) -> TestRow:
    return TestRow(
        id=test.id,
        name=test.name,
        subject=test.subject,
        default_scoring_method=test.default_scoring_method,
        created_at=test.created_at,
    )


def test_from_row(row: TestRow) -> Test:
    return Test(
        id=row.id,
        name=row.name,
        subject=row.subject,
        default_scoring_method=ScoringMethod(row.default_scoring_method),
        created_at=row.created_at,
    )


# --------------------------------------------------------------------------- #
# Question
# --------------------------------------------------------------------------- #
def question_to_row(question: Question) -> QuestionRow:
    return QuestionRow(
        id=question.id,
        test_id=question.test_id,
        number=question.number,
        page=question.page,
        points=question.points,
        scoring_method=question.scoring_method,
        model_answer=question.model_answer,
        answer_area=rect_to_json(question.answer_area),
        score_area=rect_to_json(question.score_area),
        comment_area=rect_to_json(question.comment_area),
    )


def question_from_row(row: QuestionRow) -> Question:
    return Question(
        id=row.id,
        test_id=row.test_id,
        number=row.number,
        page=row.page,
        points=row.points,
        scoring_method=ScoringMethod(row.scoring_method),
        model_answer=row.model_answer,
        answer_area=rect_from_json(row.answer_area),
        score_area=rect_from_json(row.score_area),
        comment_area=rect_from_json(row.comment_area),
    )


# --------------------------------------------------------------------------- #
# Rubric
# --------------------------------------------------------------------------- #
def rubric_rows(rubric: Rubric) -> tuple[RubricRow, list[RubricCriterionRow]]:
    parent = RubricRow(id=rubric.id, question_id=rubric.question_id)
    children = [
        RubricCriterionRow(
            id=criterion.id,
            rubric_id=rubric.id,
            description=criterion.description,
            max_points=criterion.max_points,
            position=criterion.position,
        )
        for criterion in rubric.criteria
    ]
    return parent, children


def rubric_from_rows(row: RubricRow, criteria: list[RubricCriterionRow]) -> Rubric:
    ordered = sorted(criteria, key=lambda c: c.position)
    return Rubric(
        id=row.id,
        question_id=row.question_id,
        criteria=tuple(
            RubricCriterion(
                id=c.id,
                description=c.description,
                max_points=c.max_points,
                position=c.position,
            )
            for c in ordered
        ),
    )


# --------------------------------------------------------------------------- #
# Submission
# --------------------------------------------------------------------------- #
def submission_to_row(submission: Submission) -> SubmissionRow:
    return SubmissionRow(
        id=submission.id,
        test_id=submission.test_id,
        source_pdf_path=submission.source_pdf_path,
        source_pdf_sha256=submission.source_pdf_sha256,
        page_count=submission.page_count,
        state=submission.state,
        student_label=submission.student_label,
        original_filename=submission.original_filename,
        review_reason=submission.review_reason,
        created_at=submission.created_at,
    )


def submission_from_row(row: SubmissionRow) -> Submission:
    return Submission(
        id=row.id,
        test_id=row.test_id,
        source_pdf_path=row.source_pdf_path,
        source_pdf_sha256=row.source_pdf_sha256,
        page_count=row.page_count,
        state=SubmissionState(row.state),
        student_label=row.student_label,
        original_filename=row.original_filename,
        review_reason=row.review_reason,
        created_at=row.created_at,
    )


# --------------------------------------------------------------------------- #
# AnswerImage
# --------------------------------------------------------------------------- #
def answer_image_to_row(image: AnswerImage) -> AnswerImageRow:
    return AnswerImageRow(
        id=image.id,
        submission_id=image.submission_id,
        question_id=image.question_id,
        page=image.page,
        image_path=image.image_path,
        status=image.status,
        reason=image.reason,
        created_at=image.created_at,
    )


def answer_image_from_row(row: AnswerImageRow) -> AnswerImage:
    return AnswerImage(
        id=row.id,
        submission_id=row.submission_id,
        question_id=row.question_id,
        page=row.page,
        image_path=row.image_path,
        status=AnswerImageStatus(row.status),
        reason=row.reason,
        created_at=row.created_at,
    )


# --------------------------------------------------------------------------- #
# RecognitionResult
# --------------------------------------------------------------------------- #
def recognition_to_row(result: RecognitionResult) -> RecognitionResultRow:
    return RecognitionResultRow(
        id=result.id,
        submission_id=result.submission_id,
        question_id=result.question_id,
        source=result.source,
        text=result.text,
        confidence=result.confidence,
        boxes=[_box_to_json(box) for box in result.boxes],
        created_at=result.created_at,
    )


def recognition_from_row(row: RecognitionResultRow) -> RecognitionResult:
    return RecognitionResult(
        id=row.id,
        submission_id=row.submission_id,
        question_id=row.question_id,
        source=GradingSource(row.source),
        text=row.text,
        confidence=row.confidence,
        boxes=tuple(_box_from_json(box) for box in row.boxes),
        created_at=row.created_at,
    )


# --------------------------------------------------------------------------- #
# GradeResult
# --------------------------------------------------------------------------- #
def grade_to_row(result: GradeResult) -> GradeResultRow:
    return GradeResultRow(
        id=result.id,
        submission_id=result.submission_id,
        question_id=result.question_id,
        source=result.source,
        awarded=result.score.awarded,
        maximum=result.score.maximum,
        confidence=result.confidence,
        criteria=[_criterion_to_json(c) for c in result.criteria],
        rationale=result.rationale,
        created_at=result.created_at,
    )


def grade_from_row(row: GradeResultRow) -> GradeResult:
    return GradeResult(
        id=row.id,
        submission_id=row.submission_id,
        question_id=row.question_id,
        source=GradingSource(row.source),
        score=Score(awarded=row.awarded, maximum=row.maximum),
        confidence=row.confidence,
        criteria=tuple(_criterion_from_json(c) for c in row.criteria),
        rationale=row.rationale,
        created_at=row.created_at,
    )


# --------------------------------------------------------------------------- #
# Annotation
# --------------------------------------------------------------------------- #
def annotation_to_row(annotation: Annotation) -> AnnotationRow:
    return AnnotationRow(
        id=annotation.id,
        submission_id=annotation.submission_id,
        question_id=annotation.question_id,
        source=annotation.source,
        kind=annotation.kind,
        rect=rect_to_json(annotation.rect),
        anchor_text=annotation.anchor_text,
        comment=annotation.comment,
        created_at=annotation.created_at,
    )


def annotation_from_row(row: AnnotationRow) -> Annotation:
    return Annotation(
        id=row.id,
        submission_id=row.submission_id,
        question_id=row.question_id,
        source=GradingSource(row.source),
        kind=AnnotationKind(row.kind),
        rect=rect_from_json(row.rect),
        anchor_text=row.anchor_text,
        comment=row.comment,
        created_at=row.created_at,
    )


# --------------------------------------------------------------------------- #
# Review
# --------------------------------------------------------------------------- #
def review_to_row(review: Review) -> ReviewRow:
    return ReviewRow(
        id=review.id,
        submission_id=review.submission_id,
        question_id=review.question_id,
        action=review.action,
        ai_grade_result_id=review.ai_grade_result_id,
        human_grade_result_id=review.human_grade_result_id,
        note=review.note,
        created_at=review.created_at,
    )


def review_from_row(row: ReviewRow) -> Review:
    return Review(
        id=row.id,
        submission_id=row.submission_id,
        question_id=row.question_id,
        action=ReviewAction(row.action),
        ai_grade_result_id=row.ai_grade_result_id,
        human_grade_result_id=row.human_grade_result_id,
        note=row.note,
        created_at=row.created_at,
    )


# --------------------------------------------------------------------------- #
# Job
# --------------------------------------------------------------------------- #
def job_to_row(job: Job) -> JobRow:
    return JobRow(
        id=job.id,
        kind=job.kind,
        submission_id=job.submission_id,
        question_id=job.question_id,
        state=job.state,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        last_error=job.last_error,
        error_code=job.error_code,
        blocked_on_question_id=job.blocked_on_question_id,
        usable=job.usable,
        dependency_graph_version=job.dependency_graph_version,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def job_from_row(row: JobRow) -> Job:
    return Job(
        id=row.id,
        kind=JobKind(row.kind),
        submission_id=row.submission_id,
        question_id=row.question_id,
        state=JobState(row.state),
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        last_error=row.last_error,
        error_code=ErrorCategory(row.error_code) if row.error_code is not None else None,
        blocked_on_question_id=row.blocked_on_question_id,
        usable=row.usable,
        dependency_graph_version=row.dependency_graph_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# --------------------------------------------------------------------------- #
# DependencyGraph
# --------------------------------------------------------------------------- #
def dependency_graph_rows(
    graph: DependencyGraph,
) -> tuple[DependencyGraphRow, list[DependencyEdgeRow]]:
    parent = DependencyGraphRow(
        id=graph.id,
        test_id=graph.test_id,
        version=graph.version,
        status=graph.status,
        question_ids=sorted(graph.question_ids),
        unresolved=[u.to_dict() for u in graph.unresolved],
        created_at=graph.created_at,
        confirmed_at=graph.confirmed_at,
    )
    children = [
        DependencyEdgeRow(
            graph_id=graph.id,
            from_question_id=edge.from_question_id,
            to_question_id=edge.to_question_id,
            provides=[p.value for p in edge.provides],
            rationale=edge.rationale,
            confidence=edge.confidence,
        )
        for edge in graph.edges
    ]
    return parent, children


def dependency_graph_from_rows(
    row: DependencyGraphRow, edge_rows: list[DependencyEdgeRow]
) -> DependencyGraph:
    return DependencyGraph(
        id=row.id,
        test_id=row.test_id,
        version=row.version,
        question_ids=frozenset(row.question_ids),
        edges=tuple(
            DependencyEdge(
                from_question_id=edge.from_question_id,
                to_question_id=edge.to_question_id,
                provides=tuple(DependencyProvision(p) for p in edge.provides),
                rationale=edge.rationale,
                confidence=edge.confidence,
            )
            for edge in edge_rows
        ),
        unresolved=tuple(UnresolvedQuestion.from_dict(u) for u in row.unresolved),
        status=DependencyGraphStatus(row.status),
        created_at=row.created_at,
        confirmed_at=row.confirmed_at,
    )
