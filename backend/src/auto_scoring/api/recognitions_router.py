"""HTTP boundary for recognition results and the manual-entry review path
(Issue #19 acceptance: "OCR失敗時も答案画像をレビューでき、手動文字入力へ進める").

Thin per `AGENTS.md` "Architecture": handlers parse the request, read/write
through a `SqlAlchemyUnitOfWork`, and translate to Pydantic. Mounted under
the sidecar's bearer-token auth (see `auto_scoring.api.app.create_app`).

The full review UI/API is a later issue's job, same as
`auto_scoring.api.jobs_router`'s ``/resume`` endpoint for Issue #18's
analogous "human corrects a low-confidence/failed prerequisite" acceptance
criterion; this module is that same kind of minimal, testable slice for
recognition specifically -- not the final review workflow.

Endpoints:

* ``GET  /submissions/{submission_id}/questions/{question_id}/answer-image``
  -- the cropped answer-area image a human reviews when OCR failed or
  returned low confidence (Issue #17 §7.1).
* ``GET  /submissions/{submission_id}/questions/{question_id}/recognitions``
  -- every `RecognitionResult` so far (AI proposals and human corrections,
  oldest first), for a review UI to show side by side (§19, §35-5).
* ``POST /submissions/{submission_id}/questions/{question_id}/recognitions``
  -- a human's manually-entered text. Always ``source=human``,
  ``confidence=1.0`` (a human read it), and releases any dependent question
  BLOCKED on this one, mirroring ``jobs_router.resume_question`` (Issue #18
  §4.4) -- a future full review API only needs to call the same
  `JobQueueService.mark_question_usable`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.models import (
    MAX_RECOGNIZED_TEXT_LENGTH,
    BoundingBox,
    GradingSource,
    RecognitionResult,
    find_answer_image,
)
from auto_scoring.jobs.queue import JobNotFoundError, JobQueueService, JobResumeConflictError


class BoundingBoxResponse(BaseModel):
    text: str
    x: float
    y: float
    width: float
    height: float

    @classmethod
    def from_domain(cls, box: BoundingBox) -> BoundingBoxResponse:
        return cls(
            text=box.text,
            x=box.rect.x,
            y=box.rect.y,
            width=box.rect.width,
            height=box.rect.height,
        )


class RecognitionResponse(BaseModel):
    id: str
    submission_id: str
    question_id: str
    source: str
    text: str
    confidence: float
    created_at: datetime
    boxes: list[BoundingBoxResponse]

    @classmethod
    def from_domain(cls, result: RecognitionResult) -> RecognitionResponse:
        return cls(
            id=result.id,
            submission_id=result.submission_id,
            question_id=result.question_id,
            source=result.source.value,
            text=result.text,
            confidence=result.confidence,
            created_at=result.created_at.replace(tzinfo=UTC),
            boxes=[BoundingBoxResponse.from_domain(box) for box in result.boxes],
        )


class ManualRecognitionRequest(BaseModel):
    text: str = Field(max_length=MAX_RECOGNIZED_TEXT_LENGTH)


def build_recognitions_router(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    queue_service: JobQueueService,
) -> APIRouter:
    """Build the router. Every handler opens its own `SqlAlchemyUnitOfWork`,
    matching every other router in this package."""
    router = APIRouter(tags=["recognitions"])

    @router.get(
        "/submissions/{submission_id}/questions/{question_id}/answer-image",
        # response_class=Response (the plain Starlette base, media_type=None)
        # instead of the route default JSONResponse: FastAPI otherwise still
        # advertises an *additional* application/json: {schema: {}} content
        # entry alongside the one declared in `responses` below (inferred
        # from response_class.media_type), and openapi-generator picks that
        # one first -- the generated Dart client then tried to JSON-decode
        # the PNG bytes instead of preserving them as raw binary (review
        # round 1, P1).
        response_class=Response,
        responses={
            200: {
                "content": {"image/png": {"schema": {"type": "string", "format": "binary"}}},
                "description": "The cropped answer-area image.",
            }
        },
    )
    def get_answer_image(submission_id: str, question_id: str) -> Response:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            images = uow.answer_images.list_for_submission(submission_id)
            image = find_answer_image(images, question_id)
        if image is None:
            raise HTTPException(404, detail="no answer image recorded for this question")
        data = store.read_bytes(Path(image.image_path))
        return Response(content=data, media_type="image/png")

    @router.get(
        "/submissions/{submission_id}/questions/{question_id}/recognitions",
        response_model=list[RecognitionResponse],
    )
    def list_recognitions(submission_id: str, question_id: str) -> list[RecognitionResponse]:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            results = uow.recognitions.history(submission_id, question_id)
        return [RecognitionResponse.from_domain(result) for result in results]

    @router.post(
        "/submissions/{submission_id}/questions/{question_id}/recognitions",
        response_model=RecognitionResponse,
        status_code=201,
    )
    def create_manual_recognition(
        submission_id: str, question_id: str, request: ManualRecognitionRequest
    ) -> RecognitionResponse:
        recognition = RecognitionResult(
            id=str(uuid4()),
            submission_id=submission_id,
            question_id=question_id,
            source=GradingSource.HUMAN,
            text=request.text,
            confidence=1.0,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            submission = uow.submissions.get(submission_id)
            if submission is None:
                raise HTTPException(404, detail=f"submission {submission_id!r} not found")
            question = uow.questions.get(question_id)
            if question is None:
                raise HTTPException(404, detail=f"question {question_id!r} not found")
            if question.test_id != submission.test_id:
                # Both ids exist individually but belong to different
                # tests -- inserting anyway would persist a
                # RecognitionResult under a question this submission's
                # test never had (review round 1, P2).
                raise HTTPException(
                    404,
                    detail=f"question {question_id!r} does not belong to submission "
                    f"{submission_id!r}'s test",
                )
            uow.recognitions.add(recognition)
            uow.commit()
        # The recognition row above is append-only history and stays valid
        # regardless of what happens next -- if the release below 404s/409s
        # (no confirmed graph yet, or this question's job isn't terminal
        # yet), the human's text is still recorded and
        # `POST .../resume` (jobs_router) can be retried once it is.
        try:
            queue_service.mark_question_usable(submission_id=submission_id, question_id=question_id)
        except JobNotFoundError as error:
            raise HTTPException(404, detail=str(error)) from error
        except JobResumeConflictError as error:
            raise HTTPException(409, detail=str(error)) from error
        return RecognitionResponse.from_domain(recognition)

    return router
