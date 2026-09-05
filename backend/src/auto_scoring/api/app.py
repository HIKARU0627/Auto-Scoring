"""FastAPI application factory for the sidecar."""

from __future__ import annotations

import atexit
import tempfile
import threading
from asyncio import to_thread
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from auto_scoring import __version__
from auto_scoring.adapters.image.opencv_preprocessor import OpenCvImagePreprocessor
from auto_scoring.adapters.in_memory_repository import InMemoryScoreRepository
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine
from auto_scoring.adapters.submission_intake import (
    DuplicateSubmissionError,
    SubmissionIntakeResult,
    SubmissionRetryConflictError,
    intake_submission,
    repair_incomplete_submissions,
)
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.auth import generate_token, require_token
from auto_scoring.api.body_size_limit import MaxBodySizeMiddleware
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url
from auto_scoring.db.migrator import upgrade
from auto_scoring.domain.image_preprocess import ImagePreprocessor
from auto_scoring.domain.models import MAX_STUDENT_LABEL_LENGTH, Submission
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_intake import (
    IntakeLimits,
    PdfIntakeError,
    PdfTooLargeError,
    StagedOutputTooLargeError,
)
from auto_scoring.domain.scoring import clamp_score

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
    pdf_engine: PdfEngine | None = None,
    image_preprocessor: ImagePreprocessor | None = None,
    intake_limits: IntakeLimits | None = None,
    max_concurrent_uploads: int = 2,
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
    may be reading their upload body into memory at once; see the capacity
    reservation there for why this has to happen before the read, not just
    around the (already serialized) intake pipeline itself.
    """
    app = FastAPI(title="Auto-Scoring Sidecar", version=__version__)
    app.state.api_token = api_token or generate_token()

    if data_root is not None:
        root = data_root
    else:
        scratch = tempfile.TemporaryDirectory(prefix="auto-scoring-app-data-")
        atexit.register(scratch.cleanup)
        root = Path(scratch.name)
    store = LocalFileStore(root)
    db_url = sqlite_url(store.database_path())
    upgrade(db_url, "head")
    session_factory = build_session_factory(create_sqlite_engine(db_url))

    # Startup crash recovery. sweep_temp was always documented as "run it on
    # startup" (its own docstring) but was never actually wired up anywhere;
    # it only removes interrupted writes' leftover *.part files, not the DB
    # side of the same problem -- a prior run that crashed or lost power
    # between a submission's DB commit and the file writes that follow it
    # (adapters.atomic.FinalizationError only catches that failure when the
    # process is alive to raise it) leaves that submission stuck: recorded
    # as complete, some files missing, and no way to retry it.
    # repair_incomplete_submissions covers that other half.
    store.sweep_temp()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repair_incomplete_submissions(uow, store)

    engine = pdf_engine or PdfiumPypdfEngine()
    preprocessor = image_preprocessor or OpenCvImagePreprocessor()
    limits = intake_limits or IntakeLimits()

    # Rejects an over-limit request body at the ASGI stream boundary, before
    # FastAPI's multipart parser buffers/spools it -- api/body_size_limit.py.
    # The per-file limit is enforced precisely by _read_upload_within_limit
    # below; this one only needs to be no *smaller* than that plus multipart
    # framing overhead.
    app.add_middleware(
        MaxBodySizeMiddleware,
        max_bytes=limits.max_size_bytes + _MULTIPART_OVERHEAD_BYTES,
    )

    # PDFium is not safe to call concurrently from multiple threads of the
    # same process (pypdfium2's own multithreading guidance); this lock
    # serializes actual intake runs so offloading them to a worker thread
    # (below) frees the event loop without risking two renders touching
    # PDFium at once. Every intake request was already fully serialized
    # before this change too -- the event loop ran each one to completion
    # with nothing else interleaved -- so this isn't a throughput regression,
    # just the same serialization moved off the loop.
    intake_lock = threading.Lock()

    # Bounds how many uploads may be materializing their body into memory at
    # once. intake_lock above only serializes the render/DB phase (run in a
    # worker thread); it does nothing about the read that happens *before*
    # that, in the async handler itself, on the event loop. Without a
    # separate cap there, N concurrent requests near max_size_bytes could
    # each hold a full `bytes` object simultaneously while merely waiting
    # their turn at intake_lock -- each request staying within its own
    # per-file limit but the aggregate still exhausting memory.
    intake_capacity = threading.Semaphore(max_concurrent_uploads)

    def _run_intake(
        *,
        test_id: str,
        filename: str,
        declared_mime: str | None,
        data: bytes,
        student_label: str | None,
        now: datetime,
    ) -> SubmissionIntakeResult:
        with intake_lock, SqlAlchemyUnitOfWork(session_factory) as uow:
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
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            return [
                TestSummary(id=test.id, name=test.name, subject=test.subject)
                for test in uow.tests.list_all()
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
        # Reserved *before* reading a single byte of the upload -- see
        # intake_capacity above. A non-blocking acquire rejects outright
        # (503) instead of queuing: queuing here would just move the same
        # unbounded pile-up from "requests holding a full buffer" to
        # "requests blocked in this handler", without bounding memory any
        # better.
        if not intake_capacity.acquire(blocking=False):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="too many submissions are being processed right now; try again shortly",
            )
        try:
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
        finally:
            intake_capacity.release()
        return _submission_response(result.submission, is_retry=result.is_retry)

    app.include_router(protected)
    return app


app = create_app()
