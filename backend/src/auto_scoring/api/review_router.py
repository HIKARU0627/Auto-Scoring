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
* ``POST .../review/{edit,grade,reject,regrade,approve,undo}`` -- the
  reviewer's decisions (Issue #22; ``grade`` added by Issue #118 for a
  question the AI never graded at all).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.review_actions import (
    AiGradeAlreadyExistsError,
    AiGradeChangedError,
    AnnotationInput,
    CriterionInput,
    NoAiGradeYetError,
    NothingToUndoError,
    QuestionMismatchError,
    approve_question,
    edit_question,
    grade_question_manually,
    regrade_question,
    reject_question,
    undo_last_review,
)
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.models import (
    MAX_COMMENT_CHARS,
    MAX_RECOGNIZED_TEXT_LENGTH,
    TERMINAL_JOB_STATES,
    Annotation,
    AnnotationKind,
    AnswerImageFinding,
    CriterionOutcome,
    DomainError,
    GradeResult,
    GradingSource,
    Job,
    NormalizedRect,
    Question,
    RecognitionResult,
    Review,
    latest_job_for_question,
)
from auto_scoring.domain.review_workflow import (
    ReviewVersionConflict,
    count_confirmed_questions,
    effective_latest_review,
    is_confirmed,
)
from auto_scoring.jobs.queue import JobQueueService


class SubmissionReviewProgressResponse(BaseModel):
    """How far one answer has got, counted per question (Issue #113).

    **Counts only.** 答案キュー needs three numbers per row and nothing else; the
    row's own状態 already comes from `SubmissionResponse.state`, and anything
    richer belongs to the screen that opens the answer.

    Why it exists at all: `GET /submissions/{id}/questions/{qid}/reviews` is
    per-question, so a 40-answer test would cost 200 requests to draw one list
    -- the same shape ホーム画面 already refuses for jobs
    (`docs/home-dashboard.md` §4). One request for the whole test instead.
    """

    submission_id: str
    total_questions: int
    confirmed_questions: int
    #: Questions the reviewer will have to grade themselves: the pipeline has
    #: stopped on them (`TERMINAL_JOB_STATES`) without producing an AI grade,
    #: and nobody has confirmed them yet. This is the count 「点数を入力」
    #: (Issue #118) exists for.
    #:
    #: **Not "the job failed".** A question can end up here without any failure
    #: -- a crop that was never worth sending to the AI, a host with no OCR
    #: (Issue #114) -- and what matters to the reviewer is the same either way:
    #: this answer needs them to produce N grades by hand rather than confirm N
    #: proposals. 金曜の午後の終わりに「残り3枚」を見たとき、それが「見るだけ」
    #: なのか「1問ずつ自分で採点する」なのかで、残り時間の見積もりがまるで違う。
    #:
    #: Deliberately the server-side twin of the client's `_canGradeManually`
    #: (`pdf_review_page.dart`): 一覧が0と言っているのに開いた先が
    #: 「点数を入力」を出す、は起きてはならない (Issue #84)。
    manual_grading_questions: int


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
    #: 採点AIが「渡された画像に何が写っていたか」として申告した区分
    #: (`AnswerImageFinding`、Issue #136)。点数とは別の主張なので別の欄で運ぶ。
    #:
    #: Issue #136 はこれを保存するところまでで、**画面へ出す経路が無かった**。
    #: 出す理由は実機再検証 #4 の実測にある: 0点になった設問のうち、AI自身が
    #: `blank`(解答欄に何も書かれていない)と申告した3件は**3件とも切り出しの
    #: 誤り**で、しかも採点信頼度はちょうど 1.00 だった。数字の側からは正しい
    #: 0点と見分けが付かず、見分けが付く材料はAI自身のこの申告しか残っていない。
    #:
    #: `not_the_answer` はここに現れない。その申告を受けた採点は `GradeResult`
    #: を作らずにジョブごと失敗する(`jobs.grading_processor`)ので、そもそも
    #: 点数が存在しない -- `GradeResult.__post_init__` がそれを不変条件として
    #: 持っている。`None` は「providerが何も申告しなかった」で、`answer` とは
    #: 別物である(誰も見ていない切り出しを保証したことにしない)。
    answer_image_finding: AnswerImageFinding | None = None
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
            answer_image_finding=grade.answer_image_finding,
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
    # The id of the AI grade the reviewer's client currently displays, if
    # any (Issue #22 P1 review). ``None`` skips the check -- see
    # `adapters.review_actions._latest_ai_grade_matching`'s docstring.
    expected_ai_grade_id: str | None = None
    score_awarded: int = Field(ge=0)
    score_maximum: int = Field(ge=0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    criteria: list[CriterionOutcomeRequest] = Field(default_factory=list)
    rationale: str | None = None
    comment: str | None = Field(default=None, max_length=MAX_COMMENT_CHARS)
    recognized_text: str | None = Field(default=None, max_length=MAX_RECOGNIZED_TEXT_LENGTH)
    annotations: list[AnnotationEditRequest] | None = None
    note: str | None = Field(default=None, max_length=MAX_COMMENT_CHARS)


class ManualGradeRequest(BaseModel):
    """A grade a person enters for a question the AI never graded (Issue
    #118).

    The same fields as `EditReviewRequest` minus ``expected_ai_grade_id``:
    there is no AI attempt to pin this decision to, and the server refuses
    (409) if one turns out to exist -- see
    `adapters.review_actions.grade_question_manually`.
    """

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
    # See `EditReviewRequest.expected_ai_grade_id`.
    expected_ai_grade_id: str | None = None
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


def _needs_manual_grading(
    uow: SqlAlchemyUnitOfWork,
    *,
    submission_id: str,
    question_id: str,
    jobs: Sequence[Job],
    reviews: Sequence[Review],
) -> bool:
    """Whether this question is one the reviewer has to grade themselves.

    Three conditions, and all three are the client's (`_canGradeManually` in
    `pdf_review_page.dart`) restated on the server:

    1. The pipeline has stopped on it (`TERMINAL_JOB_STATES`). A question still
       queued or running may yet produce a grade, so it is not the reviewer's
       job *yet*. A question with no job at all has not even been asked.
    2. The AI produced no grade. Issue #97 deliberately persists nothing when
       grading fails, and Issue #122 will stop sending crops that are almost
       blank at all -- **neither leaves a `GradeResult` behind**, which is
       exactly why "the job failed" is the wrong thing to count.
    3. Nobody has confirmed it yet -- including by having already graded it
       manually. This counts *remaining* work, not work that once existed.
    """
    job = latest_job_for_question(jobs, question_id)
    if job is None or job.state not in TERMINAL_JOB_STATES:
        return False
    if uow.grades.latest(submission_id, question_id, GradingSource.AI) is not None:
        return False
    return not is_confirmed(effective_latest_review(reviews))


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
        "/tests/{test_id}/review-progress",
        response_model=list[SubmissionReviewProgressResponse],
    )
    def list_review_progress(test_id: str) -> list[SubmissionReviewProgressResponse]:
        """Per-question review progress for every answer of one test.

        Ordered by the answers' own ``created_at``, the order every other list
        of a test's answers already uses (`SubmissionRepository.list_for_test`),
        so the client never has to re-sort to line this up with
        `GET /tests/{id}/submissions`.
        """
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            if uow.tests.get(test_id) is None:
                raise HTTPException(404, detail=f"test {test_id!r} not found")
            question_ids = [question.id for question in uow.questions.list_for_test(test_id)]
            progress = []
            for submission in uow.submissions.list_for_test(test_id):
                reviews_by_question = {
                    question_id: uow.reviews.history(submission.id, question_id)
                    for question_id in question_ids
                }
                jobs = uow.jobs.list_for_submission(submission.id)
                progress.append(
                    SubmissionReviewProgressResponse(
                        submission_id=submission.id,
                        total_questions=len(question_ids),
                        confirmed_questions=count_confirmed_questions(
                            question_ids, reviews_by_question
                        ),
                        manual_grading_questions=sum(
                            1
                            for question_id in question_ids
                            if _needs_manual_grading(
                                uow,
                                submission_id=submission.id,
                                question_id=question_id,
                                jobs=jobs,
                                reviews=reviews_by_question[question_id],
                            )
                        ),
                    )
                )
        return progress

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
                    expected_ai_grade_id=request.expected_ai_grade_id,
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
            except (NoAiGradeYetError, AiGradeChangedError) as error:
                raise HTTPException(409, detail=str(error)) from error
            except ReviewVersionConflict as error:
                raise _version_conflict(error) from error
            except (DomainError, ValueError) as error:
                # A request whose score/criterion-outcome/annotation-rect
                # combination passed pydantic field validation but fails once
                # `edit_question` actually builds the domain objects (e.g.
                # `score_awarded > score_maximum`, an unrecognized criterion
                # outcome, an out-of-page annotation rect) -- a malformed
                # client request, not a server fault (P2 review).
                raise HTTPException(422, detail=str(error)) from error
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
        "/submissions/{submission_id}/questions/{question_id}/review/grade",
        response_model=ReviewActionResponse,
        status_code=201,
    )
    def grade_manually(
        submission_id: str, question_id: str, request: ManualGradeRequest
    ) -> ReviewActionResponse:
        """Record a person's own grade for a question with no AI grade at all
        (Issue #118) -- the way out of a permanently-failed grading job,
        which by design leaves no `GradeResult` behind (Issue #97).

        409 when an AI grade does exist: that is the ``edit``/``approve``
        case, and this route must not quietly set aside an attempt the
        reviewer has not seen.
        """
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            try:
                result = grade_question_manually(
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
            except AiGradeAlreadyExistsError as error:
                raise HTTPException(409, detail=str(error)) from error
            except ReviewVersionConflict as error:
                raise _version_conflict(error) from error
            except (DomainError, ValueError) as error:
                # Same boundary as `edit` -- see its own handler.
                raise HTTPException(422, detail=str(error)) from error
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
                    expected_ai_grade_id=request.expected_ai_grade_id,
                    note=request.note,
                    now=datetime.now(UTC).replace(tzinfo=None),
                )
            except (LookupError, QuestionMismatchError) as error:
                raise HTTPException(404, detail=str(error)) from error
            except (NoAiGradeYetError, AiGradeChangedError) as error:
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
