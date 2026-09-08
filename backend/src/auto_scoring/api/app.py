"""FastAPI application factory for the sidecar."""

from __future__ import annotations

import atexit
import tempfile
import threading
from asyncio import to_thread
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring import __version__
from auto_scoring.adapters.ai.null_provider import NullAIProvider
from auto_scoring.adapters.data_root_lock import acquire_data_root_lock
from auto_scoring.adapters.image.opencv_preprocessor import OpenCvImagePreprocessor
from auto_scoring.adapters.in_memory_repository import InMemoryScoreRepository
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.ocr.null_provider import NullOCRProvider
from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine
from auto_scoring.adapters.submission_intake import (
    DuplicateSubmissionError,
    SubmissionIntakeResult,
    SubmissionRetryConflictError,
    TestNotReadyError,
    intake_submission,
    repair_incomplete_submissions,
)
from auto_scoring.adapters.test_intake import repair_incomplete_test_registrations
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.auth import generate_token, require_token
from auto_scoring.api.body_size_limit import MaxBodySizeMiddleware
from auto_scoring.api.dependency_graph_router import build_dependency_graph_router
from auto_scoring.api.export_router import build_export_router
from auto_scoring.api.jobs_router import build_jobs_router
from auto_scoring.api.recognitions_router import build_recognitions_router
from auto_scoring.api.review_router import build_review_router
from auto_scoring.api.submission_upload_gate import SubmissionUploadGateMiddleware
from auto_scoring.api.test_registration_router import build_test_registration_router
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url
from auto_scoring.db.migrator import upgrade
from auto_scoring.domain.ai_provider import AIProvider
from auto_scoring.domain.image_preprocess import ImagePreprocessor
from auto_scoring.domain.job_execution import JobProcessor
from auto_scoring.domain.models import MAX_STUDENT_LABEL_LENGTH, JobKind, Submission, TestStatus
from auto_scoring.domain.ocr import OCRProvider
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_intake import (
    IntakeLimits,
    PdfIntakeError,
    PdfTooLargeError,
    StagedOutputTooLargeError,
)
from auto_scoring.domain.scoring import clamp_score
from auto_scoring.jobs.clock import Clock
from auto_scoring.jobs.export_processor import ExportJobProcessor
from auto_scoring.jobs.grading_processor import GradingJobProcessor
from auto_scoring.jobs.grading_settings import GradingSettings
from auto_scoring.jobs.queue import JobQueueService
from auto_scoring.jobs.recognition_processor import RecognitionJobProcessor
from auto_scoring.jobs.recognition_settings import RecognitionSettings
from auto_scoring.jobs.routing_processor import ByKindJobProcessor
from auto_scoring.jobs.settings import QueueSettings

_PDF_INTAKE_ERROR_STATUS: dict[type[PdfIntakeError], int] = {
    PdfTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
    StagedOutputTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
}

#: Read chunk size for _read_upload_within_limit. Bounds how much of an
#: over-limit upload we ever materialize in one `bytes` object before
#: aborting (AGENTS.md "Validate every input that crosses a trust boundary").
_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024

#: Slack added on top of IntakeLimits.max_size_bytes for the ASGI-level
#: MaxBodySizeMiddleware. That middleware bounds the *whole* multipart
#: request body (boundary markers, part headers, the student_label field),
#: not just the PDF part; without this margin, a PDF sitting right at the
#: per-file limit would push the total body over it and get rejected by the
#: middleware even though _read_upload_within_limit (which only measures the
#: file part) would have accepted it.
_MULTIPART_OVERHEAD_BYTES = 64 * 1024


async def _read_upload_within_limit(file: UploadFile, max_size_bytes: int) -> bytes:
    """Read ``file`` in bounded chunks, raising as soon as it exceeds
    ``max_size_bytes`` rather than first materializing the whole body.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size_bytes:
            raise PdfTooLargeError(f"file size exceeds limit {max_size_bytes}")
        chunks.append(chunk)
    return b"".join(chunks)


class ScoreRequest(BaseModel):
    key: str
    raw: int
    maximum: int


class ScoreResponse(BaseModel):
    key: str
    awarded: int
    maximum: int
    ratio: float


class TestSummary(BaseModel):
    id: str
    name: str
    subject: str | None = None


class SubmissionResponse(BaseModel):
    id: str
    test_id: str
    state: str
    page_count: int
    student_label: str | None = None
    original_filename: str | None = None
    review_reason: str | None = None
    created_at: datetime
    is_retry: bool = False


def _submission_response(result_submission: Submission, *, is_retry: bool) -> SubmissionResponse:
    return SubmissionResponse(
        id=result_submission.id,
        test_id=result_submission.test_id,
        state=result_submission.state.value,
        page_count=result_submission.page_count,
        student_label=result_submission.student_label,
        original_filename=result_submission.original_filename,
        review_reason=result_submission.review_reason,
        created_at=result_submission.created_at,
        is_retry=is_retry,
    )


def create_app(
    *,
    api_token: str | None = None,
    data_root: Path | None = None,
    session_factory: sessionmaker[Session] | None = None,
    pdf_engine: PdfEngine | None = None,
    image_preprocessor: ImagePreprocessor | None = None,
    intake_limits: IntakeLimits | None = None,
    max_concurrent_uploads: int = 2,
    job_processor: JobProcessor | None = None,
    queue_settings: QueueSettings | None = None,
    clock: Clock | None = None,
    ocr_provider: OCRProvider | None = None,
    recognition_settings: RecognitionSettings | None = None,
    ai_provider: AIProvider | None = None,
    grading_settings: GradingSettings | None = None,
    export_processor: JobProcessor | None = None,
) -> FastAPI:
    """Build the sidecar app.

    ``api_token`` is the bearer token every non-health route requires. When it
    is omitted a random one is minted, so an app object always has a token and
    the protected routes are never accidentally open.

    ``data_root`` is the ``app-data/`` directory (simplified-design-spec.md
    §23). When omitted, a fresh temp directory is used -- fine for schema
    export and tests, but a real sidecar run always passes an explicit,
    persistent path (see ``auto_scoring.api.sidecar``). The final production
    location is provisional pending the Windows-distribution issue (see
    ``docs/answer-intake-and-preprocessing.md`` §5). The auto-created temp
    directory is registered for cleanup at process exit (``atexit``, not a
    FastAPI/ASGI ``lifespan`` hook: existing call sites -- the module-level
    ``app`` below, and tests that build a ``TestClient`` without the ``with``
    form -- never drive ``lifespan`` events) so it doesn't accumulate on disk
    across every import/test run that omits ``data_root``.

    ``max_concurrent_uploads`` bounds how many ``create_submission`` requests
    may have their upload body parsed/materialized at once; see
    ``SubmissionUploadGateMiddleware`` for why that capacity has to be
    reserved at the ASGI boundary, before FastAPI ever touches the body, not
    inside the (already serialized) intake pipeline itself.

    ``session_factory`` lets a caller supply an already-migrated database
    directly (Issue #26's dependency-graph tests do this against an
    isolated fixture) instead of having this function build one from
    ``data_root``. When supplied, this function never touches migrations,
    engine creation/disposal, or the startup repair sweep for it -- the
    caller owns that database's whole lifecycle. ``store`` (used by the
    submission/test routes below regardless) still comes from ``data_root``
    as usual either way. It also means this function never takes the
    data-root lock (see ``auto_scoring.adapters.data_root_lock``): a test
    fixture's session_factory has no real, shared ``data_root`` to protect
    two instances from racing over, and existing tests deliberately build
    more than one `create_app` against the same ``data_root`` fixture to
    simulate a process restart -- releasing the lock (see below) before the
    next one is built.

    ``job_processor``/``queue_settings``/``clock`` configure Issue #18's
    parallel job queue (`auto_scoring.jobs.queue.JobQueueService`).
    ``job_processor`` defaults to `auto_scoring.jobs.grading_processor.
    GradingJobProcessor` (Issue #20 -- recognizes via `RecognitionJobProcessor`
    (Issue #19) and then AI-grades via `AIProvider`, both halves of the one
    per-question job). Tests inject a fake (``tests/fakes.py``). The queue's
    worker pool only actually starts/stops via the FastAPI lifespan below, so
    a `TestClient` used without ``with`` (several existing tests do this,
    same as the temp-dir cleanup above) never runs it -- see
    ``app.state.queue_service`` for tests that need to drive it directly
    instead.

    ``ocr_provider``/``recognition_settings`` and ``ai_provider``/
    ``grading_settings`` configure that default processor's two halves.
    ``ocr_provider`` defaults to `auto_scoring.adapters.ocr.null_provider.
    NullOCRProvider` -- the chosen OCR service (Google Document AI,
    business-rules-and-evaluation-data.md section 3 (A), Issue #81) has no
    adapter yet. ``ai_provider`` defaults to `auto_scoring.adapters.ai.
    null_provider.NullAIProvider` for the same reason -- section 3 (B)'s
    fallback chain is not implemented yet (docs/ai-grading-pipeline.md).
    Both null adapters are honest about not being configured yet (confidence
    0.0, never a fabricated reading/grade) rather than raising, so every
    question routes to needs-review until a real adapter is injected. All
    four are ignored when
    ``job_processor`` is supplied directly.

    ``export_processor`` (Issue #23) defaults to `auto_scoring.jobs.
    export_processor.ExportJobProcessor`, handling ``JobKind.EXPORT`` jobs
    (the annotated-PDF output, ``api.export_router``). Ignored when
    ``job_processor`` is supplied directly -- that parameter still means "the
    whole queue's processor, for every kind"; otherwise ``export_processor``
    is composed alongside the grading processor via `jobs.routing_processor.
    ByKindJobProcessor` so `JobQueueService` itself still only ever holds one
    processor object.
    """
    queue_service_holder: dict[str, JobQueueService] = {}
    lock_handle_holder: dict[str, IO[bytes]] = {}

    scratch: tempfile.TemporaryDirectory[str] | None = None
    if data_root is not None:
        root = data_root
    else:
        scratch = tempfile.TemporaryDirectory(prefix="auto-scoring-app-data-")
        root = Path(scratch.name)
    store = LocalFileStore(root)

    # Only build (and later dispose/repair) a database this function itself
    # owns the lifecycle of. A caller-supplied session_factory is already
    # migrated against its own fixture; touching it here (or sweeping/
    # repairing files under `store`, which has nothing to do with whatever
    # database that session_factory actually points at) would be wrong.
    owns_session_factory = session_factory is None
    if owns_session_factory:
        # Taken here, before migrations/sweep_temp/repair below ever touch
        # this data_root -- not merely later, at ASGI lifespan startup
        # (review round 9, P1's original placement, and the very gap review
        # round 10, P1 flagged: `api/sidecar.py`'s `run()` already binds its
        # socket and writes its handshake file before ever calling this
        # function, so a second sidecar process against a data_root a live
        # process already owns would otherwise run every step below --
        # deleting *.part files the first process may still be writing,
        # marking its in-flight submissions erroneous -- before this
        # function, let alone its lifespan, ever got a chance to fail).
        lock_handle_holder["handle"] = acquire_data_root_lock(root)
    db_engine = None
    try:
        if owns_session_factory:
            db_url = sqlite_url(store.database_path())
            upgrade(db_url, "head")
            db_engine = create_sqlite_engine(db_url)
            session_factory = build_session_factory(db_engine)
        assert session_factory is not None  # either supplied, or just built above

        if owns_session_factory:
            # Startup crash recovery. sweep_temp was always documented as "run
            # it on startup" (its own docstring) but was never actually wired
            # up anywhere; it only removes interrupted writes' leftover
            # *.part files, not the DB side of the same problem -- a prior
            # run that crashed or lost power between a submission's DB commit
            # and the file writes that follow it (adapters.atomic.
            # FinalizationError only catches that failure when the process is
            # alive to raise it) leaves that submission stuck: recorded as
            # complete, some files missing, and no way to retry it.
            # repair_incomplete_submissions covers that other half.
            # repair_incomplete_test_registrations covers the same crash
            # window for test registration (Issue #16 review): a `Test` row
            # committed before its two PDFs both finished writing, with no
            # `error` state to retry into and no endpoint able to find or
            # remove it otherwise.
            store.sweep_temp()
            with SqlAlchemyUnitOfWork(session_factory) as uow:
                repair_incomplete_submissions(uow, store)
                repair_incomplete_test_registrations(uow, store)
    except BaseException:
        # Nothing below this point has run yet, so nothing else needs
        # unwinding -- but this function's caller (or a test) may go on to
        # retry it, or build a second `create_app` against a *different*
        # data_root, in the same process, and must not find this data_root
        # still locked because a failed attempt never released it.
        handle = lock_handle_holder.pop("handle", None)
        if handle is not None:
            handle.close()
        raise

    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        service = queue_service_holder["queue_service"]
        await service.start()
        try:
            yield
        finally:
            await service.shutdown()
            handle = lock_handle_holder.pop("handle", None)
            if handle is not None:
                handle.close()

    app = FastAPI(title="Auto-Scoring Sidecar", version=__version__, lifespan=_lifespan)
    app.state.api_token = api_token or generate_token()

    engine = pdf_engine or PdfiumPypdfEngine()

    # PDFium is not safe to call concurrently from multiple threads of the
    # same process (pypdfium2's own multithreading guidance). Shared by every
    # caller that offloads PDFium work to a worker thread to free the event
    # loop: submission intake (`_run_intake` below) and, since Issue #23, the
    # export job processor -- one lock, so a render in either never overlaps
    # a render in the other. Every intake request was already fully
    # serialized before this lock existed -- the event loop ran each one to
    # completion with nothing else interleaved -- so this isn't a throughput
    # regression, just the same serialization moved off the loop.
    pdfium_lock = threading.Lock()

    default_recognition_processor = RecognitionJobProcessor(
        session_factory,
        store,
        ocr_provider or NullOCRProvider(),
        settings=recognition_settings,
        clock=clock,
    )
    default_grading_processor = GradingJobProcessor(
        session_factory,
        store,
        default_recognition_processor,
        ai_provider or NullAIProvider(),
        grading_settings=grading_settings,
        clock=clock,
    )
    default_export_processor = ExportJobProcessor(
        session_factory, store, engine, pdfium_lock, clock=clock
    )
    # `job_processor`, if supplied directly, fully replaces the queue's
    # processor for every kind (existing override semantics, e.g. tests
    # exercising queue mechanics with a `tests/fakes.py` fake); otherwise
    # `EXPORT` jobs are routed to `export_processor`/`default_export_processor`
    # and everything else to the grading processor -- see
    # `jobs.routing_processor.ByKindJobProcessor`.
    effective_job_processor = job_processor or ByKindJobProcessor(
        default=default_grading_processor,
        overrides={JobKind.EXPORT: export_processor or default_export_processor},
    )
    queue_service = JobQueueService(
        session_factory,
        effective_job_processor,
        settings=queue_settings,
        clock=clock,
    )
    queue_service_holder["queue_service"] = queue_service
    app.state.queue_service = queue_service

    if scratch is not None:
        # The startup repair query above (and every other DB access this app
        # ever makes) leaves at least one connection sitting in db_engine's
        # pool -- SQLAlchemy does not close a pooled connection until the
        # engine itself is disposed. On Windows, that connection holds the
        # sqlite file open, so registering only scratch.cleanup (as this
        # used to) fails at process exit with PermissionError and leaks the
        # whole temp app-data directory instead of removing it. Dispose the
        # engine (if this function created one) before cleaning up the
        # directory it lives in.
        #
        # The data-root lock handle (see above) holds `root / ".lock"` open
        # the exact same way -- a caller that builds this app but never
        # drives its lifespan (this scratch-cleanup path exists precisely
        # for those callers: real production runs always pass an explicit
        # data_root instead) would otherwise still be holding it open when
        # this fires, and Windows refuses to remove a directory containing
        # an open file just the same as it refuses to remove one containing
        # an open database (review round 10, P1). Close it here too, before
        # `temp_dir.cleanup()`.
        temp_dir = scratch
        engine_to_dispose = db_engine

        def _cleanup_scratch() -> None:
            if engine_to_dispose is not None:
                engine_to_dispose.dispose()
            handle = lock_handle_holder.pop("handle", None)
            if handle is not None:
                handle.close()
            temp_dir.cleanup()

        atexit.register(_cleanup_scratch)

    preprocessor = image_preprocessor or OpenCvImagePreprocessor()
    limits = intake_limits or IntakeLimits()

    # Rejects an over-limit request body at the ASGI stream boundary, before
    # FastAPI's multipart parser buffers/spools it -- api/body_size_limit.py.
    # This is one app-wide limit shared by every multipart-accepting route,
    # not just this module's own /tests/{test_id}/submissions: Issue #16's
    # `POST /tests` carries *two* independently `limits.max_size_bytes`-capped
    # PDFs (model answer + marking manual) in a single multipart body. Sizing
    # this for only one file's worth would 413 a perfectly valid two-PDF
    # registration before either per-file check in
    # `test_registration_router`/`_read_upload_within_limit` ever ran, even
    # though each file on its own is within limits. The per-file limits are
    # enforced precisely by those callers; this middleware only needs to be
    # no smaller than the largest *request* (two files) plus multipart
    # framing overhead.
    _max_files_per_multipart_request = 2
    app.add_middleware(
        MaxBodySizeMiddleware,
        max_bytes=limits.max_size_bytes * _max_files_per_multipart_request
        + _MULTIPART_OVERHEAD_BYTES,
    )

    # Bounds how many uploads may have their body parsed/materialized at
    # once. Added *after* MaxBodySizeMiddleware above so it wraps outside of
    # it (Starlette makes the most-recently-added middleware outermost) and
    # so runs first: auth and capacity are checked before a single byte of
    # the body is read, not just before the (already serialized) render/DB
    # phase -- see submission_upload_gate.py.
    app.add_middleware(
        SubmissionUploadGateMiddleware,
        api_token=app.state.api_token,
        capacity=threading.Semaphore(max_concurrent_uploads),
    )

    def _run_intake(
        *,
        test_id: str,
        filename: str,
        declared_mime: str | None,
        data: bytes,
        student_label: str | None,
        now: datetime,
    ) -> SubmissionIntakeResult:
        with pdfium_lock, SqlAlchemyUnitOfWork(session_factory) as uow:
            return intake_submission(
                uow,
                store,
                engine,
                preprocessor,
                test_id=test_id,
                filename=filename,
                declared_mime=declared_mime,
                data=data,
                student_label=student_label,
                limits=limits,
                now=now,
            )

    repository = InMemoryScoreRepository()
    protected = APIRouter(dependencies=[Depends(require_token)])

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @protected.post("/score")
    def score(request: ScoreRequest) -> ScoreResponse:
        result = clamp_score(request.raw, request.maximum)
        repository.save(request.key, result)
        return ScoreResponse(
            key=request.key,
            awarded=result.awarded,
            maximum=result.maximum,
            ratio=result.ratio,
        )

    @protected.get("/tests")
    def list_tests() -> list[TestSummary]:
        # Answer intake (§16.4) must only offer tests whose registration is
        # actually complete (Issue #16: profile + dependency graph both
        # confirmed) -- a `draft` test can have unconfirmed/incomplete
        # regions or no confirmed dependency graph, and intake_submission()
        # below independently enforces the same gate so this is a UX filter,
        # not the only enforcement point.
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            return [
                TestSummary(id=test.id, name=test.name, subject=test.subject)
                for test in uow.tests.list_all()
                if test.status is TestStatus.READY
            ]

    @protected.get("/tests/{test_id}/submissions")
    def list_submissions(test_id: str) -> list[SubmissionResponse]:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            if uow.tests.get(test_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="test not found")
            return [
                _submission_response(submission, is_retry=False)
                for submission in uow.submissions.list_for_test(test_id)
            ]

    @protected.get("/submissions/{submission_id}")
    def get_submission(submission_id: str) -> SubmissionResponse:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            submission = uow.submissions.get(submission_id)
            if submission is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="submission not found")
            return _submission_response(submission, is_retry=False)

    @protected.post("/tests/{test_id}/submissions", status_code=status.HTTP_201_CREATED)
    async def create_submission(
        test_id: str,
        file: UploadFile = File(...),
        student_label: str | None = Form(None, max_length=MAX_STUDENT_LABEL_LENGTH),
    ) -> SubmissionResponse:
        try:
            data = await _read_upload_within_limit(file, limits.max_size_bytes)
        except PdfTooLargeError as exc:
            raise HTTPException(
                _PDF_INTAKE_ERROR_STATUS[PdfTooLargeError], detail=str(exc)
            ) from exc
        try:
            # Rendering every page and running OpenCV preprocessing is
            # synchronous, CPU-bound work that can take minutes for a large
            # submission; running it inline here would block this whole
            # (single-worker) event loop, so even /healthz and unrelated
            # list/get requests would stall until intake finished. Offload it
            # to a worker thread instead.
            result = await to_thread(
                _run_intake,
                test_id=test_id,
                filename=file.filename or "",
                declared_mime=file.content_type,
                data=data,
                student_label=student_label,
                now=datetime.now(UTC).replace(tzinfo=None),
            )
        except PdfIntakeError as exc:
            status_code = _PDF_INTAKE_ERROR_STATUS.get(type(exc), status.HTTP_400_BAD_REQUEST)
            raise HTTPException(status_code, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except TestNotReadyError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except DuplicateSubmissionError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "message": str(exc),
                    "existing_submission_id": exc.existing_submission_id,
                },
            ) from exc
        except SubmissionRetryConflictError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "message": str(exc),
                    "submission_id": exc.submission_id,
                },
            ) from exc
        return _submission_response(result.submission, is_retry=result.is_retry)

    protected.include_router(
        build_dependency_graph_router(
            session_factory,
            on_job_reissued=lambda job: queue_service.enqueue(job.id),
            on_stale_running_job_cancelled=queue_service.cancel_running_task,
        )
    )
    protected.include_router(build_jobs_router(queue_service))
    protected.include_router(
        build_test_registration_router(
            session_factory,
            store,
            engine,
            intake_limits=limits,
            pdfium_lock=pdfium_lock,
        )
    )
    protected.include_router(build_recognitions_router(session_factory, store))
    protected.include_router(build_review_router(session_factory, store, queue_service))
    protected.include_router(build_export_router(session_factory, store, queue_service))

    app.include_router(protected)
    return app
