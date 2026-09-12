"""Issue #116: the registration path Issues #101/#103/#105 built, carried all
the way to an exported PDF.

Those three Issues each landed with their own endpoint-level tests
(`test_intake_api.py`, `test_criteria_api.py`, `test_answer_area_api.py`),
and `test_e2e_acceptance.py` runs a full pass from registration to export --
but over the *pre-#101* registration path (`POST /tests` plus a hand-written
`PUT /profile` carrying `MODEL_ANSWER`/`RUBRIC`/`SCORE` regions). The
intersection was empty: nothing joined the new path to grading, review and
export, and the one test that came closest
(`test_answer_area_registration_flow.py`) stopped at intake and reached
`ready` by writing `Question` rows and a CONFIRMED `DependencyGraph`
straight into the database. So "採点が端から端まで通る" rested on a test that
never enqueued a grading job and never executed #103's code. This module is
that missing join.

**The pre-#101 path is not replaced by this.** It is still supported --
``build_questions_and_rubrics(criteria=None)`` exists for it -- and
`test_e2e_acceptance.py` remains its end-to-end cover, including the public
helpers `poc/issue_25_queue_throughput/report.py` drives the same app with.
This module adds the second path rather than repointing the first.

What is real, and what is substituted
=====================================
**Only external services are substituted.** Every step below crosses this
repository's own code through HTTP -- including the two that
`test_answer_area_registration_flow.py` used to bypass.

Real, driven through the API:

* 取込 (#101) -- ``POST /intake/plan``, and the roles it planned are what
  ``POST /tests`` is then called with
* 配点と採点基準 (#103) -- ``/criteria/extract`` → ``PUT /criteria`` (a
  human fills in the 不明) → ``/criteria/confirm``, which writes the
  `Question` and `Rubric` rows
* 回答欄 (#105) -- ``PUT /answer-layout`` → ``/answer-layout/detect`` →
  ``PUT /profile`` → ``/profile/confirm``
* 設問依存関係グラフ -- ``/dependency-graph/analyze`` → ``/confirm``
* ready から出力まで -- ``/complete-registration``, ``POST /submissions``,
  ``POST /submissions/{id}/jobs`` (the real queue, real SQLite, real
  `LocalFileStore`, real PDFium and OpenCV), ``/review/approve``,
  ``POST /export``

Substituted, and nothing else:

* 採点基準の抽出 provider -- `_ScriptedCriteriaExtractor`
* 回答欄検出 provider -- `_ScriptedAnswerAreaDetector`, whose output still
  goes through the real `parse_answer_area_detection`
* OCR provider -- `ScriptedOCRProvider`, and **deliberately absent** in the
  shipped-shape scenarios at the bottom of this module
* AI 採点 provider -- `ScriptedAIProvider`
* 分類 provider (#101) -- never reached at all: every file name in the
  fixture is matched by a template rule, so the plan's own estimate is zero
  calls and this app is built without a classifier

`ScriptedOCRProvider`, `ScriptedAIProvider` and `grading_response` are
imported from `test_e2e_acceptance` rather than re-written: what a provider
response has to look like for `GradingJobProcessor` to accept it is exactly
the thing a second copy would drift on. The scenario itself is this
module's own, because its fixture is a different one (questions named by
the 採点基準 draft, coordinates from detection, no `MODEL_ANSWER`/`RUBRIC`
regions at all).

Every file name, question number and document here is synthetic.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterator
from functools import partial
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.domain.answer_area_detection import (
    AnswerAreaDetectionOutput,
    AnswerAreaDetectionRequest,
    parse_answer_area_detection,
)
from auto_scoring.domain.criteria_extraction import (
    CriteriaExtractionOutput,
    CriteriaExtractionRequest,
    CriterionKind,
    ExtractedCriterionOutput,
    ExtractedQuestionOutput,
)
from auto_scoring.domain.models import NormalizedRect
from auto_scoring.domain.pdf_export import _FALLBACK_SCORE_STRIP
from auto_scoring.domain.pdf_intake import IntakeLimits
from auto_scoring.jobs.grading_settings import GradingSettings
from auto_scoring.jobs.recognition_settings import RecognitionSettings
from auto_scoring.jobs.settings import QueueSettings
from tests.font_support import install_font_covering
from tests.pdf_ink import has_red_within
from tests.test_e2e_acceptance import (
    ScriptedAIProvider,
    ScriptedOCRProvider,
    _session_factory,
    answer_crops,
    grading_response,
    ocr_result_of_spans,
)

_TOKEN = "e2e-intake-to-export-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}

#: The section 3 (C) confidence threshold, injected rather than hard-coded
#: into a decision -- same rule `test_e2e_acceptance.py` follows.
_CONFIDENCE_THRESHOLD = 0.80

#: The questions this test's 採点基準 describes, as (number, page index).
#: 問2 lives on page 2, so "the crop came from the question's own page" is a
#: real assertion rather than one page 1 would satisfy anyway.
_QUESTIONS = (("問1", 0), ("問2", 1))

#: One question per page, so the answer sheet has as many pages as questions.
_ANSWER_PAGE_COUNT = len(_QUESTIONS)

#: How many criteria the scripted extraction reports per question -- and so
#: how many `RubricCriterion` rows `/criteria/confirm` writes, whose ids a
#: grading response must echo 1:1 (`GradingJobProcessor` rejects one that
#: does not). Deliberately not the same for both: a rubric built from a
#: 採点基準 draft has one criterion per extracted clause, unlike the
#: single-criterion rubric a `RUBRIC` region produces.
_CRITERION_COUNTS = {"問1": 2, "問2": 1}

#: 問2's points are 不明 in the extraction and typed in by the reviewer --
#: the 不明 gate is on the real path, so the fixture has to go through it.
_HAND_ENTERED_POINTS = 15
_DECLARED_TOTAL_POINTS = 20

#: Where the per-submission marker is drawn on each page, and the answer area
#: the scripted detector reports over it. Keeping the marker inside the area
#: is what makes each submission's crop -- and so each provider payload --
#: distinguishable, exactly as a real handwritten answer would be.
_MARKER_XY = (60, 700)
_ANSWER_AREA = (0.05, 0.10, 0.60, 0.25)

#: The folder the reviewer picked, as the app's own scan would list it. The
#: names follow the default template's `01_`/`02_`/`03_` rules, so planning
#: resolves every role without a provider call (Issue #101 acceptance 8).
_FOLDER = "subject-a"
_ANSWER_FILE = f"{_FOLDER}/01_answers.pdf"
_CRITERIA_FILE = f"{_FOLDER}/02_criteria.pdf"
_RESOURCE_FILE = f"{_FOLDER}/03_resource.pdf"
_DEFAULT_TEMPLATE_ID = "serial-number-prefix"


# --------------------------------------------------------------------------- #
# Scripted external services
# --------------------------------------------------------------------------- #
class _ScriptedCriteriaExtractor:
    """What a model reads out of the 採点基準PDF (Issue #103).

    One question with a complete reading and one whose points it could not
    make out, because that is the shape the real material produced and the
    reason `/criteria/confirm` has a 不明 gate at all.
    """

    name = "scripted-criteria"

    def __init__(self) -> None:
        self.requests: list[CriteriaExtractionRequest] = []

    def extract(self, request: CriteriaExtractionRequest) -> CriteriaExtractionOutput:
        self.requests.append(request)
        return CriteriaExtractionOutput(
            questions=(
                ExtractedQuestionOutput(
                    number="問1",
                    points=5,
                    model_answer="問1の模範解答: 光合成のしくみを説明できている。",
                    criteria=(
                        ExtractedCriterionOutput(
                            description="要点に触れている", kind=CriterionKind.ADD, points=3
                        ),
                        ExtractedCriterionOutput(
                            description="理由を述べている", kind=CriterionKind.ADD, points=2
                        ),
                    ),
                    source_pages=(1,),
                ),
                ExtractedQuestionOutput(
                    number="問2",
                    points=None,
                    model_answer="問2の模範解答: 蒸散のはたらきを説明できている。",
                    criteria=(
                        ExtractedCriterionOutput(
                            description="主旨と理由の両方に触れている",
                            kind=CriterionKind.ADD,
                            points=None,
                        ),
                    ),
                    source_pages=(2,),
                    note="配点の記載が読み取れませんでした",
                ),
            ),
            total_points=_DECLARED_TOTAL_POINTS,
            unreadable_pages=(2,),
        )


class _ScriptedAnswerAreaDetector:
    """Reports one answer area per question, on that question's own page.

    Goes through the real `parse_answer_area_detection`, so the constraint
    that a detected area must name one of the *confirmed* question numbers
    is enforced here by the code under test, not by this class.
    """

    name = "scripted-answer-area"

    def detect(self, request: AnswerAreaDetectionRequest) -> AnswerAreaDetectionOutput:
        x0, y0, x1, y1 = _ANSWER_AREA
        return parse_answer_area_detection(
            json.dumps(
                {
                    "areas": [
                        {
                            "page": page_index + 1,
                            "question_number": number,
                            "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
                            "note": None,
                        }
                        for number, page_index in _QUESTIONS
                    ]
                }
            ),
            question_numbers=request.question_numbers,
            page_count=len(request.page_images),
        )


# --------------------------------------------------------------------------- #
# Fixture PDFs
# --------------------------------------------------------------------------- #
def _pdf(*, marker: str | None) -> bytes:
    """A `_ANSWER_PAGE_COUNT`-page A4 document.

    ``marker`` stands in for handwriting inside the answer area. Two
    submissions must differ -- `intake_submission` rejects a second upload
    with the same content hash as a duplicate (Issue #17) -- and drawing the
    marker *inside* the area is also what makes each crop, and so each
    provider payload, tell one student's answer from another's.
    """
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(595, 842))
    for page_number in range(1, _ANSWER_PAGE_COUNT + 1):
        if marker is not None:
            # ASCII only: the built-in Helvetica face has no CJK glyphs, and
            # what the pipeline "reads" out of this is the scripted OCR text
            # anyway.
            pdf.drawString(*_MARKER_XY, f"{marker}-p{page_number}")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# App / client
# --------------------------------------------------------------------------- #
@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "app-data"


@pytest.fixture
def extractor() -> _ScriptedCriteriaExtractor:
    return _ScriptedCriteriaExtractor()


@pytest.fixture
def ocr_provider() -> ScriptedOCRProvider:
    return ScriptedOCRProvider()


@pytest.fixture
def ai_provider() -> ScriptedAIProvider:
    return ScriptedAIProvider()


def _build_client(
    data_root: Path,
    *,
    extractor: _ScriptedCriteriaExtractor,
    ai_provider: ScriptedAIProvider,
    ocr_provider: ScriptedOCRProvider | None,
) -> TestClient:
    """The real app, wired to the scripted external services.

    ``ocr_provider=None`` leaves `create_app` to install its own default --
    `UnconfiguredOCRProvider` (Issue #114), which is what a host with no
    `AUTO_SCORING_DOCUMENT_AI_PROCESSOR` actually runs. The scenarios at the
    bottom of this module use that deliberately; everything above injects a
    scripted reader.

    ``with TestClient(...)`` (never the bare form) is what starts the queue's
    workers -- `create_app`'s lifespan owns `JobQueueService.start`.
    """
    return TestClient(
        create_app(
            api_token=_TOKEN,
            data_root=data_root,
            intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
            criteria_extractor=extractor,
            answer_area_detector=_ScriptedAnswerAreaDetector(),
            ocr_provider=ocr_provider,
            ai_provider=ai_provider,
            recognition_settings=RecognitionSettings(confidence_threshold=_CONFIDENCE_THRESHOLD),
            grading_settings=GradingSettings(confidence_threshold=_CONFIDENCE_THRESHOLD),
            queue_settings=QueueSettings(
                max_concurrency=2,
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
    extractor: _ScriptedCriteriaExtractor,
    ocr_provider: ScriptedOCRProvider,
    ai_provider: ScriptedAIProvider,
) -> Iterator[TestClient]:
    with _build_client(
        data_root, extractor=extractor, ai_provider=ai_provider, ocr_provider=ocr_provider
    ) as test_client:
        yield test_client


# --------------------------------------------------------------------------- #
# Registration, through the path Issues #101 / #103 / #105 built
# --------------------------------------------------------------------------- #
def _plan_the_folder(client: TestClient) -> dict[str, Any]:
    """Issue #101: what one subject folder would become, before anything is
    uploaded. Returns the single planned group."""
    response = client.post(
        "/intake/plan",
        headers=_AUTH,
        json={
            "template_id": _DEFAULT_TEMPLATE_ID,
            "root_name": _FOLDER,
            "files": [
                {"relative_path": path, "size_bytes": 1024, "sha256": f"{index:064x}"}
                for index, path in enumerate((_ANSWER_FILE, _CRITERIA_FILE, _RESOURCE_FILE))
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # Every name matched a template rule, so planning this folder costs
    # nothing and no classifier is configured on this app at all.
    assert body["estimate"]["pending"] == 0
    assert len(body["groups"]) == 1
    group: dict[str, Any] = body["groups"][0]
    assert group["missing_required_roles_if_new"] == []
    return group


def _register_from_plan(client: TestClient, group: dict[str, Any]) -> str:
    """Create the test from what the plan decided each file was.

    The roles come out of the plan rather than being restated here: that is
    the join Issue #101 actually delivers -- the screen uploads what planning
    resolved -- and restating them would leave it untested.
    """
    by_role = {planned["role"]: planned["relative_path"] for planned in group["files"]}
    assert by_role["student_answer"] == _ANSWER_FILE
    criteria_path = by_role["grading_criteria"]
    resource_path = by_role["annotation_resource"]

    created = client.post(
        "/tests",
        headers=_AUTH,
        data={
            "name": group["suggested_name"],
            "subject": "理科",
            "material_roles": ["annotation_resource"],
        },
        files=[
            ("criteria", (Path(criteria_path).name, _pdf(marker=None), "application/pdf")),
            ("materials", (Path(resource_path).name, _pdf(marker=None), "application/pdf")),
        ],
    )
    assert created.status_code == 201, created.text
    test_id: str = created.json()["id"]
    return test_id


def _confirm_criteria(client: TestClient, test_id: str) -> None:
    """Issue #103: extract the 配点と採点基準, have a human fill in the 不明,
    and confirm. This is what writes the `Question` and `Rubric` rows."""
    extracted = client.post(f"/tests/{test_id}/criteria/extract", headers=_AUTH)
    assert extracted.status_code == 200, extracted.text
    draft = extracted.json()
    assert [question["points"] for question in draft["questions"]] == [5, None]
    assert draft["totals"]["is_complete"] is False

    # Confirming is refused while a value is still 不明 -- the reviewer has
    # to type it, and this fixture goes through that rather than around it.
    still_unknown = client.post(
        f"/tests/{test_id}/criteria/confirm",
        headers=_AUTH,
        json={"revision": draft["revision"]},
    )
    assert still_unknown.status_code == 422, still_unknown.text

    questions = [dict(question) for question in draft["questions"]]
    questions[1]["points"] = _HAND_ENTERED_POINTS
    saved = client.put(
        f"/tests/{test_id}/criteria",
        headers=_AUTH,
        json={"questions": questions, "declared_total_points": _DECLARED_TOTAL_POINTS},
    )
    assert saved.status_code == 200, saved.text
    confirmed = client.post(
        f"/tests/{test_id}/criteria/confirm",
        headers=_AUTH,
        json={"revision": saved.json()["revision"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["totals"]["is_complete"] is True


def _confirm_answer_layout(client: TestClient, test_id: str) -> None:
    """Issue #105: upload one answer sheet, detect the answer areas on it,
    and confirm exactly what came back.

    **Nothing is added by hand.** Until Issue #120 this helper also drew a
    `score` and an `annotation_area` region per question, described as "the
    reviewer's own drawing" -- but Issue #103 removed both from the profile
    screen so that the 配点 would have exactly one input, and a real reviewer
    on this path cannot draw either one. Injecting them over the raw API gave
    every question a `score_area` that no real registration would have, and
    that is why this module could report the new path green while the live
    run exported a PDF with nothing written on it (Issue #120).

    A fixture that reaches a state the product cannot reach is not a
    shortcut; it is the test agreeing with itself. What detection returns is
    all there is, and `domain.pdf_export.fallback_score_areas` is what
    has to turn that into somewhere to write.
    """
    uploaded = client.put(
        f"/tests/{test_id}/answer-layout",
        headers=_AUTH,
        files={"file": ("answer-sheet.pdf", _pdf(marker="layout"), "application/pdf")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["page_count"] == _ANSWER_PAGE_COUNT
    assert uploaded.json()["detection_available"] is True

    detected = client.post(f"/tests/{test_id}/answer-layout/detect", headers=_AUTH)
    assert detected.status_code == 200, detected.text
    body = detected.json()
    assert body["undetected_question_numbers"] == []
    assert body["unassigned_region_ids"] == []
    answer_areas = [region for region in body["regions"] if region["kind"] == "answer_area"]
    assert {region["label"] for region in answer_areas} == {number for number, _ in _QUESTIONS}

    saved = client.put(f"/tests/{test_id}/profile", headers=_AUTH, json={"regions": answer_areas})
    assert saved.status_code == 200, saved.text
    confirmed = client.post(
        f"/tests/{test_id}/profile/confirm",
        headers=_AUTH,
        json={"revision": saved.json()["revision"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"


def _edge(test_id: str, *, source: str, target: str) -> dict[str, Any]:
    return {
        "from_question_id": f"{test_id}:{source}",
        "to_question_id": f"{test_id}:{target}",
        "provides": ["recognized_text"],
        "rationale": "問2は問1で答えた語を前提にしている",
        "confidence": None,
    }


def _confirm_dependency_graph(
    client: TestClient, test_id: str, *, edges: list[dict[str, Any]]
) -> None:
    analyzed = client.post(
        f"/tests/{test_id}/dependency-graph/analyze", headers=_AUTH, json={"overrides": []}
    )
    assert analyzed.status_code == 200, analyzed.text
    assert sorted(analyzed.json()["question_ids"]) == _question_ids(test_id)
    confirmed = client.post(
        f"/tests/{test_id}/dependency-graph/confirm",
        headers=_AUTH,
        json={"version": analyzed.json()["version"], "edges": edges},
    )
    assert confirmed.status_code == 200, confirmed.text


def _register_via_the_new_path(client: TestClient, *, edges: bool = False) -> str:
    """Plan a folder, register it, confirm its 採点基準, its 回答欄 and its
    dependency graph, and complete registration. Returns the `ready` test id.

    ``edges`` adds the one dependency 問1 -> 問2, which is what the
    shipped-shape scenario at the bottom needs in order to show what an
    unusable prerequisite does to its dependent.
    """
    group = _plan_the_folder(client)
    test_id = _register_from_plan(client, group)
    _confirm_criteria(client, test_id)
    _confirm_answer_layout(client, test_id)
    _confirm_dependency_graph(
        client,
        test_id,
        edges=[_edge(test_id, source="問1", target="問2")] if edges else [],
    )

    completed = client.post(f"/tests/{test_id}/complete-registration", headers=_AUTH)
    assert completed.status_code == 200, completed.text
    assert completed.json()["test"]["status"] == "ready"
    assert completed.json()["profile_confirmed"] is True
    assert completed.json()["dependency_graph_confirmed"] is True
    return test_id


# --------------------------------------------------------------------------- #
# Intake, the queue, review and export
# --------------------------------------------------------------------------- #
def _question_ids(test_id: str) -> list[str]:
    return sorted(f"{test_id}:{number}" for number, _ in _QUESTIONS)


def _criterion_ids(question_id: str) -> tuple[str, ...]:
    """The ids `/criteria/confirm` wrote for this question's rubric.

    One per criterion the extraction reported -- `_rubric_from_draft` numbers
    them ``c1``, ``c2``, ... in order. A grading response has to echo exactly
    these, so they are derived from the fixture rather than written out.
    """
    number = question_id.rsplit(":", 1)[1]
    return tuple(f"{question_id}:rubric:c{index + 1}" for index in range(_CRITERION_COUNTS[number]))


def _upload_answer(client: TestClient, test_id: str, *, marker: str) -> str:
    response = client.post(
        f"/tests/{test_id}/submissions",
        headers=_AUTH,
        data={"student_label": "A01"},
        files={"file": (Path(_ANSWER_FILE).name, _pdf(marker=marker), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["review_reason"] is None
    submission_id: str = response.json()["id"]
    return submission_id


def _script_the_grader(ai_provider: ScriptedAIProvider, crops: dict[str, bytes]) -> None:
    """Answer every question with a response that matches the rubric
    `/criteria/confirm` actually wrote.

    Keyed by the crop, like `test_e2e_acceptance.py`: the crop is the only
    thing the provider is given that differs between questions, which is
    section 2 (2)'s rule and not merely a convenience. Scripted at all --
    rather than left to `ScriptedAIProvider`'s own default -- because that
    default builds a single-criterion response, and a rubric that came from
    a 採点基準 draft has one criterion per extracted clause.
    """
    for question_id, image in crops.items():
        ai_provider.script(
            image, [partial(grading_response, criterion_ids=_criterion_ids(question_id))]
        )


def _jobs(client: TestClient, submission_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/submissions/{submission_id}/jobs", headers=_AUTH)
    assert response.status_code == 200, response.text
    listing: list[dict[str, Any]] = response.json()
    return listing


def _job_for(client: TestClient, submission_id: str, question_id: str) -> dict[str, Any]:
    matches = [job for job in _jobs(client, submission_id) if job["question_id"] == question_id]
    assert len(matches) == 1, f"expected one job for {question_id!r}, got {matches}"
    return matches[0]


#: The three states a job stops moving in. Narrower than
#: `test_e2e_acceptance.wait_until_settled`'s rule, which also has to allow
#: for a retryable FAILED being requeued -- nothing here scripts a provider
#: failure, so a FAILED job in this module is a real defect and settling on
#: it is what reports it.
_SETTLED_STATES = frozenset({"succeeded", "failed", "cancelled"})


def _wait_for(predicate: Any, message: str, *, timeout: float = 20.0) -> None:
    """Poll ``predicate`` until it holds, or fail with ``message``.

    Real-time polling, like `test_export_api.py`: this app runs on the real
    `SystemClock`. The timeout only bounds how long a *failing* run takes to
    say so -- no passing assertion is decided by it (docs/job-queue.md's
    Issue #50 record).
    """
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError(message)
        time.sleep(0.01)


def _start_and_wait(client: TestClient, submission_id: str) -> None:
    started = client.post(f"/submissions/{submission_id}/jobs", headers=_AUTH)
    assert started.status_code == 200, started.text
    _wait_for(
        lambda: all(job["state"] in _SETTLED_STATES for job in _jobs(client, submission_id)),
        f"jobs for {submission_id} never settled",
    )


def _approve_every_question(client: TestClient, test_id: str, submission_id: str) -> None:
    for question_id in _question_ids(test_id):
        history = client.get(
            f"/submissions/{submission_id}/questions/{question_id}/reviews", headers=_AUTH
        )
        assert history.status_code == 200, history.text
        approved = client.post(
            f"/submissions/{submission_id}/questions/{question_id}/review/approve",
            headers=_AUTH,
            json={"expected_version": len(history.json())},
        )
        assert approved.status_code == 201, approved.text
        assert approved.json()["review"]["action"] == "approved"


def _export(client: TestClient, submission_id: str) -> dict[str, Any]:
    response = client.post(f"/submissions/{submission_id}/export", headers=_AUTH)
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    _wait_for(
        lambda: client.get(f"/jobs/{job_id}", headers=_AUTH).json()["state"] == "succeeded",
        f"export job {job_id} never succeeded",
    )
    exports = client.get(f"/submissions/{submission_id}/exports", headers=_AUTH).json()
    matches = [export for export in exports if export["job_id"] == job_id]
    assert len(matches) == 1, f"expected one export for job {job_id}, got {exports}"
    exported: dict[str, Any] = matches[0]
    return exported


# --------------------------------------------------------------------------- #
# The join Issue #116 exists to make
# --------------------------------------------------------------------------- #
def test_a_folder_becomes_a_graded_reviewed_and_exported_answer(
    client: TestClient,
    data_root: Path,
    extractor: _ScriptedCriteriaExtractor,
    ai_provider: ScriptedAIProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One pass over the whole path Issues #101, #103 and #105 built.

    Plan a folder, register it from that plan, extract and confirm its
    配点と採点基準, detect and confirm its 回答欄, confirm the dependency
    graph, complete registration, take in an answer, let the real queue
    recognize and grade it, approve every question, and export.

    Nothing here writes a `Question`, a `Rubric`, a `Profile` or a
    `DependencyGraph` into the database: each one is produced by the
    endpoint that owns it. The only reads that go straight to storage are
    `answer_crops` (what the providers were handed) and the exported file
    on disk.
    """
    test_id = _register_via_the_new_path(client)

    # The `Question` rows really came from the confirmed 採点基準 and the
    # confirmed 回答欄, each field from whichever artefact knows it.
    questions = client.get(f"/tests/{test_id}/questions", headers=_AUTH).json()
    assert [(q["number"], q["points"]) for q in questions] == [
        ("問1", 5),
        ("問2", _HAND_ENTERED_POINTS),
    ]
    assert [q["page"] for q in questions] == [1, 2]
    assert len(extractor.requests) == 1

    submission_id = _upload_answer(client, test_id, marker="ans-a")
    crops = answer_crops(data_root, submission_id)
    assert sorted(crops) == _question_ids(test_id), "every question was cropped to its own area"
    assert len(set(crops.values())) == len(crops), "each question's crop is its own page"

    _script_the_grader(ai_provider, crops)
    _start_and_wait(client, submission_id)

    for question_id in _question_ids(test_id):
        job = _job_for(client, submission_id, question_id)
        assert job["state"] == "succeeded", job
        assert job["usable"] is True, job
        grades = client.get(
            f"/submissions/{submission_id}/questions/{question_id}/grades", headers=_AUTH
        ).json()
        assert [grade["source"] for grade in grades] == ["ai"]
        assert grades[0]["score"]["maximum"] == next(
            q["points"] for q in questions if q["id"] == question_id
        )

    # Every criterion the 採点基準 produced was graded -- the ids the AI
    # echoed are the ones `/criteria/confirm` wrote, or the response would
    # have been rejected as mismatched.
    graded = client.get(
        f"/submissions/{submission_id}/questions/{test_id}:問1/grades", headers=_AUTH
    ).json()[0]
    assert [c["criterion_id"] for c in graded["criteria"]] == list(_criterion_ids(f"{test_id}:問1"))

    _approve_every_question(client, test_id, submission_id)

    # The score is the thing the export has to draw; the glyphs it needs are
    # digits and a slash (`domain.pdf_export._score_text`).
    install_font_covering(monkeypatch, "0123456789/")

    source = data_root / "submissions" / submission_id / "source.pdf"
    before = _digest(source.read_bytes())
    exported = _export(client, submission_id)
    output = data_root / exported["file_path"]
    assert output.exists() and output != source
    assert _digest(source.read_bytes()) == before, "the original PDF was modified"

    # Issue #120: this test used to stop one line above, and that line
    # compares two `Path` objects -- true of any two different filenames,
    # including a byte-for-byte copy of the answer sheet. Which is exactly
    # what the live run produced: a 202, a succeeded job, and a PDF with no
    # score and no comment anywhere on it, because this path never set
    # `Question.score_area`. The confirmed score has to be visible on the
    # page for this path to be finished.
    #
    # Issue #159 moved *where* that has to be visible. The score used to be
    # drawn in a `score_area` derived from the answer box, and the live
    # measurement found that band on the student's own writing for fourteen
    # of sixteen questions. So the assertion is now the pair: the score is in
    # the page's left margin strip, and there is no red inside the answer box
    # at all. Both halves are needed -- "no ink on the answer" alone passes
    # for a page nothing was drawn on, which is the Issue #120 failure.
    engine = PdfiumPypdfEngine()
    for question in client.get(f"/tests/{test_id}/questions", headers=_AUTH).json():
        answer_area = question["answer_area"]
        assert answer_area is not None, f"{question['id']} lost its answer box"
        rendered = engine.render_page_png(output, question["page"] - 1, scale=2.0)
        assert has_red_within(rendered, _FALLBACK_SCORE_STRIP), (
            f"nothing was drawn in {question['id']}'s margin strip"
        )
        assert not has_red_within(rendered, NormalizedRect(**answer_area), margin=0.0), (
            f"{question['id']}'s ink landed on the student's answer"
        )
        # Last, not first: the two ink assertions above are what this test is
        # for, and a `score_area` check ahead of them would short-circuit
        # before either one ever ran.
        assert question["score_area"] is None, (
            f"{question['id']} still has a derived score area (Issue #159)"
        )


def test_export_is_refused_until_every_question_of_the_new_path_is_confirmed(
    client: TestClient, data_root: Path, ai_provider: ScriptedAIProvider
) -> None:
    """The gate at the end of the same path.

    Worth stating here rather than leaning on `test_e2e_acceptance.py`'s
    version of it: the question set that gate reports is now built by
    `/criteria/confirm` and `/profile/confirm` together, so "which questions
    are still unconfirmed" is an answer only this path can give wrongly.
    """
    test_id = _register_via_the_new_path(client)
    submission_id = _upload_answer(client, test_id, marker="ans-b")
    _script_the_grader(ai_provider, answer_crops(data_root, submission_id))
    _start_and_wait(client, submission_id)

    first, second = _question_ids(test_id)
    history = client.get(
        f"/submissions/{submission_id}/questions/{first}/reviews", headers=_AUTH
    ).json()
    client.post(
        f"/submissions/{submission_id}/questions/{first}/review/approve",
        headers=_AUTH,
        json={"expected_version": len(history)},
    )

    refused = client.post(f"/submissions/{submission_id}/export", headers=_AUTH)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["question_ids"] == [second]


# --------------------------------------------------------------------------- #
# The same path on a host with no OCR service -- the shipped shape
# --------------------------------------------------------------------------- #
# What a host with no OCR service actually does.
#
# `create_app` installs `UnconfiguredOCRProvider` when no OCR provider is
# injected, and that is what ships on a machine where
# `AUTO_SCORING_DOCUMENT_AI_PROCESSOR` is unset -- a supported configuration,
# not a broken one (simplified-design-specification.md section 24: "OCR失敗:
# **採点は止めない。**").
#
# **These three tests changed in Issue #114.** Until then `create_app` fell
# back to `NullOCRProvider`, which answered every image with an empty reading
# at ``confidence=0.0`` -- so every question came back ``usable=False`` and
# every dependency edge stalled its downstream until a human pressed
# ``/resume`` on the prerequisite. The two tests here recorded that, honestly
# labelled as "current behaviour, not the desired one: Issue #114 is where
# changing it is decided". It was decided: a host with no OCR has no OCR term
# to gate on, so the gate is the grading AI's own reading and its grading
# confidence (docs/ocr-recognition-pipeline.md section 8.2).
#
# The third test is the half that must NOT change and so is pinned
# separately: an OCR that *did* read the crop and was not confident still
# blocks its dependents, and only a human opens that gate. "The OCR could not
# read this" and "this machine has no OCR" are different facts.
def test_without_an_ocr_service_every_question_still_reaches_export_by_hand(
    data_root: Path,
    extractor: _ScriptedCriteriaExtractor,
    ai_provider: ScriptedAIProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No OCR adapter, no dependencies between questions.

    Grading runs and produces a proposal for each question -- the AI provider
    is multimodal and is handed the crop itself, so a missing OCR reading
    does not stop it.

    Since Issue #114 the questions also come back ``usable=True``: with no OCR
    reading there is no Recognition Confidence to compare, and inventing a
    0.0 to fail against is what section 8.1.4 forbids ("読めていないものに
    数値を与えない"). ``usable`` releases *dependent questions*, though --
    never a confirmation. **Confirming is still the reviewer's**, which is why
    this scenario still ends by hand.
    """
    with _build_client(
        data_root, extractor=extractor, ai_provider=ai_provider, ocr_provider=None
    ) as client:
        test_id = _register_via_the_new_path(client)
        submission_id = _upload_answer(client, test_id, marker="ans-c")
        _script_the_grader(ai_provider, answer_crops(data_root, submission_id))
        _start_and_wait(client, submission_id)

        for question_id in _question_ids(test_id):
            job = _job_for(client, submission_id, question_id)
            assert job["state"] == "succeeded", job
            assert job["usable"] is True, "with no OCR reading there is no OCR term to gate on"
            grades = client.get(
                f"/submissions/{submission_id}/questions/{question_id}/grades", headers=_AUTH
            ).json()
            assert grades, "the proposal must be kept for the reviewer, not discarded"
            recognitions = client.get(
                f"/submissions/{submission_id}/questions/{question_id}/recognitions",
                headers=_AUTH,
            ).json()
            # Only the grader's own reading. No OCR row at all -- which is how
            # "this host has no OCR" stays distinguishable afterwards from
            # "the OCR looked and found nothing" (Issue #114).
            assert [r["id"].split(":")[0] for r in recognitions] == ["grading-recognition"]

        # Nothing was auto-confirmed: every question still needs the reviewer.
        _approve_every_question(client, test_id, submission_id)
        install_font_covering(monkeypatch, "0123456789/")
        exported = _export(client, submission_id)
        assert (data_root / exported["file_path"]).exists()


def test_without_an_ocr_service_a_dependent_question_still_runs_without_a_human(
    data_root: Path,
    extractor: _ScriptedCriteriaExtractor,
    ai_provider: ScriptedAIProvider,
) -> None:
    """The same host, with one confirmed dependency 問1 -> 問2.

    **This test asserted the opposite until Issue #114**, and its old name
    said so: ``..._stays_blocked_until_a_human_resumes_it``. On the shipped
    configuration every dependency edge stalled its downstream, because
    `NullOCRProvider`'s fabricated 0.0 made every prerequisite unusable and
    `evaluate_readiness` refuses to release a dependent on an unusable one.
    For an app whose premise is 採点の自動化, a reviewer pressing ``/resume``
    once per question is not a workaround -- it is the feature not working.

    So: 問2 runs on its own, and this test never calls ``/resume``. What
    still gates it is the grading half -- see the test below, which is where
    a prerequisite the OCR genuinely could not read still stops.
    """
    with _build_client(
        data_root, extractor=extractor, ai_provider=ai_provider, ocr_provider=None
    ) as client:
        test_id = _register_via_the_new_path(client, edges=True)
        submission_id = _upload_answer(client, test_id, marker="ans-d")
        _script_the_grader(ai_provider, answer_crops(data_root, submission_id))
        _start_and_wait(client, submission_id)

        first, second = f"{test_id}:問1", f"{test_id}:問2"
        prerequisite = _job_for(client, submission_id, first)
        assert prerequisite["state"] == "succeeded"
        assert prerequisite["usable"] is True

        dependent = _job_for(client, submission_id, second)
        assert dependent["state"] == "succeeded", dependent
        # Ran, rather than merely being unblocked: a released dependent that
        # was never graded would satisfy the state assertion alone.
        assert client.get(
            f"/submissions/{submission_id}/questions/{second}/grades", headers=_AUTH
        ).json(), "問2 was released but never graded"


def test_an_ocr_that_read_nothing_still_blocks_until_a_human_resumes_it(
    data_root: Path,
    extractor: _ScriptedCriteriaExtractor,
    ocr_provider: ScriptedOCRProvider,
    ai_provider: ScriptedAIProvider,
) -> None:
    """The half Issue #114 deliberately left alone, pinned on its own.

    Here the host *has* an OCR service and it looked at 問1's crop -- and got
    nothing readable out of it. That is the case
    business-rules-and-evaluation-data.md section 4.4 was written for, and it
    still stops the dependent: the reading exists, none of it can be handed
    downstream, and a human decides what to do.

    Together with the test above this is the whole distinction Issue #114
    turns on. Loosening "no OCR here" must not quietly loosen "the OCR could
    not read this", and only running both proves it did not.

    **Issue #158 narrowed what counts as the second one, and its own test is
    below**: a reading with unreadable spans *among readable ones* no longer
    stops anything. What is scripted here is a reading with nothing readable
    in it at all -- which is why the name no longer says "could not trust".
    """
    with _build_client(
        data_root, extractor=extractor, ai_provider=ai_provider, ocr_provider=ocr_provider
    ) as client:
        test_id = _register_via_the_new_path(client, edges=True)
        submission_id = _upload_answer(client, test_id, marker="ans-e")
        crops = answer_crops(data_root, submission_id)
        _script_the_grader(ai_provider, crops)
        first, second = f"{test_id}:問1", f"{test_id}:問2"
        ocr_provider.script(
            crops[first],
            [ocr_result_of_spans([("(判読不能)", 0.3), ("(判読不能)", 0.2)])],
        )

        started = client.post(f"/submissions/{submission_id}/jobs", headers=_AUTH)
        assert started.status_code == 200, started.text
        _wait_for(
            lambda: _job_for(client, submission_id, first)["state"] in _SETTLED_STATES,
            "問1's job never settled",
        )

        prerequisite = _job_for(client, submission_id, first)
        assert prerequisite["state"] == "succeeded"
        assert prerequisite["usable"] is False
        blocked = _job_for(client, submission_id, second)
        assert blocked["state"] == "blocked", blocked
        assert blocked["blocked_on_question_id"] == first
        assert (
            client.get(
                f"/submissions/{submission_id}/questions/{second}/grades", headers=_AUTH
            ).json()
            == []
        ), "a blocked question must not have been graded"

        # The human release. Nothing else in the app can open this gate.
        resumed = client.post(
            f"/submissions/{submission_id}/questions/{first}/resume", headers=_AUTH
        )
        assert resumed.status_code == 204, resumed.text
        _wait_for(
            lambda: _job_for(client, submission_id, second)["state"] in _SETTLED_STATES,
            "問2 never ran after its prerequisite was resumed",
        )
        assert _job_for(client, submission_id, second)["state"] == "succeeded"


def test_a_partly_unreadable_prerequisite_no_longer_blocks_its_dependent(
    data_root: Path,
    extractor: _ScriptedCriteriaExtractor,
    ocr_provider: ScriptedOCRProvider,
    ai_provider: ScriptedAIProvider,
) -> None:
    """The pair to the test above, and what Issue #158 actually changed.

    Same host, same edge 問1 -> 問2, and 問1's crop *was* read -- most of it
    confidently, one span of it not. Until Issue #158 the recognition half
    reported the worst span's confidence and compared that against the
    threshold, so this reading stopped 問2 and a human had to press
    ``/resume`` to release it.

    That rule punished length. The worst of N spans only falls as N grows, so
    the more a student wrote the more certainly their answer stopped the next
    question, whatever it said -- on the 15 recorded readings of 2026-09-09
    every reading of 5 spans or fewer passed and every one of 9 or more
    failed (docs/ocr-recognition-pipeline.md §9). So this scenario, which is
    what a long answer in ordinary handwriting looks like, must run through
    without a human, while the test above -- nothing readable at all -- must
    still stop. Running both is the only way to show the loosening went
    exactly that far and no further.
    """
    with _build_client(
        data_root, extractor=extractor, ai_provider=ai_provider, ocr_provider=ocr_provider
    ) as client:
        test_id = _register_via_the_new_path(client, edges=True)
        submission_id = _upload_answer(client, test_id, marker="ans-f")
        crops = answer_crops(data_root, submission_id)
        _script_the_grader(ai_provider, crops)
        first, second = f"{test_id}:問1", f"{test_id}:問2"
        ocr_provider.script(
            crops[first],
            [
                ocr_result_of_spans(
                    [("光合成は", 0.96), ("葉緑体で", 0.93), ("&&&", 0.31), ("行われる", 0.91)]
                )
            ],
        )

        _start_and_wait(client, submission_id)

        prerequisite = _job_for(client, submission_id, first)
        assert prerequisite["state"] == "succeeded"
        assert prerequisite["usable"] is True, (
            "one unreadable span among readable ones is a fact about the "
            "length of the answer, not a reason to stop the next question"
        )

        # 問2 ran on its own. No /resume is called anywhere in this test.
        dependent = _job_for(client, submission_id, second)
        assert dependent["state"] == "succeeded", dependent
        assert client.get(
            f"/submissions/{submission_id}/questions/{second}/grades", headers=_AUTH
        ).json(), "問2 was released but never graded"

        # The unreadable span is not lost -- it is recorded where it is, for
        # a reviewer to look at (Issue #158; showing it on screen is its own
        # issue, since that needs the OpenAPI schema to carry it).
        recognitions = client.get(
            f"/submissions/{submission_id}/questions/{first}/recognitions", headers=_AUTH
        ).json()
        ocr_rows = [row for row in recognitions if row["stage"] == "ocr"]
        assert len(ocr_rows) == 1
        assert len(ocr_rows[0]["boxes"]) == 4


# --------------------------------------------------------------------------- #
# Issue #449: selecting the questions to grade
# --------------------------------------------------------------------------- #
def test_an_excluded_question_is_not_graded_and_does_not_block_its_dependent(
    data_root: Path,
    extractor: _ScriptedCriteriaExtractor,
    ai_provider: ScriptedAIProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole exclusion promise on one real run.

    問1 is a prerequisite of 問2, and 問1 is excluded. 問2 must still be
    graded (no ``/resume`` anywhere), 問1 must never reach the provider, the
    confirmation denominator must shrink to 問2, and an export that confirms
    only 問2 must be accepted.
    """
    with _build_client(
        data_root, extractor=extractor, ai_provider=ai_provider, ocr_provider=None
    ) as client:
        test_id = _register_via_the_new_path(client, edges=True)
        first, second = f"{test_id}:問1", f"{test_id}:問2"
        selected = client.put(
            f"/tests/{test_id}/scoring-targets",
            headers=_AUTH,
            json={"question_ids": [second]},
        )
        assert selected.status_code == 200, selected.text
        assert selected.json()["question_ids"] == [second]

        submission_id = _upload_answer(client, test_id, marker="ans-g")
        _script_the_grader(ai_provider, answer_crops(data_root, submission_id))
        _start_and_wait(client, submission_id)

        # ① The excluded question was not graded: no job, no grade, and the
        # provider was never handed its crop.
        assert [job["question_id"] for job in _jobs(client, submission_id)] == [second]
        assert _job_for(client, submission_id, second)["state"] == "succeeded"
        assert (
            client.get(
                f"/submissions/{submission_id}/questions/{first}/grades", headers=_AUTH
            ).json()
            == []
        )
        assert all(request.question_id != first for request in ai_provider.requests)

        # ② The confirmation denominator counts only the graded question.
        progress = client.get(f"/tests/{test_id}/review-progress", headers=_AUTH).json()
        assert len(progress) == 1
        assert progress[0]["total_questions"] == 1
        assert progress[0]["confirmed_questions"] == 0

        history = client.get(
            f"/submissions/{submission_id}/questions/{second}/reviews", headers=_AUTH
        ).json()
        approved = client.post(
            f"/submissions/{submission_id}/questions/{second}/review/approve",
            headers=_AUTH,
            json={"expected_version": len(history)},
        )
        assert approved.status_code == 201, approved.text

        progress = client.get(f"/tests/{test_id}/review-progress", headers=_AUTH).json()
        assert progress[0]["confirmed_questions"] == 1
        with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
            submission = uow.submissions.get(submission_id)
            assert submission is not None
            assert submission.state.value == "reviewed"

        # ③ The export gate ignores the excluded question: confirming only 問2
        # is enough, and the export's snapshot names only 問2 -- so nothing of
        # 問1 was drawn. Its unconfirmed review never enters the artefact.
        install_font_covering(monkeypatch, "0123456789/")
        exported = _export(client, submission_id)
        with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
            row = uow.exports.get(exported["id"])
            assert row is not None
        assert [version.question_id for version in row.review_versions] == [second]


def test_scoring_targets_endpoint_validates_and_round_trips(
    data_root: Path,
    extractor: _ScriptedCriteriaExtractor,
    ai_provider: ScriptedAIProvider,
) -> None:
    """The selection is replaceable by id, cannot be emptied, and is visible to
    the settings screen only through ``include_excluded_questions``."""
    with _build_client(
        data_root, extractor=extractor, ai_provider=ai_provider, ocr_provider=None
    ) as client:
        test_id = _register_via_the_new_path(client)
        all_questions = _question_ids(test_id)

        # Default is every question, and the review listing shows only targets
        # (all of them until something is excluded).
        default = client.get(f"/tests/{test_id}/questions", headers=_AUTH).json()
        assert [q["id"] for q in default] == all_questions
        assert all(q["is_scoring_target"] for q in default)

        empty = client.put(
            f"/tests/{test_id}/scoring-targets", headers=_AUTH, json={"question_ids": []}
        )
        assert empty.status_code == 422, empty.text

        unknown = client.put(
            f"/tests/{test_id}/scoring-targets",
            headers=_AUTH,
            json={"question_ids": ["nope"]},
        )
        assert unknown.status_code == 422, unknown.text

        selected = client.put(
            f"/tests/{test_id}/scoring-targets",
            headers=_AUTH,
            json={"question_ids": [all_questions[0]]},
        )
        assert selected.status_code == 200, selected.text
        assert selected.json()["question_ids"] == [all_questions[0]]

        default_after = client.get(f"/tests/{test_id}/questions", headers=_AUTH).json()
        assert [q["id"] for q in default_after] == [all_questions[0]]

        with_excluded = client.get(
            f"/tests/{test_id}/questions",
            headers=_AUTH,
            params={"include_excluded_questions": "true"},
        ).json()
        assert sorted(q["id"] for q in with_excluded) == all_questions
        assert {q["id"]: q["is_scoring_target"] for q in with_excluded} == {
            all_questions[0]: True,
            all_questions[1]: False,
        }

        # Re-selecting everything is allowed, including after `ready`.
        restored = client.put(
            f"/tests/{test_id}/scoring-targets",
            headers=_AUTH,
            json={"question_ids": all_questions},
        )
        assert restored.status_code == 200, restored.text
        assert sorted(restored.json()["question_ids"]) == all_questions


def test_the_selection_survives_the_profile_confirm_rebuild(
    data_root: Path,
    extractor: _ScriptedCriteriaExtractor,
    ai_provider: ScriptedAIProvider,
) -> None:
    """The profile confirm deletes and rebuilds every `Question` row. A
    selection made before it (the criteria confirm already wrote the rows, so
    the settings screen can show them) must not be silently reset to "all"."""
    with _build_client(
        data_root, extractor=extractor, ai_provider=ai_provider, ocr_provider=None
    ) as client:
        group = _plan_the_folder(client)
        test_id = _register_from_plan(client, group)
        _confirm_criteria(client, test_id)

        first, second = f"{test_id}:問1", f"{test_id}:問2"
        selected = client.put(
            f"/tests/{test_id}/scoring-targets",
            headers=_AUTH,
            json={"question_ids": [second]},
        )
        assert selected.status_code == 200, selected.text

        # Rebuilds the rows from the confirmed profile.
        _confirm_answer_layout(client, test_id)

        listed = client.get(
            f"/tests/{test_id}/questions",
            headers=_AUTH,
            params={"include_excluded_questions": "true"},
        ).json()
        assert {question["id"]: question["is_scoring_target"] for question in listed} == {
            first: False,
            second: True,
        }
