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
  two shipped-shape scenarios at the bottom of this module
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
from auto_scoring.domain.pdf_intake import IntakeLimits
from auto_scoring.jobs.grading_settings import GradingSettings
from auto_scoring.jobs.recognition_settings import RecognitionSettings
from auto_scoring.jobs.settings import QueueSettings
from tests.test_e2e_acceptance import (
    ScriptedAIProvider,
    ScriptedOCRProvider,
    answer_crops,
    grading_response,
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
#: 点数配置領域 / コメント配置候補領域. Detection reports answer areas only,
#: so these are the regions the reviewer draws by hand on the same sheet.
_SCORE_AREA = (0.70, 0.03, 0.90, 0.09)
_COMMENT_AREA = (0.05, 0.30, 0.90, 0.42)

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
    `NullOCRProvider`, which is what a host that has not configured an OCR
    service actually runs. The scenarios at the bottom of this module use
    that deliberately; everything above injects a scripted reader.

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


def _region(
    *,
    region_id: str,
    kind: str,
    label: str,
    page_index: int,
    bbox: tuple[float, float, float, float],
) -> dict[str, Any]:
    x0, y0, x1, y1 = bbox
    return {
        "region_id": region_id,
        "kind": kind,
        "page_index": page_index,
        "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        "label": label,
        "confirmed": False,
        "text": None,
    }


def _confirm_answer_layout(client: TestClient, test_id: str) -> None:
    """Issue #105: upload one answer sheet, detect the answer areas on it,
    add the 点数/コメント配置領域 by hand, and confirm.

    Detection reports answer areas and nothing else, so the other two kinds
    are the reviewer's own drawing -- which is also why this keeps the
    detected regions exactly as they came back rather than rebuilding them.
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

    regions: list[dict[str, Any]] = list(answer_areas)
    for number, page_index in _QUESTIONS:
        regions.append(
            _region(
                region_id=f"score-{number}",
                kind="score",
                label=number,
                page_index=page_index,
                bbox=_SCORE_AREA,
            )
        )
        regions.append(
            _region(
                region_id=f"comment-{number}",
                kind="annotation_area",
                label=number,
                page_index=page_index,
                bbox=_COMMENT_AREA,
            )
        )

    saved = client.put(f"/tests/{test_id}/profile", headers=_AUTH, json={"regions": regions})
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

    source = data_root / "submissions" / submission_id / "source.pdf"
    before = _digest(source.read_bytes())
    exported = _export(client, submission_id)
    output = data_root / exported["file_path"]
    assert output.exists() and output != source
    assert _digest(source.read_bytes()) == before, "the original PDF was modified"


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
# `create_app` installs `NullOCRProvider` when no OCR provider is injected,
# and that is what ships today: the chosen service (Google Document AI,
# business-rules-and-evaluation-data.md section 3 (A)) has no adapter yet.
# It reports every image as completely unrecognized at confidence 0.0, which
# is below any threshold, so **every** question comes back `usable=False`.
#
# The two tests below fix what that actually costs, rather than what it is
# hoped to cost. They are the current behaviour, not the desired one: Issue
# #114 is where changing it is decided. If it changes, these fail and say so.
def test_without_an_ocr_service_every_question_still_reaches_export_by_hand(
    data_root: Path,
    extractor: _ScriptedCriteriaExtractor,
    ai_provider: ScriptedAIProvider,
) -> None:
    """No OCR adapter, no dependencies between questions.

    Grading still runs and still produces a proposal for each question -- the
    AI provider is multimodal and is handed the crop itself, so an empty OCR
    reading does not stop it. What is lost is the automatic release: every
    question is `usable=False`, so nothing is ever auto-confirmed and the
    reviewer confirms all of them. The answer still reaches an exported PDF.
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
            assert job["usable"] is False, "a 0.0-confidence reading must release nothing"
            grades = client.get(
                f"/submissions/{submission_id}/questions/{question_id}/grades", headers=_AUTH
            ).json()
            assert grades, "the proposal must be kept for the reviewer, not discarded"

        _approve_every_question(client, test_id, submission_id)
        exported = _export(client, submission_id)
        assert (data_root / exported["file_path"]).exists()


def test_without_an_ocr_service_a_dependent_question_stays_blocked_until_a_human_resumes_it(
    data_root: Path,
    extractor: _ScriptedCriteriaExtractor,
    ai_provider: ScriptedAIProvider,
) -> None:
    """The same host, with one confirmed dependency 問1 -> 問2.

    `NullOCRProvider` makes 問1 unusable, and an unusable prerequisite is
    exactly what `evaluate_readiness` refuses to release a dependent on. So
    問2 never runs on its own: it stays BLOCKED, naming 問1. **On a host with
    no OCR service, every dependency edge stalls its downstream.** That is
    today's behaviour on the shipped configuration, and Issue #114 is where
    it is decided whether it stays.

    The way through it today is the reviewer's: `resume` marks the
    prerequisite usable, and the dependent runs immediately afterwards.
    """
    with _build_client(
        data_root, extractor=extractor, ai_provider=ai_provider, ocr_provider=None
    ) as client:
        test_id = _register_via_the_new_path(client, edges=True)
        submission_id = _upload_answer(client, test_id, marker="ans-d")
        _script_the_grader(ai_provider, answer_crops(data_root, submission_id))

        first, second = f"{test_id}:問1", f"{test_id}:問2"
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
