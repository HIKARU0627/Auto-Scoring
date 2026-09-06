"""HTTP boundary for the 添削レビュー画面 (Issue #21, simplified-design-spec.md §16.5).

Thin per `AGENTS.md` "Architecture": handlers only read through a
`SqlAlchemyUnitOfWork`/`LocalFileStore` and translate to Pydantic -- no
mutation lives here. Issue #21 is scoped to *displaying* the original PDF,
recognition, grading, rubric, and annotation data side by side; persisting a
reviewer's approve/edit/reject decision and generating the final corrected PDF
are explicitly out of scope (Issue #21 "対象外") and are a later issue's job,
same as `auto_scoring.api.recognitions_router`'s manual-recognition endpoint
was for Issue #19 relative to the full review workflow.

Endpoints:

* ``GET /tests/{test_id}/questions`` -- every `Question` for a test (its
  profile areas + rubric), the set the review screen's Navigation Rail and
  Inspector need to know what to show for each question, independent of any
  one submission.
* ``GET /submissions/{submission_id}/source-pdf`` -- the original,
  unmodified answer PDF (§13.1: 元PDF自体は直接編集しない) for the `pdfrx`
  viewer to render underneath the annotation overlay.
* ``GET /submissions/{submission_id}/questions/{question_id}/grades`` --
  every `GradeResult` so far (AI proposals and human corrections, oldest
  first), each carrying its own score, Grading Confidence, rubric-criterion
  outcomes, and rationale (§10, §19, §35-5).
* ``GET /submissions/{submission_id}/questions/{question_id}/annotations``
  -- every `Annotation` recorded for the question, for the PDF overlay.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.models import (
    Annotation,
    GradeResult,
    NormalizedRect,
    Question,
)


class NormalizedRectResponse(BaseModel):
    x: float
    y: float
    width: float
    height: float

    @classmethod
    def from_domain(cls, rect: NormalizedRect) -> NormalizedRectResponse:
        return cls(x=rect.x, y=rect.y, width=rect.width, height=rect.height)


class RubricCriterionResponse(BaseModel):
    id: str
    description: str
    max_points: int
    position: int


class QuestionResponse(BaseModel):
    id: str
    test_id: str
    number: str
    page: int
    points: int
    scoring_method: str
    model_answer: str | None = None
    answer_area: NormalizedRectResponse | None = None
    score_area: NormalizedRectResponse | None = None
    comment_area: NormalizedRectResponse | None = None
    rubric: list[RubricCriterionResponse]

    @classmethod
    def from_domain(
        cls, question: Question, rubric_criteria: list[RubricCriterionResponse]
    ) -> QuestionResponse:
        return cls(
            id=question.id,
            test_id=question.test_id,
            number=question.number,
            page=question.page,
            points=question.points,
            scoring_method=question.scoring_method.value,
            model_answer=question.model_answer,
            answer_area=_rect(question.answer_area),
            score_area=_rect(question.score_area),
            comment_area=_rect(question.comment_area),
            rubric=rubric_criteria,
        )


def _rect(rect: NormalizedRect | None) -> NormalizedRectResponse | None:
    return None if rect is None else NormalizedRectResponse.from_domain(rect)


class ScoreValueResponse(BaseModel):
    awarded: int
    maximum: int
    ratio: float


class CriterionResultResponse(BaseModel):
    criterion_id: str
    outcome: str
    confidence: float | None = None


class GradeResultResponse(BaseModel):
    id: str
    submission_id: str
    question_id: str
    source: str
    score: ScoreValueResponse
    confidence: float
    criteria: list[CriterionResultResponse]
    rationale: str | None = None
    created_at: datetime

    @classmethod
    def from_domain(cls, grade: GradeResult) -> GradeResultResponse:
        maximum = grade.score.maximum
        return cls(
            id=grade.id,
            submission_id=grade.submission_id,
            question_id=grade.question_id,
            source=grade.source.value,
            score=ScoreValueResponse(
                awarded=grade.score.awarded,
                maximum=maximum,
                ratio=grade.score.awarded / maximum if maximum else 0.0,
            ),
            confidence=grade.confidence,
            criteria=[
                CriterionResultResponse(
                    criterion_id=criterion.criterion_id,
                    outcome=criterion.outcome.value,
                    confidence=criterion.confidence,
                )
                for criterion in grade.criteria
            ],
            rationale=grade.rationale,
            created_at=grade.created_at.replace(tzinfo=UTC),
        )


class AnnotationResponse(BaseModel):
    id: str
    submission_id: str
    question_id: str
    source: str
    kind: str
    rect: NormalizedRectResponse | None = None
    anchor_text: str | None = None
    comment: str | None = None
    created_at: datetime

    @classmethod
    def from_domain(cls, annotation: Annotation) -> AnnotationResponse:
        return cls(
            id=annotation.id,
            submission_id=annotation.submission_id,
            question_id=annotation.question_id,
            source=annotation.source.value,
            kind=annotation.kind.value,
            rect=_rect(annotation.rect),
            anchor_text=annotation.anchor_text,
            comment=annotation.comment,
            created_at=annotation.created_at.replace(tzinfo=UTC),
        )


def build_review_router(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
) -> APIRouter:
    """Build the router. Every handler opens its own `SqlAlchemyUnitOfWork`,
    matching every other router in this package."""
    router = APIRouter(tags=["review"])

    @router.get("/tests/{test_id}/questions", response_model=list[QuestionResponse])
    def list_questions(test_id: str) -> list[QuestionResponse]:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            if uow.tests.get(test_id) is None:
                raise HTTPException(404, detail=f"test {test_id!r} not found")
            questions = uow.questions.list_for_test(test_id)
            responses = []
            for question in sorted(questions, key=lambda q: (q.page, q.number)):
                rubric = uow.rubrics.get_for_question(question.id)
                criteria = (
                    [
                        RubricCriterionResponse(
                            id=criterion.id,
                            description=criterion.description,
                            max_points=criterion.max_points,
                            position=criterion.position,
                        )
                        for criterion in sorted(rubric.criteria, key=lambda c: c.position)
                    ]
                    if rubric is not None
                    else []
                )
                responses.append(QuestionResponse.from_domain(question, criteria))
        return responses

    @router.get(
        "/submissions/{submission_id}/source-pdf",
        response_class=Response,
        responses={
            200: {
                "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
                "description": "The original, unmodified answer PDF.",
            }
        },
    )
    def get_source_pdf(submission_id: str) -> Response:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            submission = uow.submissions.get(submission_id)
        if submission is None:
            raise HTTPException(404, detail=f"submission {submission_id!r} not found")
        try:
            data = store.read_bytes(store.submission_source_pdf_path(submission_id))
        except FileNotFoundError as error:
            raise HTTPException(404, detail="source PDF not found on disk") from error
        return Response(content=data, media_type="application/pdf")

    @router.get(
        "/submissions/{submission_id}/questions/{question_id}/grades",
        response_model=list[GradeResultResponse],
    )
    def list_grades(submission_id: str, question_id: str) -> list[GradeResultResponse]:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            results = uow.grades.history(submission_id, question_id)
        return [GradeResultResponse.from_domain(result) for result in results]

    @router.get(
        "/submissions/{submission_id}/questions/{question_id}/annotations",
        response_model=list[AnnotationResponse],
    )
    def list_annotations(submission_id: str, question_id: str) -> list[AnnotationResponse]:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            results = uow.annotations.list_for(submission_id, question_id)
        return [AnnotationResponse.from_domain(result) for result in results]

    return router
