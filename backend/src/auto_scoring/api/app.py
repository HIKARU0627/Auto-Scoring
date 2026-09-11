"""FastAPI application factory for the sidecar."""

from __future__ import annotations

import atexit
import tempfile
import threading
from asyncio import to_thread
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring import __version__
from auto_scoring.adapters.ai.unconfigured_provider import UnconfiguredAIProvider
from auto_scoring.adapters.ai_classification.factory import create_material_classifier
from auto_scoring.adapters.ai_grading.factory import AIProviderConfigError, create_ai_provider
from auto_scoring.adapters.answer_area_detection.factory import (
    AnswerAreaDetectorConfigError,
    create_answer_area_detector,
)
from auto_scoring.adapters.credentials.api_keys import ApiKeySettings
from auto_scoring.adapters.credentials.store import UnavailableCredentialStore
from auto_scoring.adapters.criteria_extraction.extractor import UnconfiguredCriteriaExtractor
from auto_scoring.adapters.criteria_extraction.factory import (
    CriteriaExtractorConfigError,
    create_criteria_extractor,
)
from auto_scoring.adapters.data_root_lock import acquire_data_root_lock
from auto_scoring.adapters.image.opencv_preprocessor import OpenCvImagePreprocessor
from auto_scoring.adapters.in_memory_repository import InMemoryScoreRepository
from auto_scoring.adapters.local.grading_cost_store import GradingCostStore
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.ocr.factory import OCRProviderConfigError, create_ocr_provider
from auto_scoring.adapters.ocr.unconfigured_provider import UnconfiguredOCRProvider
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
from auto_scoring.api.ai_usage_router import build_ai_usage_router
from auto_scoring.api.auth import generate_token, require_token
from auto_scoring.api.body_size_limit import MaxBodySizeMiddleware
from auto_scoring.api.criteria_router import build_criteria_router
from auto_scoring.api.dependency_graph_router import build_dependency_graph_router
from auto_scoring.api.error_catalog_router import build_error_catalog_router
from auto_scoring.api.export_router import build_export_router
from auto_scoring.api.intake_router import ClassifierFactory, build_intake_router
from auto_scoring.api.jobs_router import build_jobs_router
from auto_scoring.api.page_image_router import build_page_image_router
from auto_scoring.api.recognitions_router import build_recognitions_router
from auto_scoring.api.review_router import build_review_router
from auto_scoring.api.secret_redaction import (
    SecretRegistry,
    configuration_secrets,
    redact,
)
from auto_scoring.api.settings_router import CredentialVerifier, build_settings_router
from auto_scoring.api.submission_upload_gate import SubmissionUploadGateMiddleware
from auto_scoring.api.test_artifact_lock import TestArtifactLocks
from auto_scoring.api.test_registration_router import build_test_registration_router
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url
from auto_scoring.db.migrator import upgrade
from auto_scoring.domain.ai_provider import AIProvider
from auto_scoring.domain.answer_area_detection import (
    AnswerAreaDetector,
    UnconfiguredAnswerAreaDetector,
)
from auto_scoring.domain.criteria_extraction import CriteriaExtractor
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


#: How `build_ai_provider` reaches the provider chain. Injected so a test can
#: state which world it is in -- by binding `create_ai_provider`'s own two
#: host probes (``executable_available``, ``token_source_factory``) before
#: passing it here -- instead of inheriting whatever this machine happens to
#: have installed. That is the rule docs/quality-gates.md records as
#: "ホストを見る判定はテストへ注入する".
AIProviderFactory = Callable[[Mapping[str, str]], AIProvider]

#: The `UnconfiguredAIProvider.reason` `create_app` falls back to when no
#: ``ai_provider`` was injected at all. Not reachable from the sidecar (which
#: always passes `build_ai_provider`'s result, configured or not); it is what
#: a test or a schema export gets, and it says so rather than claiming
#: something about this host's credentials.
_NO_PROVIDER_INJECTED = "no AI grading provider was supplied to create_app()"

#: The `UnconfiguredCriteriaExtractor.reason` `create_app` falls back to when
#: no ``criteria_extractor`` was injected. Same role, and the same wording
#: discipline, as `_NO_PROVIDER_INJECTED` above: it says what was not supplied
#: rather than claiming anything about this host.
_NO_EXTRACTOR_INJECTED = "no criteria extractor was supplied to create_app()"

#: How `build_ocr_provider` reaches the OCR adapter. Injected for the same
#: reason `AIProviderFactory` is: the real factory probes this host for ADC
#: credentials, and a test must be able to say which world it is in rather
#: than inherit the machine's.
OCRProviderFactory = Callable[[Mapping[str, str]], OCRProvider]

#: The `UnconfiguredOCRProvider.reason` `create_app` falls back to when no
#: ``ocr_provider`` was injected. Same role and wording discipline as
#: `_NO_PROVIDER_INJECTED`.
_NO_OCR_PROVIDER_INJECTED = "no OCR provider was supplied to create_app()"

#: What the settings endpoints report when no `ApiKeySettings` was injected.
#: Same role and wording discipline again, and the same reason for existing:
#: a default that reached for this host's real credential store would make
#: every test that builds an app -- and the schema export -- depend on
#: whether the machine running it has one (Issue #96).
_NO_CREDENTIAL_STORE_INJECTED = "no credential store was supplied to create_app()"


class OcrAvailabilityResponse(BaseModel):
    """Whether this sidecar can OCR at all, and if not, why (Issue #114).

    The counterpart of `GradingAvailabilityResponse`, and it exists for the
    same reason: without it, "usable=False" on a question is the same shape
    whether the OCR read the answer and was unsure or this machine has no
    OCR at all -- and those are different facts that call for different
    actions (Issue #114 acceptance 8).

    Unlike grading, ``available=False`` here does not stop anything: design
    section 24 has grading carry on without a reading. What is lost is
    stated in section 8.1.5 -- the cross-check against the grading AI's own
    reading, and text-anchored annotation positions -- so this is an
    "OCR is off, verification is weaker" notice, never a blocker.

    ``reason`` never contains a credential: it is
    `UnconfiguredOCRProvider.reason`, which names configuration variables and
    host prerequisites only (see `build_ocr_provider`).
    """

    available: bool
    reason: str | None = None


def build_ocr_provider(
    env: Mapping[str, str],
    *,
    factory: OCRProviderFactory = create_ocr_provider,
) -> OCRProvider:
    """Build the configured OCR provider, degrading to
    `UnconfiguredOCRProvider` instead of refusing to start (Issue #114).

    Exactly the shape of `build_ai_provider`, for a stronger version of its
    reason: a host with no OCR must not merely still import and export, it
    must still *grade and still release dependent questions*, because design
    section 24 says so outright ("OCR失敗: **採点は止めない。**"). The
    provider this returns raises `domain.ocr.OCRUnavailable` on every call,
    which `jobs.recognition_processor.RecognitionJobProcessor` turns into
    "no reading" rather than into a fabricated confidence of 0.0.

    Both failure paths keep configuration values out of the reason string,
    which is published by ``GET /ocr/availability`` and written to the
    sidecar log: `OCRProviderConfigError` is required to name variables only
    (`adapters.ocr.factory`'s module docstring), and anything else surfaces
    as its exception type alone, since an adapter constructing itself badly
    could put anything in its message. `redact` is the gate behind both, for
    the reason `build_ai_provider` states.
    """
    try:
        return factory(env)
    except OCRProviderConfigError as error:
        reason = str(error)
    except Exception as error:
        reason = f"building the OCR provider failed ({type(error).__name__}); see the sidecar log"
    return UnconfiguredOCRProvider(redact(reason, configuration_secrets(env)))


class GradingAvailabilityResponse(BaseModel):
    """Whether this sidecar can AI-grade at all, and if not, why (Issue #97).

    The app asks once per connection and keeps a banner above every screen
    while ``available`` is false. That banner is the whole point: without it,
    a host with no credentials still imports answers, still enqueues grading
    jobs, and the reviewer only ever sees each question fail -- with no way
    to tell "this machine cannot grade" apart from "the AI could not read
    this answer".

    ``reason`` never contains a credential: it is `UnconfiguredAIProvider.
    reason`, which names configuration variables and host prerequisites only
    (see `build_ai_provider`).
    """

    available: bool
    reason: str | None = None


def build_ai_provider(
    env: Mapping[str, str],
    *,
    factory: AIProviderFactory = create_ai_provider,
) -> AIProvider:
    """Build the configured provider chain, degrading to
    `UnconfiguredAIProvider` instead of refusing to start (Issue #97).

    `create_ai_provider` raises when this host has no usable credentials --
    correct for a batch job, wrong for the sidecar: importing answers,
    reviewing them and exporting annotated PDFs do not need a grading
    provider, and losing all three because one is missing would be a far
    worse failure than not grading. So the failure becomes a *state* the app
    can render (``GET /grading/availability``) rather than a crash, and the
    provider that state names raises on every `grade()` call so no question
    is ever silently recorded as "graded, 0点".

    Both failure paths keep configuration values out of the reason string,
    which is published by ``GET /grading/availability``, shown on screen, and
    written to the sidecar log:

    * `AIProviderConfigError` is required to name variables only, never
      quote their values -- stated in `adapters.ai_grading.factory`'s module
      docstring and enforced by the leak matrix in
      ``tests/test_grading_availability.py``. It was *not* true when this
      function was first written (review round 1, P2: an unparseable
      ``AUTO_SCORING_AI_GRADING_TEMPERATURE`` was echoed back verbatim, so a
      key pasted into the wrong variable was displayed and logged). Those
      messages predate there being any published channel at all; adding one
      is what made them a disclosure question, and the rule now lives with
      the messages rather than as an assumption made here.
    * Anything else is an adapter constructing itself unexpectedly badly. Its
      message could be anything (an httpx proxy URL with credentials in it,
      say), so only the exception *type* survives -- the same discipline
      `adapters.ai_grading._google_adc` applies to google-auth's own errors.
    """
    try:
        return factory(env)
    except AIProviderConfigError as error:
        reason = str(error)
    except Exception as error:
        reason = (
            f"building the AI grading provider failed ({type(error).__name__}); see the sidecar log"
        )
    # Scrubbed even though neither message above is supposed to contain a
    # value: this is the other half of `api.secret_redaction`'s gate (the log
    # filter is the first), and the point of a gate is that it does not
    # depend on every message upstream of it being written correctly. Round
    # 1's leak was precisely an upstream message that was not.
    return UnconfiguredAIProvider(redact(reason, configuration_secrets(env)))


def build_criteria_extractor(
    env: Mapping[str, str],
    *,
    factory: Callable[[Mapping[str, str]], CriteriaExtractor] = create_criteria_extractor,
) -> CriteriaExtractor:
    """Build the configured criteria extractor, degrading to
    `UnconfiguredCriteriaExtractor` instead of refusing to start (Issue #103).

    Exactly the shape of `build_ai_provider` above, for exactly its reason: a
    host with no image-capable transport can still import material, review a
    hand-entered 配点, and export -- and losing all of that because one
    optional call cannot be made would be a worse failure than not extracting.
    The extractor this returns raises on every `extract()`, so an unconfigured
    host gets a message it can act on instead of an empty result that looks
    like a document the model read and found nothing in.

    The reason string is published (the extract endpoint returns it and the
    app shows it), so the same two rules hold: `CriteriaExtractorConfigError`
    is required to name variables and never quote values, and any other
    exception contributes only its type name -- an adapter constructing itself
    badly could otherwise carry anything in its message. `redact` is the gate
    behind both, for the reason `build_ai_provider` states.
    """
    try:
        return factory(env)
    except CriteriaExtractorConfigError as error:
        reason = str(error)
    except Exception as error:
        reason = (
            f"building the criteria extractor failed ({type(error).__name__}); see the sidecar log"
        )
    return UnconfiguredCriteriaExtractor(redact(reason, configuration_secrets(env)))


#: How `build_answer_area_detector` reaches the detection adapter. Injected
#: for the same reason `AIProviderFactory` is: the real factory probes this
#: host for ADC credentials, and a test must be able to say which world it is
#: in rather than inherit the machine's.
AnswerAreaDetectorFactory = Callable[[Mapping[str, str]], AnswerAreaDetector]

#: What a caller that injected no detector gets. Not reachable from the
#: sidecar (which always passes `build_answer_area_detector`'s result); it is
#: what a test or a schema export sees, and it says so rather than claiming
#: anything about this host.
_NO_DETECTOR_INJECTED = "no answer-area detector was supplied to create_app()"


def build_answer_area_detector(
    env: Mapping[str, str],
    *,
    factory: AnswerAreaDetectorFactory = create_answer_area_detector,
) -> AnswerAreaDetector:
    """Build the configured detector, degrading to
    `UnconfiguredAnswerAreaDetector` instead of refusing to start (Issue #105).

    Same shape and same reasoning as `build_ai_provider`: a host with no
    image-capable provider must still be able to open the テスト設定 screen and
    draw answer areas by hand -- that is the documented fallback, not an
    error state -- so a missing provider becomes a reason the screen can show
    rather than a startup crash.

    Both failure paths keep configuration *values* out of the reason string,
    which is published by ``GET /tests/{id}/answer-layout`` and shown on
    screen: `AnswerAreaDetectorConfigError` is required to name variables
    only (`adapters.answer_area_detection.factory`'s module docstring), and
    anything else surfaces as its exception type alone, since an adapter
    constructing itself badly could put anything in its message.
    """
    try:
        return factory(env)
    except AnswerAreaDetectorConfigError as error:
        reason = str(error)
    except Exception as error:
        reason = f"could not build an answer-area detector: {type(error).__name__}"
    # `redact` is the same belt-and-braces gate Issue #103 put on its own
    # published reason: the factory is *required* not to quote a
    # configuration value, and this makes a lapse in that rule fail closed
    # rather than end up on screen and in the sidecar log.
    return UnconfiguredAnswerAreaDetector(redact(reason, configuration_secrets(env)))


def create_app(
    *,
    api_token: str | None = None,
    data_root: Path | None = None,
    session_factory: sessionmaker[Session] | None = None,
    pdf_engine: PdfEngine | None = None,
    pdfium_lock: threading.Lock | None = None,
    image_preprocessor: ImagePreprocessor | None = None,
    intake_limits: IntakeLimits | None = None,
    max_concurrent_uploads: int = 2,
    job_processor: JobProcessor | None = None,
    queue_settings: QueueSettings | None = None,
    clock: Clock | None = None,
    ocr_provider: OCRProvider | None = None,
    recognition_settings: RecognitionSettings | None = None,
    ai_provider: AIProvider | None = None,
    criteria_extractor: CriteriaExtractor | None = None,
    answer_area_detector: AnswerAreaDetector | None = None,
    grading_settings: GradingSettings | None = None,
    export_processor: JobProcessor | None = None,
    material_classifier_factory: ClassifierFactory | None = None,
    credential_settings: ApiKeySettings | None = None,
    secret_registry: SecretRegistry | None = None,
    credential_verifier: CredentialVerifier | None = None,
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

    ``material_classifier_factory`` supplies the intake router's AI
    classifier (Issue #101). Omitted, it reads the same provider
    configuration grading does; a test passes a fake so it never depends on
    what credentials the host happens to have (``AGENTS.md``: inject
    boundaries from outside the core).

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

    ``ocr_provider`` no longer defaults to a placeholder that answers
    (Issue #114). Google Document AI (business-rules-and-evaluation-data.md
    section 3 (A), Issue #81) now has an adapter, and this function is
    deliberately not the place that decides whether this host can reach it --
    for exactly the reason given for ``ai_provider`` below. The composition
    root (`auto_scoring.api.sidecar.run`) calls `build_ocr_provider` and
    passes the result in; omitting it yields an `UnconfiguredOCRProvider`
    that raises `domain.ocr.OCRUnavailable` on every call, which the
    recognition step treats as "no reading" (no `RecognitionResult` row, no
    OCR term in ``usable``) rather than as the fabricated ``confidence=0.0``
    the deleted ``NullOCRProvider`` used to persist. Whichever arrives is
    published by ``GET /ocr/availability`` (`OcrAvailabilityResponse`).

    ``ai_provider`` has no default either (Issue #97). Section 3 (B)'s
    fallback chain *is* implemented, and this function is deliberately not
    the place that decides whether this host can run it: reading `os.environ`
    (and, through it, probing for a `codex` executable and a `gcloud` login)
    here would make every test that builds an app inherit whatever the
    machine it runs on happens to have configured. The composition root --
    `auto_scoring.api.sidecar.run` -- calls `build_ai_provider` and passes
    the result in; omitting it yields an `UnconfiguredAIProvider` that raises
    on every call, so a caller who forgot cannot silently record fabricated
    grades. Whichever arrives is published by ``GET /grading/availability``
    (`GradingAvailabilityResponse`). All of these are ignored when
    ``job_processor`` is supplied directly.

    ``credential_settings``/``secret_registry``/``credential_verifier``
    configure the API-key settings endpoints (Issue #96). All three are
    injected for the reason ``ai_provider`` is: the real ones reach this
    host's OS credential store and, for the verifier, the network. Omitted,
    the screen reports that no credential store was supplied, saves are
    refused, and no request is ever made -- so a test that forgot to inject
    cannot silently keyring-write on a developer's machine or bill somebody
    for a live call.

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
    # Injectable so a test can observe *where* it is held: Issue #103's code
    # review found the criteria router rendering PDF pages outside it, which
    # no test could have caught while the lock was unreachable from outside
    # `create_app` (AGENTS.md "Architecture": inject boundaries from outside
    # the core). Production passes nothing and gets a fresh one, as before.
    pdfium_lock = pdfium_lock or threading.Lock()

    recognition_provider = ocr_provider or UnconfiguredOCRProvider(_NO_OCR_PROVIDER_INJECTED)
    # Published on `app.state` for the same reason as `ai_provider` below: it
    # is how a caller that built this app (`api.sidecar.run`, and its test)
    # can see what it actually got, without going through HTTP.
    app.state.ocr_provider = recognition_provider
    default_recognition_processor = RecognitionJobProcessor(
        session_factory,
        store,
        recognition_provider,
        settings=recognition_settings,
        clock=clock,
    )
    grading_provider = ai_provider or UnconfiguredAIProvider(_NO_PROVIDER_INJECTED)
    # Published on `app.state` for the same reason as `queue_service` below:
    # it is how a caller that built this app (`api.sidecar.run`, and its
    # test) can see what it actually got, without going through HTTP.
    app.state.ai_provider = grading_provider
    default_grading_processor = GradingJobProcessor(
        session_factory,
        store,
        default_recognition_processor,
        grading_provider,
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

    @protected.get("/grading/availability")
    def grading_availability() -> GradingAvailabilityResponse:
        """Whether AI grading is configured on this host (Issue #97).

        Behind the bearer token, unlike ``/healthz``: it reports on this
        installation's configuration, which is nobody's business but the
        app's -- and it is not a liveness probe, so nothing needs it before
        the handshake has been read.
        """
        if isinstance(grading_provider, UnconfiguredAIProvider):
            return GradingAvailabilityResponse(available=False, reason=grading_provider.reason)
        return GradingAvailabilityResponse(available=True)

    @protected.get("/ocr/availability")
    def ocr_availability() -> OcrAvailabilityResponse:
        """Whether OCR is configured on this host (Issue #114).

        Behind the bearer token for the same reason as
        ``/grading/availability``: it reports on this installation's
        configuration, and it is not a liveness probe.
        """
        if isinstance(recognition_provider, UnconfiguredOCRProvider):
            return OcrAvailabilityResponse(available=False, reason=recognition_provider.reason)
        return OcrAvailabilityResponse(available=True)

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
    # One lock namespace for both routers below: `/profile/confirm` and
    # `/criteria/confirm` rebuild the *same* Question/Rubric rows from the
    # same two artefacts, and a private registry per router would let them
    # interleave into a set missing one of the two (api.test_artifact_lock).
    test_artifact_locks = TestArtifactLocks()
    protected.include_router(build_error_catalog_router(session_factory, store))
    protected.include_router(
        build_test_registration_router(
            session_factory,
            store,
            engine,
            intake_limits=limits,
            pdfium_lock=pdfium_lock,
            locks=test_artifact_locks,
            answer_area_detector=(
                answer_area_detector or UnconfiguredAnswerAreaDetector(_NO_DETECTOR_INJECTED)
            ),
        )
    )
    protected.include_router(
        build_criteria_router(
            session_factory,
            store,
            engine,
            criteria_extractor or UnconfiguredCriteriaExtractor(_NO_EXTRACTOR_INJECTED),
            locks=test_artifact_locks,
            pdfium_lock=pdfium_lock,
        )
    )
    protected.include_router(
        build_intake_router(
            store,
            engine,
            # Built per request rather than once here: an operator who fixes
            # their credentials should not have to restart the app, and a
            # host with none is a normal state this router reports rather
            # than a startup failure (mirrors `build_ai_provider`'s reasoning
            # for grading).
            material_classifier_factory or create_material_classifier,
            intake_limits=limits,
            pdfium_lock=pdfium_lock,
        )
    )
    protected.include_router(
        build_settings_router(
            credential_settings
            or ApiKeySettings(
                UnavailableCredentialStore(_NO_CREDENTIAL_STORE_INJECTED), environment={}
            ),
            secret_registry=secret_registry or SecretRegistry(),
            verifier=credential_verifier,
        )
    )
    protected.include_router(
        build_page_image_router(session_factory, store, engine, pdfium_lock=pdfium_lock)
    )
    protected.include_router(build_recognitions_router(session_factory, store))
    protected.include_router(build_review_router(session_factory, store, queue_service))
    protected.include_router(build_export_router(session_factory, store, queue_service))
    protected.include_router(build_ai_usage_router(session_factory, GradingCostStore(store.root)))

    app.include_router(protected)
    return app
