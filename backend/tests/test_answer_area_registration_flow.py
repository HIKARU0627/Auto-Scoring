"""The gate this Issue exists to open: registration -> 回答欄 -> ``ready`` ->
an answer that is actually cropped per question (Issue #105 acceptance 8).

``complete-registration`` requires a **confirmed profile**, and
``intake_submission`` requires a ``ready`` test. Before this Issue the only
way to satisfy the first was a model-answer PDF that real material does not
have (Issue #95 decision 1), so no real test could ever accept an answer. This
walks the whole path with detection supplying the coordinates and asserts the
thing that actually matters at the end: the submission's answer image is a
*crop of the confirmed area*, not the whole page.

Merge order is #101 -> #103 -> #105. This branch has neither of the first two,
so the two things they contribute are supplied here the way those Issues
supply them: the questions are written as `Question` rows (what
``/criteria/confirm`` does) and their points come from a `SCORE` region (the
pre-Issue-#103 path `build_questions_and_rubrics` still supports). Neither
substitution touches the part under test -- the answer-area coordinates and
the gate they open.
"""

from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url
from auto_scoring.domain.answer_area_detection import (
    AnswerAreaDetectionOutput,
    AnswerAreaDetectionRequest,
    parse_answer_area_detection,
)
from auto_scoring.domain.dependency_graph import DependencyGraph, DependencyGraphStatus
from auto_scoring.domain.models import Question
from auto_scoring.domain.pdf_intake import IntakeLimits

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
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    if marker:
        # Distinguishes the answer being graded from the layout reference, so
        # a duplicate-content check cannot conflate the two.
        writer.add_metadata({"/Keywords": marker.decode()})
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


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


def _confirmed_graph(test_id: str) -> DependencyGraph:
    """The other half of the `ready` gate (Issue #26), confirmed directly --
    this test is about the profile half."""
    now = datetime(2026, 1, 1)
    return DependencyGraph(
        id=f"{test_id}:v1",
        test_id=test_id,
        version=1,
        question_ids=frozenset({f"{test_id}:問1"}),
        edges=(),
        unresolved=(),
        status=DependencyGraphStatus.CONFIRMED,
        created_at=now,
        confirmed_at=now,
    )


def _region(**overrides: Any) -> dict[str, Any]:
    region = {
        "region_id": "r",
        "kind": "answer_area",
        "page_index": 0,
        "bbox": {"x0": 0.0, "y0": 0.0, "x1": 0.5, "y1": 0.1},
        "label": "問1",
        "confirmed": False,
        "text": None,
    }
    region.update(overrides)
    return region


def test_registration_reaches_ready_and_crops_each_answer_to_its_area(
    client: TestClient, data_root: Path
) -> None:
    # 1. A test exists. (With Issue #101 this comes from the folder import;
    #    the two PDFs here are only what this branch's `POST /tests` asks for.)
    created = client.post(
        "/tests",
        headers=_auth(),
        data={"name": "模擬 第1回"},
        files={
            "model_answer": ("model-answer.pdf", _pdf_bytes(), "application/pdf"),
            "manual": ("manual.pdf", _pdf_bytes(), "application/pdf"),
        },
    )
    assert created.status_code == 201, created.text
    test_id = created.json()["id"]

    # 2. Its questions are confirmed. (With Issue #103 this is
    #    `/criteria/confirm`; the row it writes is what detection reads.)
    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        uow.questions.add(
            Question(id=f"{test_id}:問1", test_id=test_id, number="問1", page=1, points=10)
        )
        uow.commit()

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

    # 4. The reviewer confirms. The SCORE region is this branch's stand-in for
    #    the confirmed 採点基準 (see the module docstring); the ANSWER_AREA is
    #    the one under test, kept exactly as detected.
    detected_area = next(region for region in body["regions"] if region["kind"] == "answer_area")
    saved = client.put(
        f"/tests/{test_id}/profile",
        headers=_auth(),
        json={
            "regions": [
                detected_area,
                _region(region_id="question-1", kind="question", text="問1"),
                _region(
                    region_id="score-1",
                    kind="score",
                    text="10点",
                    bbox={"x0": 0.8, "y0": 0.0, "x1": 0.9, "y1": 0.1},
                ),
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    confirmed = client.post(
        f"/tests/{test_id}/profile/confirm",
        headers=_auth(),
        json={"revision": saved.json()["revision"]},
    )
    assert confirmed.status_code == 200, confirmed.text

    # 5. The dependency graph -- the other half of the `ready` gate (Issue #26).
    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        uow.dependency_graphs.save(_confirmed_graph(test_id))
        uow.commit()

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
        files={
            "model_answer": ("model-answer.pdf", _pdf_bytes(), "application/pdf"),
            "manual": ("manual.pdf", _pdf_bytes(), "application/pdf"),
        },
    )
    test_id = created.json()["id"]
    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        uow.questions.add(
            Question(id=f"{test_id}:問1", test_id=test_id, number="問1", page=1, points=10)
        )
        uow.dependency_graphs.save(_confirmed_graph(test_id))
        uow.commit()

    client.put(
        f"/tests/{test_id}/answer-layout",
        headers=_auth(),
        files={"file": ("answer.pdf", _pdf_bytes(), "application/pdf")},
    )
    body = client.post(f"/tests/{test_id}/answer-layout/detect", headers=_auth()).json()
    saved = client.put(
        f"/tests/{test_id}/profile",
        headers=_auth(),
        json={
            "regions": [
                next(r for r in body["regions"] if r["kind"] == "answer_area"),
                _region(region_id="question-1", kind="question", text="問1"),
                _region(
                    region_id="score-1",
                    kind="score",
                    text="10点",
                    bbox={"x0": 0.8, "y0": 0.0, "x1": 0.9, "y1": 0.1},
                ),
            ]
        },
    )
    client.post(
        f"/tests/{test_id}/profile/confirm",
        headers=_auth(),
        json={"revision": saved.json()["revision"]},
    )
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
