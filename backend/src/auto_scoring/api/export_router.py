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
  Every 409 body carries a ``detail.code`` naming *which* refusal it is
  (`domain.pdf_export.ExportRefusalReason`) -- see that enum for why. It is
  not in the OpenAPI schema (`HTTPException.detail` is untyped there), so the
  generated Dart client reads it out of the raw error body next to
  ``detail.question_ids``; on the bulk response below it *is* a declared
  field.
  Progress/retry reuse the existing job endpoints (`api.jobs_router`): poll
  ``GET /jobs/{job_id}`` (or list ``GET /submissions/{submission_id}/jobs``),
  and ``POST /jobs/{job_id}/retry`` if it fails.
* ``POST /tests/{test_id}/export`` -- the same thing for a whole test at once
  (Issue #142). **It never stops at the first refusal**: every submission
  gets a row saying what happened to it (queued / reused / refused, with the
  reason), because a reviewer running 40 answer sheets must not lose the
  other 39 to one bad one. Optional ``submission_ids`` narrows it to a
  subset, which is how "re-run only the ones that failed" is expressed.
* ``GET  /submissions/{submission_id}/exports`` -- every successful export
  for a submission, oldest first (Flutter's "保存先表示" / export history).
* ``GET  /exports/{export_id}/file`` -- the produced PDF's bytes. The app
  needs these to write each answer sheet into the folder the reviewer
  picked: `Export.file_path` is relative to the sidecar's ``app-data/``
  root, and **the app deliberately does not know where that is**
  (`app/lib/main.dart`: the sidecar owns that decision). Handing over bytes
  keeps it that way, and keeps `LocalFileStore`'s "no path escape" rule
  intact -- nothing outside ``app-data/`` is ever written by the sidecar.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore, file_matches_sha256
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.models import Export, Job, JobKind, JobState, Review, Submission
from auto_scoring.domain.pdf_export import (
    ExportRefusal,
    ExportRefusalReason,
    ReexportDecision,
    decide_reexport,
    export_refusal,
    review_version_snapshot,
)
from auto_scoring.jobs.queue import JobQueueService


def _as_utc(value: datetime) -> datetime:
    """See `api.jobs_router._as_utc` for why a naive (DB-stored) UTC
    timestamp must be marked as such at this boundary."""
    return value.replace(tzinfo=UTC)


#: Developer-facing wording for each refusal. The screen picks its own
#: Japanese text from the code (`core/widgets/export_dialog.dart`); this is
#: what a raw API consumer and the logs see.
_REFUSAL_MESSAGES = {
    ExportRefusalReason.UNCONFIRMED_QUESTIONS: "one or more questions are not yet confirmed",
    ExportRefusalReason.NO_ROOM_FOR_SCORE: (
        "one or more questions have no area to write the score in"
    ),
}


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


class BulkExportItemStatus(StrEnum):
    """What happened to one submission in a bulk export (Issue #142).

    Deliberately *not* an error: the whole point of the bulk endpoint is
    that one submission's refusal must not cost the reviewer the other 39
    (Issue #142, "途中で止めない"). So every outcome -- including the ones
    the single-submission endpoint raises a 409 for -- comes back as a row.
    """

    #: A fresh `Job` (kind=EXPORT) was queued; poll it via `api.jobs_router`.
    QUEUED = "queued"
    #: `ReexportDecision.REUSE_EXISTING` -- the current review state was
    #: already exported, so nothing was queued and ``export`` is the file.
    REUSED = "reused"
    #: Refused before queueing; ``refusal_code`` says which refusal
    #: (`domain.pdf_export.ExportRefusalReason`) and ``refusal_question_ids``
    #: names the questions it is about.
    REFUSED = "refused"


class BulkExportItemResponse(BaseModel):
    """One submission's outcome in a bulk export."""

    submission_id: str
    #: The uploaded answer sheet's own file name, so the screen can list the
    #: targets by something a human recognises instead of a uuid. `None` for
    #: a submission recorded before the field existed.
    original_filename: str | None = None
    status: BulkExportItemStatus
    job_id: str | None = None
    export: ExportResponse | None = None
    refusal_code: ExportRefusalReason | None = None
    refusal_question_ids: list[str] = Field(default_factory=list)


class BulkExportRequest(BaseModel):
    """``submission_ids`` narrows the run to a subset of the test's
    submissions; omitted or ``null`` means every one of them.

    This is the whole of "失敗した分だけ再実行できる" (Issue #142): the screen
    already holds the failed rows, so re-running them is the same call with
    a shorter list -- no server-side notion of "a bulk run" to persist,
    resume, or garbage-collect.

    Ids that do not belong to ``test_id`` are not silently dropped: the
    request is refused (400), because a caller asking for a submission this
    test does not have is asking for something that will never happen, and
    quietly exporting a shorter list would look like success.
    """

    submission_ids: list[str] | None = None


class BulkExportResponse(BaseModel):
    """Every target's outcome, in the same order the test's submissions are
    listed in (`SubmissionRepository.list_for_test`) -- so the screen's
    progress list matches the queue screen's order."""

    test_id: str
    items: list[BulkExportItemResponse]


def _reviews_by_question(
    uow: SqlAlchemyUnitOfWork, submission_id: str, question_ids: Sequence[str]
) -> dict[str, Sequence[Review]]:
    """Every question's review history for one submission, in the shape
    `domain.pdf_export.export_refusal`/`review_version_snapshot` read."""
    return {
        question_id: uow.reviews.history(submission_id, question_id) for question_id in question_ids
    }


def _refused_item(submission: Submission, refusal: ExportRefusal) -> BulkExportItemResponse:
    return BulkExportItemResponse(
        submission_id=submission.id,
        original_filename=submission.original_filename,
        status=BulkExportItemStatus.REFUSED,
        refusal_code=refusal.reason,
        refusal_question_ids=list(refusal.question_ids),
    )


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

            questions = uow.questions.list_for_test(submission.test_id, scoring_targets_only=True)
            question_ids = [question.id for question in questions]
            reviews_by_question = _reviews_by_question(uow, submission_id, question_ids)
            refusal = export_refusal(questions, reviews_by_question)
            if refusal is not None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail={
                        "code": refusal.reason.value,
                        "message": _REFUSAL_MESSAGES[refusal.reason],
                        "question_ids": list(refusal.question_ids),
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

    @router.post("/tests/{test_id}/export", response_model=BulkExportResponse)
    def request_bulk_export(
        test_id: str, request: BulkExportRequest | None = None
    ) -> BulkExportResponse:
        """Export a whole test's answer sheets in one go (Issue #142).

        Runs the *same* per-submission gate and re-export decision as
        ``POST /submissions/{id}/export`` -- `domain.pdf_export.export_refusal`
        and `decide_reexport` -- for every target, and **never raises on a
        per-submission outcome**. A reviewer running 40 answer sheets loses
        nothing to one unconfirmed sheet; the refused ones come back as rows
        to show, and the rest are queued.

        All the `Job` rows are committed in one transaction and only then
        handed to the queue, matching the single endpoint's order (commit
        first, enqueue after) -- a queued id must always name a row that is
        actually there.
        """
        now = datetime.now(UTC).replace(tzinfo=None)
        items: list[BulkExportItemResponse] = []
        queued_job_ids: list[str] = []
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            if uow.tests.get(test_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="test not found")

            submissions = uow.submissions.list_for_test(test_id)
            requested = None if request is None else request.submission_ids
            if requested is not None:
                known = {submission.id for submission in submissions}
                unknown = sorted(set(requested) - known)
                if unknown:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail={
                            "message": "submission_ids contains ids not in this test",
                            "submission_ids": unknown,
                        },
                    )
                wanted = set(requested)
                submissions = [s for s in submissions if s.id in wanted]

            questions = uow.questions.list_for_test(test_id, scoring_targets_only=True)
            question_ids = [question.id for question in questions]

            for submission in submissions:
                reviews_by_question = _reviews_by_question(uow, submission.id, question_ids)
                refusal = export_refusal(questions, reviews_by_question)
                if refusal is not None:
                    items.append(_refused_item(submission, refusal))
                    continue

                snapshot = review_version_snapshot(question_ids, reviews_by_question)
                previous = uow.exports.latest_for_submission(submission.id)
                decision = decide_reexport(previous, snapshot)
                if decision is ReexportDecision.REUSE_EXISTING:
                    assert previous is not None  # decide_reexport only returns this when so
                    if file_matches_sha256(store.root / previous.file_path, previous.file_sha256):
                        items.append(
                            BulkExportItemResponse(
                                submission_id=submission.id,
                                original_filename=submission.original_filename,
                                status=BulkExportItemStatus.REUSED,
                                export=ExportResponse.from_domain(previous),
                            )
                        )
                        continue
                    # Same reasoning as the single endpoint: never hand back
                    # a `reuse_existing` pointing at a file that is not
                    # actually on disk.

                job = Job(
                    id=str(uuid4()),
                    kind=JobKind.EXPORT,
                    submission_id=submission.id,
                    state=JobState.QUEUED,
                    created_at=now,
                    updated_at=now,
                )
                uow.jobs.add(job)
                queued_job_ids.append(job.id)
                items.append(
                    BulkExportItemResponse(
                        submission_id=submission.id,
                        original_filename=submission.original_filename,
                        status=BulkExportItemStatus.QUEUED,
                        job_id=job.id,
                    )
                )
            uow.commit()
        for job_id in queued_job_ids:
            queue_service.enqueue(job_id)
        return BulkExportResponse(test_id=test_id, items=items)

    @router.get(
        "/exports/{export_id}/file",
        response_class=Response,
        responses={
            200: {
                "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
                "description": "The generated annotated PDF's bytes.",
            }
        },
    )
    def get_export_file(export_id: str) -> Response:
        """The produced PDF itself, so the app can write it wherever the
        reviewer asked (Issue #142).

        The sidecar does not copy files out of ``app-data/`` on request: the
        destination is a folder a human picked in a desktop file dialog, and
        `LocalFileStore` exists precisely to guarantee nothing the sidecar
        writes lands outside its own root. Handing over bytes keeps the
        "where do the reviewer's files go" decision entirely on the app side,
        where the dialog is, and mirrors how the review screen already gets
        `GET /submissions/{id}/source-pdf`.
        """
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            export = uow.exports.get(export_id)
        if export is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="export not found")
        try:
            data = store.read_bytes(store.root / export.file_path)
        except FileNotFoundError as error:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="export file not found on disk"
            ) from error
        return Response(content=data, media_type="application/pdf")

    @router.get("/submissions/{submission_id}/exports", response_model=list[ExportResponse])
    def list_exports(submission_id: str) -> list[ExportResponse]:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            if uow.submissions.get(submission_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="submission not found")
            exports = uow.exports.list_for_submission(submission_id)
            return [ExportResponse.from_domain(export) for export in exports]

    return router
