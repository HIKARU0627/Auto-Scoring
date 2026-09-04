"""FastAPI application factory for the sidecar."""

from __future__ import annotations

import tempfile
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
    intake_submission,
)
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.auth import generate_token, require_token
from auto_scoring.api.body_size_limit import MaxBodySizeMiddleware
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url
from auto_scoring.db.migrator import upgrade
from auto_scoring.domain.image_preprocess import ImagePreprocessor
from auto_scoring.domain.models import Submission
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_intake import IntakeLimits, PdfIntakeError, PdfTooLargeError
from auto_scoring.domain.scoring import clamp_score

_PDF_INTAKE_ERROR_STATUS: dict[type[PdfIntakeError], int] = {
    PdfTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
}

#: Read chunk size for _read_upload_within_limit. Bounds how much of an
#: over-limit upload we ever materialize in one `bytes` object before
#: aborting (AGENTS.md "Validate every input that crosses a trust boundary").
_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024


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
    ``docs/answer-intake-and-preprocessing.md`` §5).
    """
    app = FastAPI(title="Auto-Scoring Sidecar", version=__version__)
    app.state.api_token = api_token or generate_token()

    root = data_root or Path(tempfile.mkdtemp(prefix="auto-scoring-app-data-"))
    store = LocalFileStore(root)
    db_url = sqlite_url(store.database_path())
    upgrade(db_url, "head")
    session_factory = build_session_factory(create_sqlite_engine(db_url))

    engine = pdf_engine or PdfiumPypdfEngine()
    preprocessor = image_preprocessor or OpenCvImagePreprocessor()
    limits = intake_limits or IntakeLimits()

    # Rejects an over-limit request body at the ASGI stream boundary, before
    # FastAPI's multipart parser buffers/spools it -- api/body_size_limit.py.
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=limits.max_size_bytes)

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
        student_label: str | None = Form(None),
    ) -> SubmissionResponse:
        try:
            data = await _read_upload_within_limit(file, limits.max_size_bytes)
        except PdfTooLargeError as exc:
            raise HTTPException(
                _PDF_INTAKE_ERROR_STATUS[PdfTooLargeError], detail=str(exc)
            ) from exc
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            try:
                result = intake_submission(
                    uow,
                    store,
                    engine,
                    preprocessor,
                    test_id=test_id,
                    filename=file.filename or "",
                    declared_mime=file.content_type,
                    data=data,
                    student_label=student_label,
                    limits=limits,
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
        return _submission_response(result.submission, is_retry=result.is_retry)

    app.include_router(protected)
    return app


app = create_app()
