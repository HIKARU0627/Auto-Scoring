"""Issue #25: the MVP's acceptance scenarios, run end to end in one pass.

Every layer already has its own tests -- registration
(`test_test_registration_api.py`), intake (`test_api_submissions.py`), the
queue (`test_job_queue.py`), recognition/grading
(`test_recognition_processor.py`, `test_grading_processor.py`), review
(`test_review_api.py`), export (`test_export_api.py`). What none of them
covers is the join: register a test, take in several answers, let the queue
recognize and grade them while a human reviews an earlier one, correct and
approve, export, and restart. Issue #25 asks for exactly that single pass, so
this module runs the *real* app -- `create_app` plus `TestClient` with its
lifespan started, so `JobQueueService`'s workers and the real
`GradingJobProcessor` run against real SQLite, a real `LocalFileStore`, real
PDF rendering and real OpenCV preprocessing -- and replaces only the two
things it must: the OCR and AI providers.

Those two are replaced because there is nothing yet to put behind them.
Which OCR service and which AI model the product uses are decisions A and B
in business-rules-and-evaluation-data.md section 3, both still the project
owner's, and no API key for either exists. Issue #25's own "検証の境界" says
the same: ordinary CI runs against dummy/recorded providers and stays
reproducible, while a live-provider run is a separately triggered job with
its own secret. Scripting every provider outcome before the queue starts also
keeps the run deterministic -- the correction Issue #50 (docs/job-queue.md)
arrived at after a test whose result depended on how far the workers got
before the test coroutine ran again.

Both scripts are keyed by the answer-area crop, because that is the only
thing either provider is given that differs between one student's answer and
another's. That is not a convenience: it *is* section 2 (2) -- no student
identifier, no filename, no submission id ever reaches a provider -- and
`test_no_student_identifying_data_reaches_either_provider` asserts it
directly against the payloads recorded here.

Deliberately not re-tested here: the per-layer details the modules above
already pin down. This module asserts the seams between them.

Names without a leading underscore are the ones
`poc/issue_25_queue_throughput/report.py` imports: that probe drives the same
app through the same endpoints, and reusing these is what keeps it from
growing a second, silently diverging copy of "register a test, upload an
answer, wait for its jobs". Everything else here is private to this module.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections.abc import Callable, Iterator
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageChops
from PIL.Image import Image as PilImage
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url
from auto_scoring.domain.ai_provider import (
    GradingAnnotationCandidate,
    GradingCriterionOutcome,
    GradingRequest,
    GradingResponse,
    ProviderDescriptor,
    ProviderServerError,
)
from auto_scoring.domain.annotation_layout import resolve_annotation_rect
from auto_scoring.domain.models import AnnotationKind, CriterionOutcome, JobState
from auto_scoring.domain.ocr import (
    BoundingBox,
    ConfidenceBand,
    OCRProvider,
    OcrResult,
    OCRTimeoutError,
    OcrToken,
)
from auto_scoring.domain.pdf_intake import IntakeLimits
from auto_scoring.jobs.grading_settings import GradingSettings
from auto_scoring.jobs.recognition_settings import RecognitionSettings
from auto_scoring.jobs.settings import QueueSettings
from tests.font_support import install_font_covering
from tests.support import make_job

_TOKEN = "e2e-acceptance-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}

#: Deliberately *not* `QueueSettings`' own default (4 since Issue #81,
#: business-rules-and-evaluation-data.md section 3 (E)): everything below
#: asserts the app honours whatever value it is *configured* with, never that
#: this particular number is the right one. **So nothing here exercises the
#: shipped default's saturation** -- with the cap at 2, the held calls prove
#: two-way overlap and no more (see tests/test_e2e_dag_parallelism.py's module
#: docstring for the same gap on the DAG side).
_MAX_CONCURRENCY = 2

#: The section 3 (C) default, injected rather than branched on: the scenarios
#: pick confidences *relative to this constant*, so they keep meaning as the
#: threshold is adjusted in operation (Issue #81 decided it stays a tunable
#: setting). Section 3.1 (C) forbids hard-coding a threshold into a decision.
_CONFIDENCE_THRESHOLD = 0.80
_ABOVE_THRESHOLD = 0.95
_BELOW_THRESHOLD = 0.40

#: The answer PDF has 2 pages, so question "2" really lives on its own page.
_ANSWER_PAGE_COUNT = 2

#: How long a held provider call waits before giving up (see
#: `ScriptedOCRProvider.hold`). Bounds only the failing path.
_HOLD_TIMEOUT_SECONDS = 20.0

#: Where the per-submission marker is drawn on each page, and the answer area
#: registered over it (normalized, origin top-left). Keeping the marker
#: inside the answer area is what makes each submission's crop -- and so each
#: provider payload -- distinguishable, exactly as a real handwritten answer
#: would be.
_MARKER_XY = (60, 700)
_ANSWER_AREA = (0.05, 0.10, 0.60, 0.25)
#: 点数配置領域 and コメント配置候補領域 (section 2 (7) / (6)) -- the export
#: assertions below look for the drawn score and comment in exactly these.
_SCORE_AREA = (0.70, 0.03, 0.90, 0.09)
_COMMENT_AREA = (0.05, 0.30, 0.90, 0.42)

#: What `ScriptedAIProvider.script` accepts for one call.
AIOutcome = GradingResponse | Exception | Callable[[GradingRequest], GradingResponse]

_DESCRIPTOR = ProviderDescriptor(
    provider="e2e-scripted-ai",
    model="e2e-scripted-model",
    version="test",
    prompt_version="v1",
    temperature=0.0,
    structured_output_mode="json_schema",
)

#: Every question in this module's fixture test, as (number, page_index).
QUESTIONS = (("1", 0), ("2", 1))


def _digest(image: bytes) -> str:
    return hashlib.sha256(image).hexdigest()


# --------------------------------------------------------------------------- #
# Scripted providers
# --------------------------------------------------------------------------- #
class ScriptedOCRProvider:
    """`OCRProvider` scripted per answer-area crop, recording what it was sent.

    Follows the module-local scripted-provider convention
    `test_grading_processor.py` and `test_recognition_processor.py` already
    use, rather than adding shared fixture machinery. Two differences: a
    whole submission's questions are processed in one run, so outcomes are
    keyed rather than single-shot; and the calls are made through
    `asyncio.to_thread`, so above a concurrency of 1 two of them really do
    overlap on two threads -- hence the lock and the observed-concurrency
    counters.
    """

    name = "e2e-scripted-ocr"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._scripts: dict[str, list[OcrResult | Exception]] = {}
        self._held: set[str] = set()
        self._release = threading.Event()
        self.received_images: list[bytes] = []
        self.concurrency = 0
        self.max_concurrency_seen = 0
        self.hold_timed_out = False

    def script(self, image: bytes, outcomes: list[OcrResult | Exception]) -> None:
        self._scripts.setdefault(_digest(image), []).extend(outcomes)

    def hold(self, *images: bytes) -> None:
        """Make recognition of ``images`` block until `release` is called.

        This is how a scenario pins work as genuinely *in flight* while the
        test does something else, instead of hoping the queue has not drained
        yet -- which it usually has, since a scripted provider returns
        immediately. Held calls give up after `_HOLD_TIMEOUT_SECONDS` and set
        `hold_timed_out`, so a run that never reaches them fails on its own
        assertions rather than hanging the suite.
        """
        with self._lock:
            self._held.update(_digest(image) for image in images)

    def release(self) -> None:
        self._release.set()

    def recognize(self, image: bytes, *, language: str = "ja") -> OcrResult:
        with self._lock:
            self.concurrency += 1
            self.max_concurrency_seen = max(self.max_concurrency_seen, self.concurrency)
            self.received_images.append(image)
            digest = _digest(image)
            queued = self._scripts.get(digest)
            outcome = queued.pop(0) if queued else None
            held = digest in self._held
        try:
            if held and not self._release.wait(timeout=_HOLD_TIMEOUT_SECONDS):
                self.hold_timed_out = True
            if outcome is None:
                return ocr_result(text=DEFAULT_ANSWER_TEXT, confidence=_ABOVE_THRESHOLD)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        finally:
            with self._lock:
                self.concurrency -= 1


class ScriptedAIProvider:
    """`AIProvider` scripted per answer-area crop, recording every request.

    The recorded `GradingRequest`s are the payloads that would have crossed
    the trust boundary to a cloud provider; the security assertions read them
    back verbatim.
    """

    name = "e2e-scripted-ai"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._scripts: dict[str, list[AIOutcome]] = {}
        self.requests: list[GradingRequest] = []
        self.concurrency = 0
        self.max_concurrency_seen = 0

    def script(self, image: bytes, outcomes: list[AIOutcome]) -> None:
        """Queue outcomes for the question whose crop is ``image``.

        An outcome may be a ready-made `GradingResponse`, an exception to
        raise, or -- most often -- a callable applied to the real
        `GradingRequest`. The callable form exists because a valid response
        has to echo the request's own ``question_id``, ``max_score`` and
        rubric criterion ids (`GradingJobProcessor` rejects one that does
        not), and a hand-built stub would drift from the fixture.
        """
        self._scripts.setdefault(_digest(image), []).extend(outcomes)

    def describe(self) -> ProviderDescriptor:
        return _DESCRIPTOR

    def grade(self, request: GradingRequest) -> GradingResponse:
        with self._lock:
            self.concurrency += 1
            self.max_concurrency_seen = max(self.max_concurrency_seen, self.concurrency)
            self.requests.append(request)
            queued = self._scripts.get(_digest(request.answer_image))
            outcome = queued.pop(0) if queued else None
        try:
            if outcome is None:
                return grading_response(request)
            if isinstance(outcome, Exception):
                raise outcome
            if callable(outcome):
                return outcome(request)
            return outcome
        finally:
            with self._lock:
                self.concurrency -= 1


#: The AI's own comment proposal. Named so an export assertion can state
#: "this one must *not* be on the page" -- the reviewer superseded it.
AI_COMMENT = "理由をもう一段くわしく書きましょう。"

#: The recognized answer text every scripted reading uses unless a scenario
#: needs its own. Also the string the logging assertion searches for -- it
#: has to be the *actual* answer body that flowed through the pipeline, not a
#: sentinel, for that assertion to mean anything (section 28).
DEFAULT_ANSWER_TEXT = "光合成は葉緑体で行われ、水と二酸化炭素からデンプンをつくる"


def ocr_result(*, text: str, confidence: float) -> OcrResult:
    return OcrResult(
        text=text,
        tokens=(
            OcrToken(
                text=text,
                bounding_box=BoundingBox(0.1, 0.1, 0.6, 0.1),
                confidence=confidence,
                band=(
                    ConfidenceBand.HIGH
                    if confidence >= _CONFIDENCE_THRESHOLD
                    else ConfidenceBand.LOW
                ),
            ),
        ),
        provider="e2e-scripted-ocr",
    )


def grading_response(
    request: GradingRequest,
    *,
    score: int | None = None,
    grading_confidence: float = _ABOVE_THRESHOLD,
    recognition_confidence: float = _ABOVE_THRESHOLD,
    annotations: tuple[GradingAnnotationCandidate, ...] = (),
    criterion_ids: tuple[str, ...] | None = None,
) -> GradingResponse:
    """A well-formed response for ``request``.

    Built from the request so the criterion ids always correspond 1:1 to the
    registered rubric -- `GradingJobProcessor` rejects a response whose
    criteria do not, and hand-written ids would silently drift as the fixture
    changes.

    ``criterion_ids`` overrides `_criterion_ids`' single-criterion default,
    which describes the rubric a `RUBRIC` *region* produces. A rubric built
    from a confirmed 採点基準 draft instead (Issue #103) has one criterion
    per extracted clause, so a caller on that path states its own ids --
    see `tests/test_e2e_intake_to_export.py`.
    """
    return GradingResponse(
        question_id=request.question_id,
        recognition_text=request.ocr_text,
        recognition_confidence=recognition_confidence,
        score=request.max_score - 1 if score is None else score,
        max_score=request.max_score,
        grading_confidence=grading_confidence,
        rationale="主旨は捉えているが、理由の記述がやや不足している。",
        comment=AI_COMMENT,
        criteria=tuple(
            GradingCriterionOutcome(
                criterion_id=criterion_id,
                outcome=CriterionOutcome.PASS,
                confidence=_ABOVE_THRESHOLD,
                rationale="観点を満たしている。",
            )
            for criterion_id in (criterion_ids or _criterion_ids(request))
        ),
        annotations=annotations,
        descriptor=_DESCRIPTOR,
        latency_seconds=0.01,
    )


def _criterion_ids(request: GradingRequest) -> tuple[str, ...]:
    """The rubric criterion ids `domain.test_registration.
    build_questions_and_rubrics` derives for a confirmed profile: one
    criterion per question, named after the question. The `GradingRequest`
    carries the rubric's *text* but not its ids, so a scripted response has
    to reconstruct them the same way registration did.
    """
    return (f"{request.question_id}:rubric:c1",)


# --------------------------------------------------------------------------- #
# Fixture PDFs
# --------------------------------------------------------------------------- #
def _registration_pdf() -> bytes:
    """The model-answer / marking-manual PDF. Text-free on purpose: automatic
    region detection then finds nothing and the reviewer supplies the regions
    by hand through `PUT /profile` -- the manual fallback path
    `test_test_registration_api.py` documents, and the one that does not need
    a CID font embedded into a hand-built PDF.

    Same page count as the answers: the profile's regions are drawn on *this*
    PDF, and `PUT /profile` rejects a region on a page the registered format
    does not have, so a question on page 2 needs a two-page format to be
    placed on.
    """
    return _pdf(pages=_ANSWER_PAGE_COUNT, marker=None)


def _answer_pdf(marker: str) -> bytes:
    """A student's answer PDF, carrying ``marker`` inside each page's
    registered answer area.

    Two submissions must differ: `intake_submission` rejects a second upload
    with the same content hash as a duplicate of the first (Issue #17), which
    is correct -- an identical PDF *is* the same answer. Drawing the marker
    inside the answer area rather than outside it also makes each
    submission's crop differ, which is what lets the scripted providers tell
    two students' answers apart. They have nothing else to go on, by design
    (section 2 (2)).
    """
    return _pdf(pages=_ANSWER_PAGE_COUNT, marker=marker)


def _pdf(*, pages: int, marker: str | None) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(595, 842))
    for page_number in range(1, pages + 1):
        if marker is not None:
            # ASCII only: this is a fixture marker standing in for
            # handwriting, and the built-in Helvetica face has no CJK
            # glyphs. What the pipeline "reads" out of it is the scripted
            # OCR text, which is Japanese.
            pdf.drawString(*_MARKER_XY, f"{marker}-p{page_number}")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# App / client
# --------------------------------------------------------------------------- #
@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "app-data"


@pytest.fixture
def ocr_provider() -> ScriptedOCRProvider:
    return ScriptedOCRProvider()


@pytest.fixture
def ai_provider() -> ScriptedAIProvider:
    return ScriptedAIProvider()


def build_app_client(
    data_root: Path,
    ocr_provider: OCRProvider,
    ai_provider: ScriptedAIProvider,
    *,
    max_concurrency: int = _MAX_CONCURRENCY,
) -> TestClient:
    """The real app, wired to the scripted providers.

    ``with TestClient(...)`` (never the bare form) is what actually starts the
    queue's workers -- `create_app`'s lifespan owns `JobQueueService.start`.

    ``initial_backoff_seconds`` is small because this app runs on the real
    `SystemClock`: a retry scenario would otherwise spend the default second
    of wall time waiting. It shortens a real delay the pipeline genuinely
    has; it is not a timeout being widened to make an assertion pass
    (docs/job-queue.md, Issue #50).

    ``max_concurrency`` is a parameter only so
    `poc/issue_25_queue_throughput/report.py` can sweep it; every test here
    uses the module default.
    """
    return TestClient(
        create_app(
            api_token=_TOKEN,
            data_root=data_root,
            intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
            ocr_provider=ocr_provider,
            ai_provider=ai_provider,
            recognition_settings=RecognitionSettings(confidence_threshold=_CONFIDENCE_THRESHOLD),
            grading_settings=GradingSettings(confidence_threshold=_CONFIDENCE_THRESHOLD),
            queue_settings=QueueSettings(
                max_concurrency=max_concurrency,
                max_attempts=2,
                initial_backoff_seconds=0.01,
                backoff_multiplier=2.0,
                max_backoff_seconds=0.05,
            ),
        )
    )


@pytest.fixture
def client(
    data_root: Path,
    ocr_provider: ScriptedOCRProvider,
    ai_provider: ScriptedAIProvider,
) -> Iterator[TestClient]:
    with build_app_client(data_root, ocr_provider, ai_provider) as test_client:
        yield test_client


def _session_factory(data_root: Path) -> sessionmaker[Session]:
    """A read-side handle on the database the app under test owns.

    Matches `test_test_registration_api.py`'s helper of the same name: the
    app is driven only through HTTP, and this is used purely to read back
    what it persisted (and, for the restart scenario, to stage the state a
    killed process would have left behind).
    """
    return build_session_factory(create_sqlite_engine(sqlite_url(data_root / "database.sqlite")))


# --------------------------------------------------------------------------- #
# Scenario 1: register a test and confirm its profile and DAG
# --------------------------------------------------------------------------- #
def _region(
    *,
    region_id: str,
    kind: str,
    label: str,
    page_index: int,
    bbox: tuple[float, float, float, float],
    text: str | None = None,
) -> dict[str, object]:
    x0, y0, x1, y1 = bbox
    return {
        "region_id": region_id,
        "kind": kind,
        "page_index": page_index,
        "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        "label": label,
        "confirmed": False,
        "text": text,
    }


def _regions_for(number: str, page_index: int) -> list[dict[str, object]]:
    """One question's worth of confirmed regions.

    All six kinds, because grading needs all of them: `GradingJobProcessor`
    refuses to call the provider at all without a registered model answer and
    a rubric (it must not have the AI invent either), the answer area is what
    intake crops, and the score area is where the score annotation lands on
    export.
    """
    x0, y0, x1, y1 = _ANSWER_AREA
    return [
        _region(
            region_id=f"question-{number}",
            kind="question",
            label=number,
            page_index=page_index,
            bbox=(0.05, 0.03, 0.60, 0.08),
            text=f"問{number}",
        ),
        _region(
            region_id=f"answer-{number}",
            kind="answer_area",
            label=number,
            page_index=page_index,
            bbox=(x0, y0, x1, y1),
        ),
        _region(
            region_id=f"score-{number}",
            kind="score",
            label=number,
            page_index=page_index,
            bbox=_SCORE_AREA,
            text="5点",
        ),
        _region(
            region_id=f"comment-{number}",
            kind="annotation_area",
            label=number,
            page_index=page_index,
            bbox=_COMMENT_AREA,
        ),
        _region(
            region_id=f"model-answer-{number}",
            kind="model_answer",
            label=number,
            page_index=page_index,
            bbox=(0.05, 0.50, 0.90, 0.60),
            text=f"問{number}の模範解答: 光合成のしくみを説明できている。",
        ),
        _region(
            region_id=f"rubric-{number}",
            kind="rubric",
            label=number,
            page_index=page_index,
            bbox=(0.05, 0.62, 0.90, 0.72),
            text=f"問{number}の採点基準: 主旨と理由の両方に触れていれば満点。",
        ),
    ]


def register_ready_test(
    client: TestClient,
    *,
    name: str = "理科 第1回",
    edges: list[dict[str, object]] | None = None,
) -> str:
    """Acceptance scenario 1, through the real endpoints.

    Register the criteria PDF (plus a reference PDF, which is what automatic
    candidate generation reads the page layout from), generate profile
    candidates, have the reviewer
    replace them with the confirmed regions, confirm the profile, then
    analyze and confirm the question dependency graph, and finally complete
    registration. Returns the test id, now `ready` -- which is the gate
    answer intake checks.
    """
    created = client.post(
        "/tests",
        headers=_AUTH,
        data={"name": name, "subject": "理科", "material_roles": ["reference"]},
        files=[
            ("criteria", ("02_criteria.pdf", _registration_pdf(), "application/pdf")),
            # Automatic candidate generation reads the *page layout* from a
            # model-answer-shaped document. Issue #101 made that optional, so
            # this scenario -- which goes on to call /profile/analyze --
            # registers one explicitly as a `reference` material.
            ("materials", ("reference.pdf", _registration_pdf(), "application/pdf")),
        ],
    )
    assert created.status_code == 201, created.text
    test_id: str = created.json()["id"]

    analyzed = client.post(f"/tests/{test_id}/profile/analyze", headers=_AUTH)
    assert analyzed.status_code == 200, analyzed.text
    # The registration PDFs carry no text, so nothing is auto-detected: this
    # is the human-correction step the scenario calls for, not a formality.
    assert analyzed.json()["regions"] == []

    regions: list[dict[str, object]] = []
    for number, page_index in QUESTIONS:
        regions.extend(_regions_for(number, page_index))
    updated = client.put(f"/tests/{test_id}/profile", headers=_AUTH, json={"regions": regions})
    assert updated.status_code == 200, updated.text

    revision = client.get(f"/tests/{test_id}/profile", headers=_AUTH).json()["revision"]
    confirmed = client.post(
        f"/tests/{test_id}/profile/confirm", headers=_AUTH, json={"revision": revision}
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"

    analyzed_graph = client.post(
        f"/tests/{test_id}/dependency-graph/analyze", headers=_AUTH, json={"overrides": []}
    )
    assert analyzed_graph.status_code == 200, analyzed_graph.text
    confirmed_graph = client.post(
        f"/tests/{test_id}/dependency-graph/confirm",
        headers=_AUTH,
        # No edges by default: the two questions are independent, which is
        # what lets the queue run them in parallel below. Dependent ordering
        # through the *fake* processor has its own coverage in
        # `test_e2e_dag_parallelism.py`; ``edges`` exists so a scenario can
        # drive a real dependency through this real stack instead
        # (`test_e2e_ocr_unavailable_chain.py`, Issue #114).
        json={"version": analyzed_graph.json()["version"], "edges": edges or []},
    )
    assert confirmed_graph.status_code == 200, confirmed_graph.text

    completed = client.post(f"/tests/{test_id}/complete-registration", headers=_AUTH)
    assert completed.status_code == 200, completed.text
    assert completed.json()["test"]["status"] == "ready"
    return test_id


# --------------------------------------------------------------------------- #
# Scenario 2 helpers: intake and the queue
# --------------------------------------------------------------------------- #
def upload_answer(
    client: TestClient, test_id: str, *, marker: str, student_label: str | None = None
) -> str:
    response = client.post(
        f"/tests/{test_id}/submissions",
        headers=_AUTH,
        data={} if student_label is None else {"student_label": student_label},
        files={"file": (f"{marker}.pdf", _answer_pdf(marker), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    submission_id: str = response.json()["id"]
    return submission_id


def answer_crops(data_root: Path, submission_id: str) -> dict[str, bytes]:
    """Each question's cropped answer image, as intake stored it.

    This is the byte string both providers will be handed for that question
    of that submission, so it is also the key the scripts are written
    against.
    """
    store_root = data_root
    crops: dict[str, bytes] = {}
    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        images = uow.answer_images.list_for_submission(submission_id)
    for image in images:
        crops[image.question_id] = (store_root / image.image_path).read_bytes()
    return crops


def start_jobs(client: TestClient, submission_id: str) -> list[dict[str, Any]]:
    response = client.post(f"/submissions/{submission_id}/jobs", headers=_AUTH)
    assert response.status_code == 200, response.text
    jobs: list[dict[str, Any]] = response.json()
    return jobs


def _jobs(client: TestClient, submission_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/submissions/{submission_id}/jobs", headers=_AUTH)
    assert response.status_code == 200, response.text
    listing: list[dict[str, Any]] = response.json()
    return listing


#: Retryable in `domain.retry_policy.is_retryable`'s sense -- the categories
#: the queue's backoff scheduler will requeue a FAILED job for.
_RETRYABLE_ERROR_CODES = {"timeout", "rate_limited", "server_error"}


def _is_settled(job: dict[str, Any]) -> bool:
    """Whether ``job`` has genuinely stopped moving.

    FAILED alone is not enough. A retryable failure with attempts left is a
    *transient* FAILED: the backoff scheduler will requeue it moments later.
    Treating it as final made this module's first draft read a job's state
    between its first failure and its automatic retry and call that the
    answer -- a race, and exactly the kind Issue #50 (docs/job-queue.md) is
    the record of. The condition here mirrors
    `domain.retry_policy.RetryPolicy.should_retry` instead, so it settles on
    the same rule the queue itself uses.
    """
    state = job["state"]
    if state in (JobState.SUCCEEDED.value, JobState.CANCELLED.value):
        return True
    if state != JobState.FAILED.value:
        return False
    if job["error_code"] not in _RETRYABLE_ERROR_CODES:
        return True
    return bool(job["attempts"] >= job["max_attempts"])


def wait_until_settled(
    client: TestClient, submission_id: str, *, timeout: float = 20.0
) -> list[dict[str, Any]]:
    """Poll until every one of ``submission_id``'s jobs has stopped moving.

    Real-time polling, like `test_export_api.py` and `test_jobs_api.py`: this
    app runs on the real `SystemClock` through a real `TestClient`, so there
    is no virtual clock to advance. The timeout only bounds how long a
    *failing* run takes to say so -- no passing assertion is decided by it
    (docs/job-queue.md's Issue #50 record).
    """
    deadline = time.monotonic() + timeout
    while True:
        listing = _jobs(client, submission_id)
        if listing and all(_is_settled(job) for job in listing):
            return listing
        if time.monotonic() > deadline:
            raise AssertionError(f"jobs for {submission_id} never settled: {listing}")
        time.sleep(0.01)


# --------------------------------------------------------------------------- #
# Scenarios 1 + 2
# --------------------------------------------------------------------------- #
def test_register_take_in_three_answers_and_process_them_while_reviewing(
    client: TestClient,
    data_root: Path,
    ocr_provider: ScriptedOCRProvider,
    ai_provider: ScriptedAIProvider,
) -> None:
    """Acceptance scenarios 1 and 2 in one pass.

    Register a test and confirm its profile and DAG by hand; take in three
    answers; process the first; then, with the other two pinned mid-flight
    inside the OCR provider, review the first one and check the sidecar keeps
    answering. Holding the later two is what makes "while reviewing" a fact
    rather than a hope: a scripted provider returns instantly, so a run that
    merely started everything at once would almost always have drained before
    the first review request went out, and would assert nothing.

    "UI が操作可能なまま" is stood in for by the sidecar staying responsive to
    review requests while the queue is working -- there is no UI in a backend
    test to operate. That substitution is recorded in docs/mvp-acceptance.md
    rather than left implicit here.
    """
    test_id = register_ready_test(client)
    first = upload_answer(client, test_id, marker="ans-a", student_label="A01")
    rest = [
        upload_answer(client, test_id, marker=marker, student_label=label)
        for marker, label in (("ans-b", "B02"), ("ans-c", None))
    ]

    start_jobs(client, first)
    wait_until_settled(client, first)

    for submission_id in rest:
        ocr_provider.hold(*answer_crops(data_root, submission_id).values())
    for submission_id in rest:
        start_jobs(client, submission_id)

    # Both worker slots are now occupied by held calls, so the queue is
    # demonstrably mid-flight for the whole review below.
    _wait_for(
        lambda: ocr_provider.concurrency == _MAX_CONCURRENCY,
        "the queue never reached the configured concurrency",
    )

    reviewed = 0
    for _ in range(5):
        assert client.get(f"/tests/{test_id}/questions", headers=_AUTH).status_code == 200
        assert client.get(f"/submissions/{first}/source-pdf", headers=_AUTH).status_code == 200
        for question_id in _question_ids(test_id):
            grades = client.get(
                f"/submissions/{first}/questions/{question_id}/grades", headers=_AUTH
            )
            assert grades.status_code == 200
            assert grades.json(), "the first answer was graded before the others started"
            reviewed += 1
        assert ocr_provider.concurrency == _MAX_CONCURRENCY, (
            "the held calls finished early -- the reads above no longer prove anything"
        )
    assert reviewed == 5 * len(QUESTIONS)

    ocr_provider.release()
    for submission_id in rest:
        wait_until_settled(client, submission_id)

    assert not ocr_provider.hold_timed_out
    for submission_id in [first, *rest]:
        states = {job["question_id"]: job["state"] for job in _jobs(client, submission_id)}
        assert set(states.values()) == {"succeeded"}, states
        assert len(states) == len(QUESTIONS)

    # Every question of every answer really was recognized and graded.
    assert len(ocr_provider.received_images) == 3 * len(QUESTIONS)
    assert len(ai_provider.requests) == 3 * len(QUESTIONS)

    # And never above the configured cap, measured on the provider calls
    # themselves -- the point at which a real external API's own limit
    # applies (section 3 (E): the value is a setting, the bound is not).
    assert ocr_provider.max_concurrency_seen <= _MAX_CONCURRENCY
    assert ai_provider.max_concurrency_seen <= _MAX_CONCURRENCY

    # The crops the providers were sent are the ones intake stored -- one per
    # question per submission, all distinct.
    stored = {
        digest
        for submission_id in [first, *rest]
        for digest in map(_digest, answer_crops(data_root, submission_id).values())
    }
    assert stored == {_digest(image) for image in ocr_provider.received_images}
    assert len(stored) == 3 * len(QUESTIONS)


def _question_ids(test_id: str) -> list[str]:
    """The ids `build_questions_and_rubrics` derives for this fixture's test."""
    return [f"{test_id}:{number}" for number, _ in QUESTIONS]


def _wait_for(predicate: Any, message: str, *, timeout: float = 20.0) -> None:
    """Poll ``predicate`` until it holds, or fail with ``message``.

    Same role as `wait_until_settled`'s own deadline: it bounds how long a
    failing run takes, never what a passing one asserts.
    """
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError(message)
        time.sleep(0.01)


def _one_answer(
    client: TestClient, data_root: Path, *, marker: str = "ans-a", label: str | None = "A01"
) -> tuple[str, str, dict[str, bytes]]:
    """Register the fixture test and take in one answer, without starting its
    jobs -- so a scenario can script the providers against the real crops
    first. Returns ``(test_id, submission_id, crops-by-question-id)``.
    """
    test_id = register_ready_test(client)
    submission_id = upload_answer(client, test_id, marker=marker, student_label=label)
    return test_id, submission_id, answer_crops(data_root, submission_id)


def _job_for(client: TestClient, submission_id: str, question_id: str) -> dict[str, Any]:
    matches = [job for job in _jobs(client, submission_id) if job["question_id"] == question_id]
    assert len(matches) == 1, f"expected one job for {question_id!r}, got {matches}"
    return matches[0]


# --------------------------------------------------------------------------- #
# Scenario 3: low confidence, OCR failure, AI failure, unplaceable annotation
# --------------------------------------------------------------------------- #
def test_a_low_confidence_reading_is_held_for_a_human_and_never_auto_confirmed(
    client: TestClient, data_root: Path, ocr_provider: ScriptedOCRProvider
) -> None:
    """The reading comes back below the configured threshold.

    The result is still persisted -- it is a *proposal*
    (simplified-design-specification.md section 19), and discarding it would
    leave the reviewer nothing to correct -- but it must be marked unusable,
    must stay ``source=ai``, and must not produce a `Review` of its own.
    Nothing here compares against a literal 0.80: the fixture threshold is
    injected and the scripted confidence is chosen relative to it
    (section 3.1 (C)).
    """
    test_id, submission_id, crops = _one_answer(client, data_root)
    low, high = _question_ids(test_id)
    ocr_provider.script(
        crops[low], [ocr_result(text="よく読み取れない答案", confidence=_BELOW_THRESHOLD)]
    )

    start_jobs(client, submission_id)
    wait_until_settled(client, submission_id)

    held = _job_for(client, submission_id, low)
    assert held["state"] == "succeeded"
    assert held["usable"] is False, "a below-threshold reading must not release anything"
    # The unaffected question is untouched: one uncertain reading does not
    # stall the rest of the answer.
    assert _job_for(client, submission_id, high)["usable"] is True

    grades = client.get(
        f"/submissions/{submission_id}/questions/{low}/grades", headers=_AUTH
    ).json()
    assert grades, "the proposal must be kept for the reviewer, not discarded"
    assert {grade["source"] for grade in grades} == {"ai"}
    reviews = client.get(
        f"/submissions/{submission_id}/questions/{low}/reviews", headers=_AUTH
    ).json()
    assert reviews == [], "nothing may be confirmed without a human"


def test_a_failing_ocr_provider_fails_the_job_and_a_human_retry_recovers_it(
    client: TestClient, data_root: Path, ocr_provider: ScriptedOCRProvider
) -> None:
    """OCR failure (section 24 "OCR失敗"): retried automatically to the
    configured attempt limit, then left FAILED with a classified reason for a
    human, who retries it explicitly once the cause is gone.
    """
    test_id, submission_id, crops = _one_answer(client, data_root)
    failing, _ = _question_ids(test_id)
    # max_attempts=2 in this fixture, so two scripted timeouts exhaust the
    # automatic retries and the third call -- the human's -- succeeds.
    ocr_provider.script(crops[failing], [OCRTimeoutError(), OCRTimeoutError()])

    start_jobs(client, submission_id)
    wait_until_settled(client, submission_id)

    failed = _job_for(client, submission_id, failing)
    assert failed["state"] == "failed"
    assert failed["error_code"] == "timeout"
    assert failed["attempts"] == 2

    retried = client.post(f"/jobs/{failed['id']}/retry", headers=_AUTH)
    assert retried.status_code == 200, retried.text
    wait_until_settled(client, submission_id)

    recovered = _job_for(client, submission_id, failing)
    assert recovered["state"] == "succeeded"
    assert recovered["usable"] is True


def test_a_failing_ai_provider_fails_the_job_with_its_own_classified_reason(
    client: TestClient, data_root: Path, ai_provider: ScriptedAIProvider
) -> None:
    """AI failure (section 24 "AI API失敗"), classified separately from an OCR
    failure so the queue's retry rules and the reviewer see the real cause.
    """
    test_id, submission_id, crops = _one_answer(client, data_root)
    failing, _ = _question_ids(test_id)
    ai_provider.script(crops[failing], [ProviderServerError(), ProviderServerError()])

    start_jobs(client, submission_id)
    wait_until_settled(client, submission_id)

    failed = _job_for(client, submission_id, failing)
    assert failed["state"] == "failed"
    assert failed["error_code"] == "server_error"
    # The message the reviewer and the log see carries no answer text.
    assert DEFAULT_ANSWER_TEXT not in (failed["last_error"] or "")

    retried = client.post(f"/jobs/{failed['id']}/retry", headers=_AUTH)
    assert retried.status_code == 200, retried.text
    wait_until_settled(client, submission_id)
    assert _job_for(client, submission_id, failing)["state"] == "succeeded"


def test_an_annotation_whose_target_text_is_not_on_the_page_falls_back_to_the_comment_area(
    client: TestClient, data_root: Path, ai_provider: ScriptedAIProvider
) -> None:
    """Annotation position unknown (section 12.4).

    The AI proposes underlining a phrase, but names one the OCR never read.
    The annotation is still recorded -- with its ``anchor_text`` and no rect,
    since the AI never supplies coordinates (section 12.1) -- and
    `resolve_annotation_rect` declines to place it, which is the signal for
    the caller's comment-area fallback. The reviewer then places it by hand
    through the edit endpoint, which is the "手動修正" half of the scenario.
    """
    test_id, submission_id, crops = _one_answer(client, data_root)
    question_id, _ = _question_ids(test_id)
    unreadable_target = "この語はOCR結果に存在しない"

    def _with_unplaceable_annotation(request: GradingRequest) -> GradingResponse:
        return grading_response(
            request,
            annotations=(
                GradingAnnotationCandidate(
                    target=unreadable_target,
                    type=AnnotationKind.UNDERLINE,
                    comment="ここは根拠が不足しています。",
                ),
            ),
        )

    ai_provider.script(crops[question_id], [_with_unplaceable_annotation])

    start_jobs(client, submission_id)
    wait_until_settled(client, submission_id)

    annotations = client.get(
        f"/submissions/{submission_id}/questions/{question_id}/annotations", headers=_AUTH
    ).json()
    proposed = [a for a in annotations if a["anchor_text"] == unreadable_target]
    assert len(proposed) == 1
    assert proposed[0]["rect"] is None

    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        question = uow.questions.get(question_id)
        assert question is not None
        stored = uow.annotations.list_for(submission_id, question_id)
        recognitions = uow.recognitions.history(submission_id, question_id)
        unplaceable = next(a for a in stored if a.anchor_text == unreadable_target)
        assert (
            resolve_annotation_rect(unplaceable, question=question, recognitions=recognitions)
            is None
        ), "an unmatched anchor on a non-fixed kind must stay unplaced (section 12.4)"
        assert question.comment_area is not None, "the fallback area itself must exist"

    # The reviewer places it explicitly; the edit is recorded as a human row.
    version = len(
        client.get(
            f"/submissions/{submission_id}/questions/{question_id}/reviews", headers=_AUTH
        ).json()
    )
    edited = client.post(
        f"/submissions/{submission_id}/questions/{question_id}/review/edit",
        headers=_AUTH,
        json={
            "expected_version": version,
            "score_awarded": 4,
            "score_maximum": 5,
            "criteria": [
                {"criterion_id": f"{question_id}:rubric:c1", "outcome": "pass"},
            ],
            "annotations": [
                {
                    "kind": "underline",
                    "x": 0.1,
                    "y": 0.2,
                    "width": 0.3,
                    "height": 0.03,
                    "comment": "ここは根拠が不足しています。",
                }
            ],
        },
    )
    assert edited.status_code == 201, edited.text
    placed = edited.json()["annotations"][0]
    # The reviewer's own coordinates, not merely "some rect is set now".
    assert placed["rect"] == {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.03}
    assert placed["source"] == "human"


# --------------------------------------------------------------------------- #
# Scenario 4: correct, approve, and undo -- with the history behind it
# --------------------------------------------------------------------------- #
def _review_version(client: TestClient, submission_id: str, question_id: str) -> int:
    history = client.get(
        f"/submissions/{submission_id}/questions/{question_id}/reviews", headers=_AUTH
    )
    assert history.status_code == 200, history.text
    return len(history.json())


#: The reviewer's own comment. Deliberately different from the AI's
#: (`grading_response`'s "理由をもう一段くわしく書きましょう。") so an export
#: assertion can tell "drew the confirmed text" from "drew whatever comment
#: it found first".
CONFIRMED_COMMENT = "根拠の書き方がよくなりました。"


def _confirm_question(
    client: TestClient,
    submission_id: str,
    question_id: str,
    *,
    annotations: list[dict[str, object]] | None = None,
    score_awarded: int = 5,
) -> dict[str, Any]:
    """One reviewer's confirmation of one question, through `review/edit`.

    Uses ``edit`` rather than ``approve`` because the acceptance scenario is
    about *correcting* the AI's proposal -- recognized text, score, comment
    and marks -- and then having that correction confirmed.
    """
    payload: dict[str, object] = {
        "expected_version": _review_version(client, submission_id, question_id),
        "score_awarded": score_awarded,
        "score_maximum": 5,
        "comment": CONFIRMED_COMMENT,
        "recognized_text": "光合成は葉緑体で行われ、水と二酸化炭素からデンプンをつくる",
        "criteria": [{"criterion_id": f"{question_id}:rubric:c1", "outcome": "pass"}],
    }
    if annotations is not None:
        payload["annotations"] = annotations
    response = client.post(
        f"/submissions/{submission_id}/questions/{question_id}/review/edit",
        headers=_AUTH,
        json=payload,
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_correcting_approving_and_undoing_leaves_a_complete_history(
    client: TestClient, data_root: Path
) -> None:
    """Acceptance scenario 4.

    The reviewer corrects the AI's recognized text, score and comment,
    approves the next question, then undoes the correction. Every step is an
    appended row -- the undo included -- so the history is a record of what
    happened, not the current state pretending to be one (section 19).
    """
    test_id, submission_id, _ = _one_answer(client, data_root)
    corrected, approved = _question_ids(test_id)
    start_jobs(client, submission_id)
    wait_until_settled(client, submission_id)

    ai_grades = client.get(
        f"/submissions/{submission_id}/questions/{corrected}/grades", headers=_AUTH
    ).json()
    assert [grade["source"] for grade in ai_grades] == ["ai"]
    ai_score = ai_grades[0]["score"]["awarded"]

    edited = _confirm_question(client, submission_id, corrected)
    assert edited["review"]["action"] == "modified"
    assert edited["grade"]["source"] == "human"
    assert edited["grade"]["score"]["awarded"] == 5 != ai_score
    # `RecognitionResponseSlim` carries no `source` -- an edit's recognition
    # row is human by construction -- so the history endpoint is where that
    # shows up alongside the AI's own readings.
    readings = client.get(
        f"/submissions/{submission_id}/questions/{corrected}/recognitions", headers=_AUTH
    ).json()
    human = [row for row in readings if row["source"] == "human"]
    assert [row["id"] for row in human] == [edited["recognition"]["id"]]

    approval = client.post(
        f"/submissions/{submission_id}/questions/{approved}/review/approve",
        headers=_AUTH,
        json={"expected_version": _review_version(client, submission_id, approved)},
    )
    assert approval.status_code == 201, approval.text
    assert approval.json()["review"]["action"] == "approved"

    undone = client.post(
        f"/submissions/{submission_id}/questions/{corrected}/review/undo",
        headers=_AUTH,
        json={"expected_version": _review_version(client, submission_id, corrected)},
    )
    assert undone.status_code == 201, undone.text
    assert undone.json()["review"]["action"] == "undone"

    history = client.get(
        f"/submissions/{submission_id}/questions/{corrected}/reviews", headers=_AUTH
    ).json()
    assert [row["action"] for row in history] == ["modified", "undone"]
    assert [row["version"] for row in history] == [1, 2]
    # The corrected grade row itself is still there -- undo appends, it does
    # not delete -- so the history stays auditable.
    after_undo = client.get(
        f"/submissions/{submission_id}/questions/{corrected}/grades", headers=_AUTH
    ).json()
    assert {grade["source"] for grade in after_undo} == {"ai", "human"}


# --------------------------------------------------------------------------- #
# Scenario 5: export, without touching the original
# --------------------------------------------------------------------------- #
#: Where `_circle_annotation` puts its ○, as (x0, y0, x1, y1).
_CIRCLE_AREA = (0.70, 0.05, 0.78, 0.10)


def _circle_annotation() -> list[dict[str, object]]:
    """A ○ mark with an explicit rect and no text.

    A shape rather than text, deliberately: a ○ needs no glyphs, so this
    scenario -- a new file is produced, the original is untouched, the
    confirmed mark is on the page -- holds on any machine regardless of
    which fonts it has. The text-bearing half is asserted separately by
    `test_the_exported_pdf_carries_the_reviewed_comment_text` and
    `test_the_exported_pdf_carries_the_reviewed_score` below, which each
    need a font carrying the glyphs they draw.
    """
    x0, y0, x1, y1 = _CIRCLE_AREA
    return [{"kind": "circle", "x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}]


def _export(client: TestClient, submission_id: str) -> dict[str, Any]:
    """Queue an export, wait for it, and return *this* export's record.

    Selected by ``job_id`` rather than by taking the only entry: a re-export
    after the review state has genuinely moved on leaves the earlier export
    in place (docs/pdf-export.md section 5), and the score assertion below
    depends on comparing exactly those two.
    """
    response = client.post(f"/submissions/{submission_id}/export", headers=_AUTH)
    assert response.status_code == 202, response.text
    body: dict[str, Any] = response.json()
    job_id = body["job_id"]
    _wait_for(
        lambda: client.get(f"/jobs/{job_id}", headers=_AUTH).json()["state"] == "succeeded",
        f"export job {job_id} never succeeded",
    )
    exports = client.get(f"/submissions/{submission_id}/exports", headers=_AUTH).json()
    matches = [export for export in exports if export["job_id"] == job_id]
    assert len(matches) == 1, f"expected one export for job {job_id}, got {exports}"
    exported: dict[str, Any] = matches[0]
    return exported


def _reviewed_answer(
    client: TestClient, data_root: Path, *, annotations: list[dict[str, object]]
) -> tuple[str, str]:
    test_id, submission_id, _ = _one_answer(client, data_root)
    start_jobs(client, submission_id)
    wait_until_settled(client, submission_id)
    for question_id in _question_ids(test_id):
        _confirm_question(client, submission_id, question_id, annotations=annotations)
    return test_id, submission_id


def test_exporting_a_fully_reviewed_answer_never_touches_the_original_pdf(
    client: TestClient, data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance scenario 5, and section 2 (15)'s hardest rule: the original
    answer PDF is never written to, replaced, or deleted.

    Checked by hashing the stored original before the export and again
    afterwards, and by confirming the export landed on a different path.
    """
    _, submission_id = _reviewed_answer(client, data_root, annotations=_circle_annotation())
    # Since Issue #120 every export draws the confirmed score, so one really
    # has to be drawable here -- digits and a slash
    # (`domain.pdf_export._score_text`).
    install_font_covering(monkeypatch, "0123456789/")
    source = data_root / "submissions" / submission_id / "source.pdf"
    assert source.exists(), source
    before = _digest(source.read_bytes())

    exported = _export(client, submission_id)

    output = data_root / exported["file_path"]
    assert output != source
    assert output.name == "ans-a_corrected.pdf"
    assert _digest(source.read_bytes()) == before, "the original PDF was modified"

    # The output is a real, separately-generated PDF of this answer -- not a
    # copy of the original under a new name, which every check above would
    # otherwise have accepted (round 1 review made the same point about the
    # text-bearing export test). The ○ the reviewer confirmed is drawn where
    # they placed it, and the original page is blank in exactly that spot.
    assert _digest(output.read_bytes()) != before
    assert PdfReader(str(output)).pages.__len__() == _ANSWER_PAGE_COUNT
    assert not _has_ink(_region_crop(source, 0, _CIRCLE_AREA))
    assert _has_ink(_region_crop(output, 0, _CIRCLE_AREA)), "the confirmed ○ was not drawn"


def test_export_is_refused_while_any_question_is_still_unconfirmed(
    client: TestClient, data_root: Path
) -> None:
    """The other half of scenario 5: "全設問確認後に" is a precondition, not
    a suggestion. An export attempted with a question still unreviewed is
    refused, and names what is missing.
    """
    test_id, submission_id, _ = _one_answer(client, data_root)
    start_jobs(client, submission_id)
    wait_until_settled(client, submission_id)
    first, second = _question_ids(test_id)
    _confirm_question(client, submission_id, first, annotations=_circle_annotation())

    refused = client.post(f"/submissions/{submission_id}/export", headers=_AUTH)

    assert refused.status_code == 409
    assert refused.json()["detail"]["question_ids"] == [second]


def _page_text(pdf_path: Path, page_index: int) -> str:
    return PdfReader(str(pdf_path)).pages[page_index].extract_text()


def _region_crop(
    pdf_path: Path, page_index: int, area: tuple[float, float, float, float]
) -> PilImage:
    """The rendered pixels inside ``area`` (normalized ``x0, y0, x1, y1``).

    Rasterizing through the same `PdfiumPypdfEngine` the export used is the
    methodology `test_pdf_annotation_rendering.py` established for "was this
    mark really drawn here" -- reused rather than reinvented. Needed for
    marks that carry no text (a ○ has no glyphs to extract), and independent
    of which font the machine happens to have.
    """
    png = PdfiumPypdfEngine().render_page_png(pdf_path, page_index, scale=2.0)
    with Image.open(BytesIO(png)) as image:
        rgb = image.convert("RGB")
    x0, y0, x1, y1 = area
    width, height = rgb.size
    return rgb.crop((int(x0 * width), int(y0 * height), int(x1 * width), int(y1 * height)))


def _has_ink(crop: PilImage) -> bool:
    """Whether anything was drawn in ``crop`` -- i.e. it is not blank paper.

    `ImageChops.invert(...).getbbox()` is ``None`` for a wholly white
    region, the same "is there a bounding box of non-background pixels" test
    `test_pdf_annotation_rendering.py._redness_bbox` uses.
    """
    return ImageChops.invert(crop.convert("L")).getbbox() is not None


def test_the_exported_pdf_carries_the_reviewed_comment_text(
    client: TestClient, data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One half of scenario 5's text output: the comment on the page is the
    one the *reviewer* confirmed, not the AI's proposal and not nothing.

    Read straight out of the output's text layer. The earlier version of this
    test asserted only that the file existed and was non-empty, which an
    exporter that copied the source verbatim would also have satisfied
    (round 1 review) -- hence the third assertion below, which pins that the
    source really has no such text to copy.
    """
    install_font_covering(monkeypatch, CONFIRMED_COMMENT)
    _, submission_id = _reviewed_answer(
        client,
        data_root,
        annotations=[
            {
                "kind": "comment",
                "x": 0.05,
                "y": 0.30,
                "width": 0.85,
                "height": 0.12,
                "comment": CONFIRMED_COMMENT,
            }
        ],
    )

    exported = _export(client, submission_id)

    output = data_root / exported["file_path"]
    text = _page_text(output, 0)
    assert CONFIRMED_COMMENT in text, f"confirmed comment missing from the export: {text!r}"
    # The AI's own comment was superseded by the reviewer's edit. An exporter
    # drawing whatever comment it found first would still pass without this.
    assert AI_COMMENT not in text
    # And the source has nothing of the sort to have been copied from.
    assert CONFIRMED_COMMENT not in _page_text(
        data_root / "submissions" / submission_id / "source.pdf", 0
    )


#: The comment attached to a *shape* annotation, whose text the export used
#: to throw away entirely (Issue #141).
CROSS_COMMENT = "計算の途中が誤っています。"


def test_the_exported_pdf_carries_a_shape_annotation_s_comment_as_well(
    client: TestClient, data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #141: a ``×`` explains nothing on its own.

    `PdfEngine.render_annotations` renders a mark's text only for the SCORE
    and COMMENT kinds, so the explanation handed to a CROSS mark was dropped
    by the engine without a word: the live re-verification produced fourteen
    annotations and not one character of their comments reached any page. The
    comment now goes to the question's margin band instead of to the shape.
    """
    install_font_covering(monkeypatch, CROSS_COMMENT + "×")
    _, submission_id = _reviewed_answer(
        client,
        data_root,
        annotations=[
            {
                "kind": "cross",
                "x": 0.20,
                "y": 0.30,
                "width": 0.15,
                "height": 0.04,
                "comment": CROSS_COMMENT,
            }
        ],
    )

    exported = _export(client, submission_id)

    text = _page_text(data_root / exported["file_path"], 0)
    assert CROSS_COMMENT in text, f"the cross's comment is missing from the export: {text!r}"
    # And the source has nothing of the sort to have been copied from.
    assert CROSS_COMMENT not in _page_text(
        data_root / "submissions" / submission_id / "source.pdf", 0
    )


def test_the_exported_pdf_carries_the_reviewed_score(
    client: TestClient, data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half: the score drawn in the 点数配置領域 is the confirmed
    one, and it follows the reviewer when they change it.

    Split from the comment test because the two need different glyphs, and no
    single font on a stock Linux image covers both (see `tests/font_support.py`).
    Splitting is what lets each half actually run outside Windows rather than
    both being skipped.
    """
    install_font_covering(monkeypatch, "0123456789/")
    score_annotation = [{"kind": "score", "x": 0.70, "y": 0.03, "width": 0.20, "height": 0.06}]
    test_id, submission_id = _reviewed_answer(client, data_root, annotations=score_annotation)

    exported = _export(client, submission_id)

    first = _page_text(data_root / exported["file_path"], 0)
    assert "5/5" in first, f"the confirmed score is not on the exported page: {first!r}"

    # Re-confirm the same answer at a different score. The re-export must
    # carry the new one -- and not the old one, which is what distinguishes
    # "draws the confirmed score" from "draws some score".
    for question_id in _question_ids(test_id):
        _confirm_question(
            client, submission_id, question_id, annotations=score_annotation, score_awarded=2
        )
    regraded = _export(client, submission_id)

    second = _page_text(data_root / regraded["file_path"], 0)
    assert "2/5" in second, f"the re-confirmed score is not on the re-exported page: {second!r}"
    assert "5/5" not in second


# --------------------------------------------------------------------------- #
# Scenario 6: restart, and recovery from an abnormally terminated sidecar
# --------------------------------------------------------------------------- #
def test_job_and_review_state_survive_an_app_restart(
    data_root: Path,
    ocr_provider: ScriptedOCRProvider,
    ai_provider: ScriptedAIProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance scenario 6, first half: a clean restart.

    A second `create_app` against the same ``data_root`` is a real restart --
    new engine, new migrations check, new startup repair sweep, new queue --
    which is why the first client is closed first (its lifespan releases the
    data-root lock the second one has to take).
    """
    with build_app_client(data_root, ocr_provider, ai_provider) as client:
        test_id, submission_id, _ = _one_answer(client, data_root)
        first, second = _question_ids(test_id)
        start_jobs(client, submission_id)
        wait_until_settled(client, submission_id)
        _confirm_question(client, submission_id, first, annotations=_circle_annotation())
        before_jobs = {job["question_id"]: job["state"] for job in _jobs(client, submission_id)}

    with build_app_client(data_root, ocr_provider, ai_provider) as restarted:
        assert {
            job["question_id"]: job["state"] for job in _jobs(restarted, submission_id)
        } == before_jobs
        history = restarted.get(
            f"/submissions/{submission_id}/questions/{first}/reviews", headers=_AUTH
        ).json()
        assert [row["action"] for row in history] == ["modified"]
        grades = restarted.get(
            f"/submissions/{submission_id}/questions/{first}/grades", headers=_AUTH
        ).json()
        assert {grade["source"] for grade in grades} == {"ai", "human"}

        # And the restarted app can carry the work forward from where the
        # reviewer left off, not merely display it.
        _confirm_question(restarted, submission_id, second, annotations=_circle_annotation())
        # Since Issue #120 the export also draws the confirmed score.
        install_font_covering(monkeypatch, "0123456789/")
        exported = _export(restarted, submission_id)
        carried = data_root / exported["file_path"]
        # A real export produced *after* the restart -- the ○ confirmed
        # before it and the one confirmed after are both on the page.
        assert _has_ink(_region_crop(carried, 0, _CIRCLE_AREA))
        assert _has_ink(_region_crop(carried, 1, _CIRCLE_AREA))


def test_a_job_left_running_by_a_killed_sidecar_is_recovered_on_the_next_start(
    data_root: Path,
    ocr_provider: ScriptedOCRProvider,
    ai_provider: ScriptedAIProvider,
) -> None:
    """Acceptance scenario 6, second half: the sidecar dies mid-job.

    A killed process leaves exactly one trace: a ``jobs`` row still reading
    RUNNING, with its interrupted attempt already counted, and no task
    anywhere still working on it. That row is written here directly, while no
    app is running -- the same shape `domain.job_scheduling.recover_running_job`
    is specified against. Staging it this way rather than trying to kill a
    `TestClient` mid-flight is deliberate: `JobQueueService.shutdown` is a
    *graceful* stop that waits for in-flight jobs by design, so no amount of
    driving it produces the state a real kill leaves.
    """
    with build_app_client(data_root, ocr_provider, ai_provider) as client:
        test_id, submission_id, _ = _one_answer(client, data_root)
        question_ids = _question_ids(test_id)

    interrupted = "job-interrupted-by-kill"
    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        graph = uow.dependency_graphs.get_latest_confirmed(test_id)
        assert graph is not None
        for index, question_id in enumerate(question_ids):
            uow.jobs.add(
                make_job(
                    id=interrupted if index == 0 else f"job-queued-{index}",
                    submission_id=submission_id,
                    question_id=question_id,
                    dependency_graph_version=graph.version,
                    # The killed one was mid-attempt; the other never started.
                    state=JobState.RUNNING if index == 0 else JobState.QUEUED,
                    attempts=1 if index == 0 else 0,
                )
            )
        uow.commit()

    with build_app_client(data_root, ocr_provider, ai_provider) as restarted:
        settled = wait_until_settled(restarted, submission_id)

    states = {job["id"]: job["state"] for job in settled}
    assert states[interrupted] == "succeeded"
    assert set(states.values()) == {"succeeded"}
    # Recovered, not restarted from scratch: the interrupted attempt still
    # counts, so the recovered job succeeded on its *second* attempt.
    recovered = next(job for job in settled if job["id"] == interrupted)
    assert recovered["attempts"] == 2
    # And exactly once -- recovery must not double-process.
    assert len(ocr_provider.received_images) == len(question_ids)


# --------------------------------------------------------------------------- #
# Security (Issue #25: 外部送信・ログ・artifact)
# --------------------------------------------------------------------------- #
#: What "生徒識別情報" means for the payload assertion below. Recorded here
#: and in docs/mvp-acceptance.md because business-rules-and-evaluation-data.md
#: section 2 (2) names the categories (氏名・生徒ID・出席番号・学校名・答案
#: ファイル名) but a test needs the concrete values this run actually used.
_STUDENT_LABEL = "3年B組 山田太郎"
_ANSWER_FILENAME_MARKER = "ans-secret"


def test_no_student_identifying_data_reaches_either_provider(
    client: TestClient,
    data_root: Path,
    ocr_provider: ScriptedOCRProvider,
    ai_provider: ScriptedAIProvider,
) -> None:
    """Section 2 (2): a cloud payload carries one question's material and no
    student identity at all.

    Asserted against the payloads actually recorded during a real run, not
    against the type definitions -- `GradingRequest` has no field for a
    student label, but a caller could still smuggle one into ``prompt_text``
    or ``rubric_text``, and the OCR provider is handed raw bytes with no
    schema to stop it being a whole page.
    """
    test_id = register_ready_test(client)
    submission_id = upload_answer(
        client, test_id, marker=_ANSWER_FILENAME_MARKER, student_label=_STUDENT_LABEL
    )
    start_jobs(client, submission_id)
    wait_until_settled(client, submission_id)
    assert ai_provider.requests, "nothing was sent, so nothing was proved"

    # Section 2 (2)'s list is about the student -- name, student id, seat
    # number, school, answer filename -- plus the per-student
    # `submissionId` those map onto internally.
    #
    # The test id used to be excluded here, on the grounds that the question
    # and rubric criterion ids the request had to carry were built from it.
    # Since Issue #117 no identifier is sent at all (a criterion is a
    # position in the numbered rubric, and there is no question id on the
    # wire), so the test id has nothing left to ride in on and is asserted
    # absent like the rest. It is still not *student* data; this is simply
    # a payload that no longer needs it.
    forbidden = [_STUDENT_LABEL, submission_id, _ANSWER_FILENAME_MARKER, test_id]
    for request in ai_provider.requests:
        text_fields = (
            request.prompt_text,
            request.ocr_text,
            request.model_answer,
            request.rubric_text,
        )
        for needle in forbidden:
            for field in text_fields:
                assert needle not in field, f"{needle!r} leaked into a grading request"
        # One question's material, and only this question's -- and neither
        # this question's own identifiers nor any other question's.
        assert request.question_id in _question_ids(test_id)
        joined = "".join(text_fields)
        assert all(q not in joined for q in _question_ids(test_id))
        assert all(criterion_id not in joined for criterion_id in request.criterion_ids)

    # The image is the registered answer area's crop, never the whole page:
    # a full page carries the header the student's name is written in
    # (section 2 (2)'s "ページ全体の画像…を送信してはならない").
    crops = answer_crops(data_root, submission_id)
    sent = {_digest(image) for image in ocr_provider.received_images}
    assert sent == {_digest(image) for image in crops.values()}
    page_images = sorted((data_root / "submissions" / submission_id / "pages").glob("*.png"))
    assert page_images, "no page raster was kept, so the comparison below proves nothing"
    assert sent.isdisjoint({_digest(page.read_bytes()) for page in page_images})
    for image in ocr_provider.received_images:
        assert len(image) < min(page.stat().st_size for page in page_images)


def test_neither_the_api_token_nor_the_answer_body_is_written_to_the_log(
    client: TestClient, data_root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Section 28: "生徒答案本文をデバッグログへ無条件に書き込まない", and
    Issue #25's "secret/答案本文がログ・artifact・screenshotへ出ない".

    Captures every record the whole pipeline emits at DEBUG -- the level at
    which a careless diagnostic would be added -- and searches for the two
    strings that must never be there. `test_sidecar.py` already covers the
    `_RedactingFilter` that scrubs the token from a record that does contain
    it; what this adds is that a full register/intake/recognize/grade/review
    run does not produce such a record in the first place.
    """
    with caplog.at_level(logging.DEBUG):
        test_id, submission_id, _ = _one_answer(client, data_root, label=_STUDENT_LABEL)
        start_jobs(client, submission_id)
        wait_until_settled(client, submission_id)
        for question_id in _question_ids(test_id):
            _confirm_question(client, submission_id, question_id)

    assert caplog.records, "nothing was logged at all, so this asserts nothing"
    for record in caplog.records:
        rendered = "\n".join(
            part
            for part in (record.getMessage(), record.exc_text, str(record.args))
            if part is not None
        )
        assert _TOKEN not in rendered, f"the API token reached the log: {record.name}"
        assert DEFAULT_ANSWER_TEXT not in rendered, f"answer text reached the log: {record.name}"
        assert _STUDENT_LABEL not in rendered, f"a student label reached the log: {record.name}"
