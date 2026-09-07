"""HTTP boundary for the annotated-PDF export feature (Issue #23, parent #3).

Thin per `AGENTS.md` "Architecture": every handler only parses the request,
calls into `domain.pdf_export`/the job queue, and translates the result.
Mounted under the sidecar's bearer-token auth (see
`auto_scoring.api.app.create_app`). See `docs/pdf-export.md` for the full
design record.

Endpoints:

* ``POST /submissions/{submission_id}/export`` -- refuse (409) if any
  question is not yet confirmed, naming which; otherwise decide
  (`domain.pdf_export.decide_reexport`) whether to hand back the latest
  successful export as-is or queue a new ``Job`` (kind=``EXPORT``).
  Progress/retry reuse the existing job endpoints (`api.jobs_router`): poll
  ``GET /jobs/{job_id}`` (or list ``GET /submissions/{submission_id}/jobs``),
  and ``POST /jobs/{job_id}/retry`` if it fails.
* ``GET  /submissions/{submission_id}/exports`` -- every successful export
  for a submission, oldest first (Flutter's "保存先表示" / export history).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore, file_matches_sha256
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.models import Export, Job, JobKind, JobState
from auto_scoring.domain.pdf_export import (
    ReexportDecision,
    decide_reexport,
    review_version_snapshot,
    unconfirmed_question_ids,
)
from auto_scoring.jobs.queue import JobQueueService


def _as_utc(value: datetime) -> datetime:
    """See `api.jobs_router._as_utc` for why a naive (DB-stored) UTC
    timestamp must be marked as such at this boundary."""
    return value.replace(tzinfo=UTC)


class ExportResponse(BaseModel):
    id: str
    submission_id: str
    job_id: str
    file_path: str
    file_sha256: str
    created_at: datetime

    @classmethod
    def from_domain(cls, export: Export) -> ExportResponse:
        return cls(
            id=export.id,
            submission_id=export.submission_id,
            job_id=export.job_id,
            file_path=export.file_path,
            file_sha256=export.file_sha256,
            created_at=_as_utc(export.created_at),
        )


class ExportRequestResponse(BaseModel):
    """Result of ``POST .../export``: `decision` is one of
    `domain.pdf_export.ReexportDecision`'s values.

    ``job_id`` is set (and the HTTP status is 202) for
    ``accept_new``/``accept_new_superseding`` -- a fresh `Job` was queued;
    poll it via `api.jobs_router`. ``export`` is set (status 200) for
    ``reuse_existing`` -- nothing was queued, the existing export already
    reflects the current review state.
    """

    decision: str
    job_id: str | None = None
    export: ExportResponse | None = None


def build_export_router(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    queue_service: JobQueueService,
) -> APIRouter:
    """Build the router. Every handler owns its own `SqlAlchemyUnitOfWork`
    per call, same as `api.jobs_router`."""
    router = APIRouter(tags=["export"])

    @router.post(
        "/submissions/{submission_id}/export",
        response_model=ExportRequestResponse,
        status_code=status.HTTP_202_ACCEPTED,
        responses={
            200: {
                "model": ExportRequestResponse,
                "description": (
                    "The current review state was already exported; no new "
                    "job was queued (`decision: reuse_existing`)."
                ),
            }
        },
    )
    def request_export(submission_id: str, response: Response) -> ExportRequestResponse:
        now = datetime.now(UTC).replace(tzinfo=None)
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            submission = uow.submissions.get(submission_id)
            if submission is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="submission not found")

            questions = uow.questions.list_for_test(submission.test_id)
            question_ids = [question.id for question in questions]
            reviews_by_question = {
                question_id: uow.reviews.history(submission_id, question_id)
                for question_id in question_ids
            }
            missing = unconfirmed_question_ids(question_ids, reviews_by_question)
            if missing:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail={
                        "message": "one or more questions are not yet confirmed",
                        "question_ids": sorted(missing),
                    },
                )

            snapshot = review_version_snapshot(question_ids, reviews_by_question)
            previous = uow.exports.latest_for_submission(submission_id)
            decision = decide_reexport(previous, snapshot)
            if decision is ReexportDecision.REUSE_EXISTING:
                assert previous is not None  # decide_reexport only returns this when so
                if file_matches_sha256(store.root / previous.file_path, previous.file_sha256):
                    response.status_code = status.HTTP_200_OK
                    return ExportRequestResponse(
                        decision=decision.value, export=ExportResponse.from_domain(previous)
                    )
                # The recorded export's file is missing or corrupted (P1
                # review, round 2 -- e.g. a crash between its DB commit and
                # the file write that follows it, or the file being
                # removed/corrupted afterward). Never hand back a
                # `reuse_existing` pointing at a file that is not actually
                # there; queue a fresh export instead, exactly as if the
                # review state itself had moved on. `previous`'s row is left
                # untouched as a historical record -- only the same job
                # that originally produced it can repair it in place
                # (`jobs.export_processor.ExportJobProcessor`'s own
                # crash-recovery path, keyed by that job's id).
                decision = ReexportDecision.ACCEPT_NEW_SUPERSEDING

            job = Job(
                id=str(uuid4()),
                kind=JobKind.EXPORT,
                submission_id=submission_id,
                state=JobState.QUEUED,
                created_at=now,
                updated_at=now,
            )
            uow.jobs.add(job)
            uow.commit()
        queue_service.enqueue(job.id)
        return ExportRequestResponse(decision=decision.value, job_id=job.id)

    @router.get("/submissions/{submission_id}/exports", response_model=list[ExportResponse])
    def list_exports(submission_id: str) -> list[ExportResponse]:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            if uow.submissions.get(submission_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="submission not found")
            exports = uow.exports.list_for_submission(submission_id)
            return [ExportResponse.from_domain(export) for export in exports]

    return router
