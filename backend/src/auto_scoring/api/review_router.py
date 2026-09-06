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
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.review_actions import (
    AnnotationInput,
    CriterionInput,
    NoAiGradeYetError,
    NothingToUndoError,
    QuestionMismatchError,
    approve_question,
    edit_question,
    regrade_question,
    reject_question,
    undo_last_review,
)
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.models import (
    MAX_COMMENT_CHARS,
    MAX_RECOGNIZED_TEXT_LENGTH,
    Annotation,
    AnnotationKind,
    CriterionOutcome,
    GradeResult,
    NormalizedRect,
    Question,
    RecognitionResult,
    Review,
)
from auto_scoring.domain.review_workflow import ReviewVersionConflict
from auto_scoring.jobs.queue import JobQueueService


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
    # AIの総評コメント(簡易設計書 §16.5「コメント」、
    # docs/ai-grading-pipeline.md「GradeResultのAI追跡情報とcontextの記録」)。
    comment: str | None = None
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
            comment=grade.comment,
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


class ReviewResponse(BaseModel):
    """One row of the append-only operation history (Issue #22 §19).

    ``version`` is the optimistic-concurrency token a client must echo back
    (as ``expected_version``) on its *next* mutating call for this
    submission-question -- see `domain.review_workflow.next_review_version`
    and `docs/review-edit-history.md` "同時実行制御". A client that has never
    loaded any review for a question passes ``expected_version=0``.
    """

    id: str
    submission_id: str
    question_id: str
    action: str
    version: int
    ai_grade_result_id: str | None = None
    human_grade_result_id: str | None = None
    regrade_job_id: str | None = None
    undone_review_id: str | None = None
    note: str | None = None
    created_at: datetime

    @classmethod
    def from_domain(cls, review: Review) -> ReviewResponse:
        return cls(
            id=review.id,
            submission_id=review.submission_id,
            question_id=review.question_id,
            action=review.action.value,
            version=review.version,
            ai_grade_result_id=review.ai_grade_result_id,
            human_grade_result_id=review.human_grade_result_id,
            regrade_job_id=review.regrade_job_id,
            undone_review_id=review.undone_review_id,
            note=review.note,
            created_at=review.created_at.replace(tzinfo=UTC),
        )


class AnnotationEditRequest(BaseModel):
    """One annotation to record as part of an ``edit`` request. Omitting the
    parent request's ``annotations`` field entirely (not sending an empty
    list) keeps the AI attempt's own marks -- see
    ``adapters.review_actions._carry_forward_annotations``.
    """

    kind: str
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    anchor_text: str | None = None
    comment: str | None = Field(default=None, max_length=MAX_COMMENT_CHARS)

    def to_domain(self) -> AnnotationInput:
        has_rect = None not in (self.x, self.y, self.width, self.height)
        rect = (
            NormalizedRect(x=self.x, y=self.y, width=self.width, height=self.height)  # type: ignore[arg-type]
            if has_rect
            else None
        )
        return AnnotationInput(
            kind=AnnotationKind(self.kind),
            rect=rect,
            anchor_text=self.anchor_text,
            comment=self.comment,
        )


class CriterionOutcomeRequest(BaseModel):
    criterion_id: str
    outcome: str
    confidence: float | None = None

    def to_domain(self) -> CriterionInput:
        return CriterionInput(
            criterion_id=self.criterion_id,
            outcome=CriterionOutcome(self.outcome),
            confidence=self.confidence,
        )


class EditReviewRequest(BaseModel):
    expected_version: int = Field(ge=0)
    score_awarded: int = Field(ge=0)
    score_maximum: int = Field(ge=0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    criteria: list[CriterionOutcomeRequest] = Field(default_factory=list)
    rationale: str | None = None
    comment: str | None = Field(default=None, max_length=MAX_COMMENT_CHARS)
    recognized_text: str | None = Field(default=None, max_length=MAX_RECOGNIZED_TEXT_LENGTH)
    annotations: list[AnnotationEditRequest] | None = None
    note: str | None = Field(default=None, max_length=MAX_COMMENT_CHARS)


class ReasonedReviewRequest(BaseModel):
    expected_version: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=MAX_COMMENT_CHARS)


class ApproveReviewRequest(BaseModel):
    expected_version: int = Field(ge=0)
    note: str | None = Field(default=None, max_length=MAX_COMMENT_CHARS)


class UndoReviewRequest(BaseModel):
    expected_version: int = Field(ge=0)


class RecognitionResponseSlim(BaseModel):
    """The recognized-text row `edit_question` optionally creates. Deliberately
    not the full `api.recognitions_router.RecognitionResponse` (no ``boxes``,
    no ``stage``): a human's manually-entered correction never carries OCR
    word boxes, and this is always ``source=human`` by construction.
    """

    id: str
    text: str
    confidence: float
    created_at: datetime

    @classmethod
    def from_domain(cls, recognition: RecognitionResult) -> RecognitionResponseSlim:
        return cls(
            id=recognition.id,
            text=recognition.text,
            confidence=recognition.confidence,
            created_at=recognition.created_at.replace(tzinfo=UTC),
        )


class ReviewActionResponse(BaseModel):
    """The new `Review` row plus whatever it produced, and the submission's
    state right after re-syncing it (Issue #22 acceptance: "未確認設問が残る
    Submissionは出力可能状態にならない") -- so the review screen can update
    its `SubmissionState` chip without a second round trip.
    """

    review: ReviewResponse
    grade: GradeResultResponse | None = None
    recognition: RecognitionResponseSlim | None = None
    annotations: list[AnnotationResponse] = Field(default_factory=list)
    job_id: str | None = None
    submission_state: str


def _version_conflict(error: ReviewVersionConflict) -> HTTPException:
    return HTTPException(409, detail=str(error))


def build_review_router(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    queue_service: JobQueueService,
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

    @router.get(
        "/submissions/{submission_id}/questions/{question_id}/reviews",
        response_model=list[ReviewResponse],
    )
    def list_reviews(submission_id: str, question_id: str) -> list[ReviewResponse]:
        """The full append-only operation history, oldest first. Its length is
        the ``expected_version`` the client's *next* mutating call for this
        submission-question must pass (0 if the list is empty)."""
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            results = uow.reviews.history(submission_id, question_id)
        return [ReviewResponse.from_domain(result) for result in results]

    @router.post(
        "/submissions/{submission_id}/questions/{question_id}/review/edit",
        response_model=ReviewActionResponse,
        status_code=201,
    )
    def edit(
        submission_id: str, question_id: str, request: EditReviewRequest
    ) -> ReviewActionResponse:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            try:
                result = edit_question(
                    uow,
                    submission_id=submission_id,
                    question_id=question_id,
                    expected_version=request.expected_version,
                    score_awarded=request.score_awarded,
                    score_maximum=request.score_maximum,
                    confidence=request.confidence,
                    criteria=[c.to_domain() for c in request.criteria],
                    rationale=request.rationale,
                    comment=request.comment,
                    recognized_text=request.recognized_text,
                    annotations=(
                        None
                        if request.annotations is None
                        else [a.to_domain() for a in request.annotations]
                    ),
                    note=request.note,
                    now=datetime.now(UTC).replace(tzinfo=None),
                )
            except (LookupError, QuestionMismatchError) as error:
                raise HTTPException(404, detail=str(error)) from error
            except NoAiGradeYetError as error:
                raise HTTPException(409, detail=str(error)) from error
            except ReviewVersionConflict as error:
                raise _version_conflict(error) from error
        return ReviewActionResponse(
            review=ReviewResponse.from_domain(result.review),
            grade=GradeResultResponse.from_domain(result.grade),
            recognition=(
                RecognitionResponseSlim.from_domain(result.recognition)
                if result.recognition is not None
                else None
            ),
            annotations=[AnnotationResponse.from_domain(a) for a in result.annotations],
            submission_state=result.submission.state.value,
        )

    @router.post(
        "/submissions/{submission_id}/questions/{question_id}/review/reject",
        response_model=ReviewActionResponse,
        status_code=201,
    )
    def reject(
        submission_id: str, question_id: str, request: ReasonedReviewRequest
    ) -> ReviewActionResponse:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            try:
                review, submission = reject_question(
                    uow,
                    submission_id=submission_id,
                    question_id=question_id,
                    expected_version=request.expected_version,
                    reason=request.reason,
                    now=datetime.now(UTC).replace(tzinfo=None),
                )
            except (LookupError, QuestionMismatchError) as error:
                raise HTTPException(404, detail=str(error)) from error
            except ReviewVersionConflict as error:
                raise _version_conflict(error) from error
        return ReviewActionResponse(
            review=ReviewResponse.from_domain(review), submission_state=submission.state.value
        )

    @router.post(
        "/submissions/{submission_id}/questions/{question_id}/review/regrade",
        response_model=ReviewActionResponse,
        status_code=201,
    )
    def regrade(
        submission_id: str, question_id: str, request: ReasonedReviewRequest
    ) -> ReviewActionResponse:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            try:
                review, job, submission = regrade_question(
                    uow,
                    submission_id=submission_id,
                    question_id=question_id,
                    expected_version=request.expected_version,
                    reason=request.reason,
                    now=datetime.now(UTC).replace(tzinfo=None),
                )
            except (LookupError, QuestionMismatchError) as error:
                raise HTTPException(404, detail=str(error)) from error
            except ReviewVersionConflict as error:
                raise _version_conflict(error) from error
        # Enqueued only after the row above committed (see
        # `adapters.review_actions.regrade_question`'s own docstring) --
        # mirrors `JobQueueService.submit_submission`'s identical ordering.
        queue_service.enqueue(job.id)
        return ReviewActionResponse(
            review=ReviewResponse.from_domain(review),
            job_id=job.id,
            submission_state=submission.state.value,
        )

    @router.post(
        "/submissions/{submission_id}/questions/{question_id}/review/approve",
        response_model=ReviewActionResponse,
        status_code=201,
    )
    def approve(
        submission_id: str, question_id: str, request: ApproveReviewRequest
    ) -> ReviewActionResponse:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            try:
                review, submission = approve_question(
                    uow,
                    submission_id=submission_id,
                    question_id=question_id,
                    expected_version=request.expected_version,
                    note=request.note,
                    now=datetime.now(UTC).replace(tzinfo=None),
                )
            except (LookupError, QuestionMismatchError) as error:
                raise HTTPException(404, detail=str(error)) from error
            except NoAiGradeYetError as error:
                raise HTTPException(409, detail=str(error)) from error
            except ReviewVersionConflict as error:
                raise _version_conflict(error) from error
        return ReviewActionResponse(
            review=ReviewResponse.from_domain(review), submission_state=submission.state.value
        )

    @router.post(
        "/submissions/{submission_id}/questions/{question_id}/review/undo",
        response_model=ReviewActionResponse,
        status_code=201,
    )
    def undo(
        submission_id: str, question_id: str, request: UndoReviewRequest
    ) -> ReviewActionResponse:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            try:
                review, submission = undo_last_review(
                    uow,
                    submission_id=submission_id,
                    question_id=question_id,
                    expected_version=request.expected_version,
                    now=datetime.now(UTC).replace(tzinfo=None),
                )
            except (LookupError, QuestionMismatchError) as error:
                raise HTTPException(404, detail=str(error)) from error
            except NothingToUndoError as error:
                raise HTTPException(409, detail=str(error)) from error
            except ReviewVersionConflict as error:
                raise _version_conflict(error) from error
        return ReviewActionResponse(
            review=ReviewResponse.from_domain(review), submission_state=submission.state.value
        )

    return router
