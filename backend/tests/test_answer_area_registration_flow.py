"""The gate this Issue exists to open: registration -> 回答欄 -> ``ready`` ->
an answer that is actually cropped per question (Issue #105 acceptance 8).

``complete-registration`` requires a **confirmed profile**, and
``intake_submission`` requires a ``ready`` test. Before this Issue the only
way to satisfy the first was a model-answer PDF that real material does not
have (Issue #95 decision 1), so no real test could ever accept an answer. This
walks the whole path with detection supplying the coordinates and asserts the
thing that actually matters at the end: the submission's answer image is a
*crop of the confirmed area*, not the whole page.

Everything the walk needs now comes from the endpoint that owns it. This
module was written while #101 and #103 were still unmerged, and stood in for
them by inserting `Question` rows and a CONFIRMED `DependencyGraph` straight
into the database; both are merged, so the substitution is gone and the
questions and the graph are produced by ``/criteria/*`` and
``/dependency-graph/*`` here (Issue #116). The 採点基準 is typed in rather
than extracted -- ``PUT /criteria`` is the hand-entry path Issue #95
決定 8 requires to exist, and using it means this module needs no scripted
extraction provider at all. The only external service substituted is the
answer-area detector.

The path this module walks is joined to grading, review and export in
`test_e2e_intake_to_export.py`; what it asserts on its own is the answer-area
half: the coordinates, and the ``ready`` gate they open.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url
from auto_scoring.domain.answer_area_detection import (
    AnswerAreaDetectionOutput,
    AnswerAreaDetectionRequest,
    parse_answer_area_detection,
)
from auto_scoring.domain.pdf_intake import IntakeLimits
from tests.support import written_on_pdf_bytes

_TOKEN = "answer-area-flow-token"

#: Where the answer sheet's single question is, as the detector will report it.
_AREA = (0.1, 0.25, 0.9, 0.55)


class _ScriptedDetector:
    """Reports one area for 問1, through the real parser."""

    name = "scripted"

    def detect(self, request: AnswerAreaDetectionRequest) -> AnswerAreaDetectionOutput:
        x0, y0, x1, y1 = _AREA
        return parse_answer_area_detection(
            json.dumps(
                {
                    "areas": [
                        {
                            "page": 1,
                            "question_number": "問1",
                            "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
                            "note": None,
                        }
                    ]
                }
            ),
            question_numbers=request.question_numbers,
            page_count=len(request.page_images),
        )


def _pdf_bytes(*, pages: int = 1, marker: bytes = b"") -> bytes:
    """An answer sheet with writing on it -- see `support.written_on_pdf_bytes`.

    ``marker`` distinguishes the answer being graded from the layout
    reference, so a duplicate-content check cannot conflate the two.
    """
    return written_on_pdf_bytes(
        pages=pages,
        width=595,
        height=842,
        metadata={"/Keywords": marker.decode()} if marker else None,
    )


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "app-data"


@pytest.fixture
def client(data_root: Path) -> TestClient:
    app = create_app(
        api_token=_TOKEN,
        data_root=data_root,
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
        answer_area_detector=_ScriptedDetector(),
    )
    return TestClient(app)


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TOKEN}"}


def _session_factory(data_root: Path) -> sessionmaker[Session]:
    return build_session_factory(create_sqlite_engine(sqlite_url(data_root / "database.sqlite")))


def _confirm_criteria(client: TestClient, test_id: str) -> None:
    """The test's one question, its points and its 採点基準, typed in by a
    reviewer and confirmed (Issue #103).

    This is what writes the `Question` row detection then reads: an answer
    area can only be assigned to a question that is already confirmed.
    """
    saved = client.put(
        f"/tests/{test_id}/criteria",
        headers=_auth(),
        json={
            "questions": [
                {
                    "number": "問1",
                    "points": 10,
                    "model_answer": "問1の模範解答",
                    "criteria": [{"description": "要点に触れている", "kind": "add", "points": 10}],
                    "source_pages": [],
                    "note": None,
                }
            ],
            "declared_total_points": 10,
        },
    )
    assert saved.status_code == 200, saved.text
    confirmed = client.post(
        f"/tests/{test_id}/criteria/confirm",
        headers=_auth(),
        json={"revision": saved.json()["revision"]},
    )
    assert confirmed.status_code == 200, confirmed.text


def _confirm_dependency_graph(client: TestClient, test_id: str) -> None:
    """The other half of the `ready` gate (Issue #26). One question, so the
    real analyzer has no edge to find and there is none to confirm."""
    analyzed = client.post(
        f"/tests/{test_id}/dependency-graph/analyze", headers=_auth(), json={"overrides": []}
    )
    assert analyzed.status_code == 200, analyzed.text
    confirmed = client.post(
        f"/tests/{test_id}/dependency-graph/confirm",
        headers=_auth(),
        json={"version": analyzed.json()["version"], "edges": []},
    )
    assert confirmed.status_code == 200, confirmed.text


def test_registration_reaches_ready_and_crops_each_answer_to_its_area(
    client: TestClient, data_root: Path
) -> None:
    # 1. A test exists. The folder import (Issue #101) is what produces this
    #    call in the app; the 採点基準PDF is its one required upload.
    created = client.post(
        "/tests",
        headers=_auth(),
        data={"name": "模擬 第1回"},
        files={"criteria": ("02_criteria.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert created.status_code == 201, created.text
    test_id = created.json()["id"]

    # 2. Its 配点と採点基準 are confirmed (Issue #103). The `Question` row
    #    that writes is what detection reads.
    _confirm_criteria(client, test_id)

    # 3. The reviewer picks one answer sheet and detects the answer areas.
    assert (
        client.put(
            f"/tests/{test_id}/answer-layout",
            headers=_auth(),
            files={"file": ("answer.pdf", _pdf_bytes(), "application/pdf")},
        ).status_code
        == 200
    )
    detected = client.post(f"/tests/{test_id}/answer-layout/detect", headers=_auth())
    assert detected.status_code == 200, detected.text
    body = detected.json()
    assert body["undetected_question_numbers"] == []
    assert body["unassigned_region_ids"] == []

    # 4. The reviewer confirms. The ANSWER_AREA is the one under test, kept
    #    exactly as detected; the points and the 採点基準 come from step 2.
    detected_area = next(region for region in body["regions"] if region["kind"] == "answer_area")
    saved = client.put(
        f"/tests/{test_id}/profile",
        headers=_auth(),
        json={"regions": [detected_area]},
    )
    assert saved.status_code == 200, saved.text
    confirmed = client.post(
        f"/tests/{test_id}/profile/confirm",
        headers=_auth(),
        json={"revision": saved.json()["revision"]},
    )
    assert confirmed.status_code == 200, confirmed.text

    # 5. The dependency graph -- the other half of the `ready` gate (Issue #26).
    _confirm_dependency_graph(client, test_id)

    # 6. The gate opens. This is the whole point of Issue #105: before it,
    #    `profile_confirmed` was unreachable for a real test.
    completed = client.post(f"/tests/{test_id}/complete-registration", headers=_auth())
    assert completed.status_code == 200, completed.text
    assert completed.json()["test"]["status"] == "ready"
    assert completed.json()["profile_confirmed"] is True

    # 7. An answer is accepted and cropped to the confirmed area -- not sent
    #    whole (simplified-design-specification.md §26.1.1), and not flagged
    #    `no_answer_area_defined`.
    submitted = client.post(
        f"/tests/{test_id}/submissions",
        headers=_auth(),
        files={"file": ("student.pdf", _pdf_bytes(marker=b"student-a"), "application/pdf")},
    )
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["state"] == "ai_processed"
    assert submitted.json()["review_reason"] is None

    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        question = uow.questions.list_for_test(test_id)[0]
        assert question.answer_area is not None
        assert question.answer_area.x == pytest.approx(_AREA[0])
        assert question.answer_area.width == pytest.approx(_AREA[2] - _AREA[0])


def test_one_confirmed_layout_serves_every_later_answer_of_that_test(
    client: TestClient, data_root: Path
) -> None:
    """Issue #105 acceptance 7, and the shape of it worth being precise about.

    There is no per-answer step: the confirmed area lives on the `Question`
    row, and `adapters.submission_intake` crops every submission of that test
    against it. Forty answers of one format cost exactly the same human work
    as one.

    What this does **not** show, and what nothing in this repository can show,
    is how well those coordinates fit a *different student's* sheet. The real
    material holds one answer per subject, so there is no second answer of the
    same test to measure against (Issue #105: 測れないことを測れると書かない).
    A sheet whose page count differs is caught -- `describe_coverage_issue`
    already routes that to ``needs_review`` -- but a differently laid out sheet
    of the same page count is not detected by anything here.
    """
    created = client.post(
        "/tests",
        headers=_auth(),
        data={"name": "模擬 第1回"},
        files={"criteria": ("02_criteria.pdf", _pdf_bytes(), "application/pdf")},
    )
    test_id = created.json()["id"]
    _confirm_criteria(client, test_id)

    client.put(
        f"/tests/{test_id}/answer-layout",
        headers=_auth(),
        files={"file": ("answer.pdf", _pdf_bytes(), "application/pdf")},
    )
    body = client.post(f"/tests/{test_id}/answer-layout/detect", headers=_auth()).json()
    saved = client.put(
        f"/tests/{test_id}/profile",
        headers=_auth(),
        json={"regions": [next(r for r in body["regions"] if r["kind"] == "answer_area")]},
    )
    client.post(
        f"/tests/{test_id}/profile/confirm",
        headers=_auth(),
        json={"revision": saved.json()["revision"]},
    )
    _confirm_dependency_graph(client, test_id)
    client.post(f"/tests/{test_id}/complete-registration", headers=_auth())

    # Three different students, one confirmed layout, no further human step.
    for student in (b"student-a", b"student-b", b"student-c"):
        response = client.post(
            f"/tests/{test_id}/submissions",
            headers=_auth(),
            files={"file": ("student.pdf", _pdf_bytes(marker=student), "application/pdf")},
        )
        assert response.status_code == 201, response.text
        assert response.json()["state"] == "ai_processed"

    # A sheet with an extra page is *not* silently cropped with page 1's
    # coordinates -- the existing page-coverage check routes it to review.
    odd_one_out = client.post(
        f"/tests/{test_id}/submissions",
        headers=_auth(),
        files={
            "file": ("student.pdf", _pdf_bytes(pages=2, marker=b"student-d"), "application/pdf")
        },
    )
    assert odd_one_out.status_code == 201, odd_one_out.text
    assert odd_one_out.json()["state"] == "needs_review"
    assert "extra_pages" in odd_one_out.json()["review_reason"]
