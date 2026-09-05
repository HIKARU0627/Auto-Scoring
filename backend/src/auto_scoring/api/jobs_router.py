"""HTTP boundary for the parallel AI processing queue (Issue #18).

Thin per `AGENTS.md` "Architecture": every handler only parses the request,
calls into `auto_scoring.jobs.queue.JobQueueService`, and translates the
result to a Pydantic response. Mounted under the sidecar's bearer-token auth
(see `auto_scoring.api.app.create_app`).

Endpoints:

* ``POST /submissions/{submission_id}/jobs`` -- create (idempotently) and
  queue this submission's per-question jobs from its test's confirmed
  dependency graph.
* ``GET  /submissions/{submission_id}/jobs`` -- list, for progress display.
* ``GET  /jobs/{job_id}`` -- one job's detail.
* ``POST /jobs/{job_id}/retry`` -- requeue a FAILED job.
* ``POST /jobs/{job_id}/cancel`` -- cancel a QUEUED/BLOCKED/FAILED/RUNNING job.
* ``POST /submissions/{submission_id}/questions/{question_id}/resume`` --
  human-triggered resume once a low-confidence/failed prerequisite has been
  corrected (business-rules-and-evaluation-data.md §4.4).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auto_scoring.domain.models import Job
from auto_scoring.jobs.queue import (
    JobCancelConflictError,
    JobNotCancellableError,
    JobNotFoundError,
    JobNotRetryableError,
    JobQueueService,
    SubmissionJobCreationConflictError,
    SubmissionNotReadyError,
)


def _as_utc(value: datetime) -> datetime:
    """Mark a naive (DB-stored) UTC timestamp as UTC for the API boundary --
    see `auto_scoring.api.dependency_graph_router._as_utc` for why this
    matters to the generated Dart client's ISO-8601 parser."""
    return value.replace(tzinfo=UTC)


class JobResponse(BaseModel):
    id: str
    kind: str
    submission_id: str
    question_id: str | None = None
    state: str
    attempts: int
    max_attempts: int
    last_error: str | None = None
    error_code: str | None = None
    blocked_on_question_id: str | None = None
    usable: bool | None = None
    dependency_graph_version: int | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, job: Job) -> JobResponse:
        return cls(
            id=job.id,
            kind=job.kind.value,
            submission_id=job.submission_id,
            question_id=job.question_id,
            state=job.state.value,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            last_error=job.last_error,
            error_code=job.error_code.value if job.error_code is not None else None,
            blocked_on_question_id=job.blocked_on_question_id,
            usable=job.usable,
            dependency_graph_version=job.dependency_graph_version,
            created_at=_as_utc(job.created_at),
            updated_at=_as_utc(job.updated_at),
        )


def build_jobs_router(queue_service: JobQueueService) -> APIRouter:
    """Build the router. Every handler delegates straight to ``queue_service``,
    which owns its own `SqlAlchemyUnitOfWork` per call."""
    router = APIRouter(tags=["jobs"])

    @router.post("/submissions/{submission_id}/jobs", response_model=list[JobResponse])
    def create_submission_jobs(submission_id: str) -> list[JobResponse]:
        try:
            queue_service.submit_submission(submission_id=submission_id)
        except SubmissionNotReadyError as error:
            raise HTTPException(409, detail=str(error)) from error
        except SubmissionJobCreationConflictError as error:
            raise HTTPException(409, detail=str(error)) from error
        except JobNotFoundError as error:
            raise HTTPException(404, detail=str(error)) from error
        jobs = queue_service.list_for_submission(submission_id)
        return [JobResponse.from_domain(job) for job in jobs]

    @router.get("/submissions/{submission_id}/jobs", response_model=list[JobResponse])
    def list_submission_jobs(submission_id: str) -> list[JobResponse]:
        jobs = queue_service.list_for_submission(submission_id)
        return [JobResponse.from_domain(job) for job in jobs]

    @router.post(
        "/submissions/{submission_id}/questions/{question_id}/resume",
        status_code=204,
    )
    def resume_question(submission_id: str, question_id: str) -> None:
        try:
            queue_service.mark_question_usable(submission_id=submission_id, question_id=question_id)
        except JobNotFoundError as error:
            raise HTTPException(404, detail=str(error)) from error

    @router.get("/jobs/{job_id}", response_model=JobResponse)
    def get_job(job_id: str) -> JobResponse:
        job = queue_service.get_job(job_id)
        if job is None:
            raise HTTPException(404, detail=f"job {job_id!r} not found")
        return JobResponse.from_domain(job)

    @router.post("/jobs/{job_id}/retry", response_model=JobResponse)
    def retry_job(job_id: str) -> JobResponse:
        try:
            return JobResponse.from_domain(queue_service.retry_job(job_id))
        except JobNotFoundError as error:
            raise HTTPException(404, detail=str(error)) from error
        except JobNotRetryableError as error:
            raise HTTPException(409, detail=str(error)) from error

    @router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
    def cancel_job(job_id: str) -> JobResponse:
        try:
            return JobResponse.from_domain(queue_service.cancel_job(job_id))
        except JobNotFoundError as error:
            raise HTTPException(404, detail=str(error)) from error
        except JobNotCancellableError as error:
            raise HTTPException(409, detail=str(error)) from error
        except JobCancelConflictError as error:
            raise HTTPException(409, detail=str(error)) from error

    return router
