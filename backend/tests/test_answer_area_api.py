"""API-level tests for 回答欄 detection and the confirm gate it adds
(Issue #105).

**Where the confirmed questions come from.** Detection offers the reviewer a
choice between this test's confirmed question numbers, which are the
`Question` rows. Since Issue #103 those rows are created by
``/criteria/confirm`` from the human-confirmed 採点基準 draft -- a router this
branch does not have yet (merge order: #101 -> #103 -> #105). These tests
therefore write the rows straight through `SqlAlchemyUnitOfWork`, which is
exactly what that endpoint does, and keeps the detection path testable
against the seam it actually depends on (`uow.questions.list_for_test`)
rather than against one Issue's particular way of filling it.

Every fixture is synthetic: blank PDFs and invented question numbers. No part
of the real material appears here (Issue #105 acceptance 9).
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pypdf import PdfWriter
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url
from auto_scoring.domain.ai_provider import ProviderUnavailable, SchemaViolation
from auto_scoring.domain.answer_area_detection import (
    UNASSIGNED_QUESTION_LABEL,
    AnswerAreaDetectionOutput,
    AnswerAreaDetectionRequest,
    UnconfiguredAnswerAreaDetector,
    parse_answer_area_detection,
)
from auto_scoring.domain.models import Question
from auto_scoring.domain.pdf_intake import IntakeLimits

_TOKEN = "answer-area-token"


class _FakeDetector:
    """Answers with a canned JSON body, parsed through the very same
    `parse_answer_area_detection` a real adapter uses.

    Not a stub returning `AnswerAreaDetectionOutput` objects directly: the
    thing worth testing is that a provider's *text* survives (or fails)
    validation, and a fake that skips the parser would pass a response the
    real adapters reject. The `ValidationError` -> `SchemaViolation`
    conversion is copied from them for the same reason -- that is the
    exception the port declares, and the router only handles what the port
    declares.
    """

    name = "fake"

    def __init__(self, body: str | Exception) -> None:
        self._body = body
        self.requests: list[AnswerAreaDetectionRequest] = []

    def set_body(self, body: str | Exception) -> None:
        """Answer differently on the next call -- what a re-run after a
        provider failure looks like from the router's side."""
        self._body = body

    def detect(self, request: AnswerAreaDetectionRequest) -> AnswerAreaDetectionOutput:
        self.requests.append(request)
        if isinstance(self._body, Exception):
            raise self._body
        try:
            return parse_answer_area_detection(
                self._body,
                question_numbers=request.question_numbers,
                page_count=len(request.page_images),
                boxes_per_page=[len(boxes) for boxes in request.page_boxes],
            )
        except ValidationError:
            raise SchemaViolation("fake response failed schema validation") from None


def _pdf_bytes(*, pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _detection_body(*areas: dict[str, object], absent: list[str] | None = None) -> str:
    return json.dumps({"areas": list(areas), "questions_not_on_these_pages": absent or []})


def _area(
    *,
    page: int = 1,
    number: str = "問1",
    bbox: tuple[float, float, float, float] = (0.1, 0.2, 0.6, 0.4),
    note: str | None = None,
) -> dict[str, object]:
    x0, y0, x1, y1 = bbox
    return {
        "page": page,
        "question_number": number,
        "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        "note": note,
    }


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "app-data"


@pytest.fixture
def detector() -> _FakeDetector:
    return _FakeDetector(_detection_body(_area()))


@pytest.fixture
def client(data_root: Path, detector: _FakeDetector) -> TestClient:
    app = create_app(
        api_token=_TOKEN,
        data_root=data_root,
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
        answer_area_detector=detector,
    )
    return TestClient(app)


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TOKEN}"}


def _session_factory(data_root: Path) -> sessionmaker[Session]:
    return build_session_factory(create_sqlite_engine(sqlite_url(data_root / "database.sqlite")))


def _register_test(client: TestClient) -> str:
    """Register a test the way Issue #101 does it: the 採点基準PDF and nothing
    else.

    Deliberately **no** ``reference`` material -- that is the state every real
    test is in (there is no model-answer PDF), and it is the state in which
    `analyze_profile` answers 409 and the 回答欄 path is the only way to a
    confirmed profile.
    """
    response = client.post(
        "/tests",
        headers=_auth(),
        data={"name": "模擬 第1回", "subject": "模擬"},
        files={"criteria": ("02_criteria.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]  # type: ignore[no-any-return]


def _confirm_questions(data_root: Path, test_id: str, *numbers: str) -> None:
    """Stand in for ``/criteria/confirm`` -- see the module docstring."""
    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        for index, number in enumerate(numbers):
            uow.questions.add(
                Question(
                    id=f"{test_id}:{number}",
                    test_id=test_id,
                    number=number,
                    page=1,
                    points=5 + index,
                )
            )
        uow.commit()


def _upload_layout(client: TestClient, test_id: str, *, pages: int = 1) -> Any:
    return client.put(
        f"/tests/{test_id}/answer-layout",
        headers=_auth(),
        files={"file": ("answer.pdf", _pdf_bytes(pages=pages), "application/pdf")},
    )


def _detect(client: TestClient, test_id: str) -> Any:
    return client.post(f"/tests/{test_id}/answer-layout/detect", headers=_auth())


class TestAnswerLayoutUpload:
    def test_reports_no_sheet_before_one_is_uploaded(self, client: TestClient) -> None:
        """`null`, not `0`: "not uploaded" and "uploaded, zero pages" are
        different things, and no PDF has zero pages.
        """
        test_id = _register_test(client)
        body = client.get(f"/tests/{test_id}/answer-layout", headers=_auth()).json()
        assert body["page_count"] is None

    def test_stores_the_sheet_and_reports_its_page_count(self, client: TestClient) -> None:
        test_id = _register_test(client)
        response = _upload_layout(client, test_id, pages=3)
        assert response.status_code == 200, response.text
        assert response.json()["page_count"] == 3

    def test_serves_the_stored_sheet_back(self, client: TestClient) -> None:
        """The overlay editor draws on this. Served as a PDF, not as page
        images, because the app already renders PDFs and places normalized
        overlays on them.
        """
        test_id = _register_test(client)
        _upload_layout(client, test_id)
        response = client.get(f"/tests/{test_id}/answer-layout/pdf", headers=_auth())
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")

    def test_serving_a_missing_sheet_is_404(self, client: TestClient) -> None:
        test_id = _register_test(client)
        response = client.get(f"/tests/{test_id}/answer-layout/pdf", headers=_auth())
        assert response.status_code == 404

    def test_rejects_a_non_pdf(self, client: TestClient) -> None:
        test_id = _register_test(client)
        response = client.put(
            f"/tests/{test_id}/answer-layout",
            headers=_auth(),
            files={"file": ("answer.pdf", b"not a pdf at all", "application/pdf")},
        )
        assert response.status_code == 400

    def test_a_corrupt_upload_does_not_destroy_the_stored_sheet(
        self, client: TestClient, data_root: Path
    ) -> None:
        """The current answer areas were drawn on the stored sheet. Losing it
        to a bad upload would leave a profile whose coordinates refer to a
        page nobody can see any more.
        """
        test_id = _register_test(client)
        _upload_layout(client, test_id, pages=2)
        before = (data_root / "tests" / test_id / "answer-layout.pdf").read_bytes()

        response = client.put(
            f"/tests/{test_id}/answer-layout",
            headers=_auth(),
            files={"file": ("answer.pdf", b"%PDF-1.4 truncated", "application/pdf")},
        )
        assert response.status_code == 400
        assert (data_root / "tests" / test_id / "answer-layout.pdf").read_bytes() == before

    def test_replaces_the_previous_sheet(self, client: TestClient) -> None:
        test_id = _register_test(client)
        _upload_layout(client, test_id, pages=1)
        assert _upload_layout(client, test_id, pages=3).json()["page_count"] == 3

    def test_uploading_a_sheet_creates_the_profile_to_draw_on(self, client: TestClient) -> None:
        """A test registered without a model-answer PDF has no profile at all,
        and with no profile there is no page format to place a region on --
        so "領域を手動追加" had nothing to add to and the manual path was
        unreachable (Issue #105 review round 1, P1).

        Uploading the sheet *is* the act of saying which document the
        coordinates are for, so it is where the profile starts existing.
        """
        test_id = _register_test(client)
        assert client.get(f"/tests/{test_id}/profile", headers=_auth()).status_code == 404

        _upload_layout(client, test_id, pages=2)

        profile = client.get(f"/tests/{test_id}/profile", headers=_auth())
        assert profile.status_code == 200, profile.text
        body = profile.json()
        assert body["status"] == "draft"
        assert body["regions"] == []
        assert len(body["pages"]) == 2

    def test_the_manual_path_works_with_no_detection_at_all(self, client: TestClient) -> None:
        """The whole point of the profile existing after an upload: a host
        with no image-capable provider, or a reviewer who would rather draw
        the boxes, must be able to get from a fresh test to a saved region set
        without calling a provider once.
        """
        test_id = _register_test(client)
        _upload_layout(client, test_id)
        saved = client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={
                "regions": [
                    {
                        "region_id": "manual-0",
                        "kind": "answer_area",
                        "page_index": 0,
                        "bbox": {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.4},
                        "label": "問1",
                        "confirmed": False,
                        "text": None,
                    }
                ]
            },
        )
        assert saved.status_code == 200, saved.text

    def test_replacing_the_sheet_bumps_the_revision(self, client: TestClient) -> None:
        """The regions are coordinates *on this sheet*, so swapping the sheet
        changes what every one of them means. A confirm pinned to a revision
        reviewed against the old sheet has to be rejected as stale.
        """
        test_id = _register_test(client)
        _upload_layout(client, test_id)
        before = client.get(f"/tests/{test_id}/profile", headers=_auth()).json()["revision"]

        _upload_layout(client, test_id)
        after = client.get(f"/tests/{test_id}/profile", headers=_auth()).json()["revision"]
        assert after > before

        stale = client.post(
            f"/tests/{test_id}/profile/confirm", headers=_auth(), json={"revision": before}
        )
        assert stale.status_code == 409

    def test_a_shorter_sheet_reports_the_regions_it_cannot_keep(
        self, client: TestClient, data_root: Path
    ) -> None:
        """Regions on a page the new sheet does not have cannot be
        reinterpreted -- but they were somebody's work, so the count comes
        back rather than vanishing.
        """
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1")
        _upload_layout(client, test_id, pages=2)
        saved = client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={
                "regions": [
                    {
                        "region_id": f"manual-{page}",
                        "kind": "answer_area",
                        "page_index": page,
                        "bbox": {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.4},
                        "label": "問1",
                        "confirmed": False,
                        "text": None,
                    }
                    for page in (0, 1)
                ]
            },
        )
        assert saved.status_code == 200, saved.text

        replaced = _upload_layout(client, test_id, pages=1)
        assert replaced.json()["dropped_region_count"] == 1
        kept = client.get(f"/tests/{test_id}/profile", headers=_auth()).json()
        assert [r["page_index"] for r in kept["regions"]] == [0]

    def test_a_confirmed_profile_freezes_its_answer_sheet_too(
        self, client: TestClient, data_root: Path
    ) -> None:
        """Otherwise the sheet a finished test was confirmed against could be
        swapped afterwards, leaving confirmed coordinates pointing at a
        document nobody reviewed.
        """
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1")
        _upload_layout(client, test_id)
        detected = _detect(client, test_id).json()
        saved = client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={
                "regions": [
                    *detected["regions"],
                    {
                        "region_id": "question-1",
                        "kind": "question",
                        "page_index": 0,
                        "bbox": {"x0": 0.0, "y0": 0.0, "x1": 0.4, "y1": 0.1},
                        "label": "問1",
                        "confirmed": False,
                        "text": "問1",
                    },
                    {
                        "region_id": "score-1",
                        "kind": "score",
                        "page_index": 0,
                        "bbox": {"x0": 0.8, "y0": 0.0, "x1": 0.9, "y1": 0.1},
                        "label": "問1",
                        "confirmed": False,
                        "text": "5点",
                    },
                ]
            },
        ).json()
        client.post(
            f"/tests/{test_id}/profile/confirm",
            headers=_auth(),
            json={"revision": saved["revision"]},
        )

        response = _upload_layout(client, test_id)
        assert response.status_code == 409
        assert "confirmed" in response.json()["detail"]

    def test_requires_auth(self, client: TestClient) -> None:
        test_id = _register_test(client)
        response = client.put(
            f"/tests/{test_id}/answer-layout",
            files={"file": ("answer.pdf", _pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 401


class TestDetection:
    def test_saves_the_detected_areas_as_draft_regions(
        self, client: TestClient, data_root: Path
    ) -> None:
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1", "問2")
        _upload_layout(client, test_id)

        body = _detect(client, test_id).json()
        assert body["status"] == "draft"
        assert [(r["kind"], r["label"]) for r in body["regions"]] == [("answer_area", "問1")]
        assert all(r["confirmed"] is False for r in body["regions"])

    def test_offers_the_confirmed_questions_as_the_only_choices(
        self, client: TestClient, data_root: Path, detector: _FakeDetector
    ) -> None:
        """Issue #105 acceptance 3: the attribution is a multiple-choice
        question over this test's own question set.
        """
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1", "問2")
        _upload_layout(client, test_id)
        _detect(client, test_id)
        assert detector.requests[0].question_numbers == ("問1", "問2")

    def test_sends_every_page_of_the_sheet(
        self, client: TestClient, data_root: Path, detector: _FakeDetector
    ) -> None:
        """Detection is the one call that sends whole pages, and it sends all
        of them -- a question can be on any page (simplified-design-spec
        §26.1.1).
        """
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1")
        _upload_layout(client, test_id, pages=3)
        _detect(client, test_id)
        assert len(detector.requests[0].page_images) == 3

    def test_reports_which_questions_were_not_found(
        self, client: TestClient, data_root: Path
    ) -> None:
        """Issue #105 acceptance 4 -- never silently dropped."""
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1", "問2", "問3")
        _upload_layout(client, test_id)
        body = _detect(client, test_id).json()
        assert body["undetected_question_numbers"] == ["問2", "問3"]

    def test_reports_a_box_with_no_question(
        self, client: TestClient, data_root: Path, detector: _FakeDetector
    ) -> None:
        detector._body = _detection_body(
            _area(number=UNASSIGNED_QUESTION_LABEL, note="どの設問か読み取れない")
        )
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1")
        _upload_layout(client, test_id)
        body = _detect(client, test_id).json()
        assert len(body["unassigned_region_ids"]) == 1

    def test_a_malformed_response_saves_nothing(
        self, client: TestClient, data_root: Path, detector: _FakeDetector
    ) -> None:
        """Issue #105 acceptance 5. Half a detection is worse than none: on the
        overlay, a partial region set looks exactly like a complete one.
        """
        detector._body = '{"areas": [{"page": 1, "question_number": "問9"}]}'
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1")
        _upload_layout(client, test_id)

        assert _detect(client, test_id).status_code == 502
        # The profile itself exists (uploading the sheet created it), so what
        # has to be empty is its *regions* -- a partially-applied detection
        # looks exactly like a complete one on the overlay.
        assert client.get(f"/tests/{test_id}/profile", headers=_auth()).json()["regions"] == []

    def test_an_unreachable_provider_is_503_and_saves_nothing(
        self, client: TestClient, data_root: Path, detector: _FakeDetector
    ) -> None:
        detector._body = ProviderUnavailable("provider request timed out")
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1")
        _upload_layout(client, test_id)

        assert _detect(client, test_id).status_code == 503
        assert client.get(f"/tests/{test_id}/profile", headers=_auth()).json()["regions"] == []

    def test_a_schema_violation_is_502(
        self, client: TestClient, data_root: Path, detector: _FakeDetector
    ) -> None:
        detector._body = SchemaViolation("provider response failed schema validation")
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1")
        _upload_layout(client, test_id)
        assert _detect(client, test_id).status_code == 502

    def test_stops_when_no_questions_are_confirmed(
        self, client: TestClient, detector: _FakeDetector
    ) -> None:
        """A multiple-choice question with no choices is not one -- and a free
        text answer would invent a question number matching no allocation.
        """
        test_id = _register_test(client)
        _upload_layout(client, test_id)
        response = _detect(client, test_id)
        assert response.status_code == 409
        assert detector.requests == []

    def test_stops_when_no_answer_sheet_is_stored(
        self, client: TestClient, data_root: Path, detector: _FakeDetector
    ) -> None:
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1")
        assert _detect(client, test_id).status_code == 409
        assert detector.requests == []

    def test_can_be_run_again_and_bumps_the_revision(
        self, client: TestClient, data_root: Path
    ) -> None:
        """Re-running after a provider failure is normal. The bumped revision
        invalidates a confirm pinned to the previous region set, exactly as
        `analyze`/`PUT /profile` do.
        """
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1")
        _upload_layout(client, test_id)
        first = _detect(client, test_id).json()["revision"]
        assert _detect(client, test_id).json()["revision"] == first + 1

    def test_keeps_a_hand_drawn_region_of_another_kind(
        self, client: TestClient, data_root: Path
    ) -> None:
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1")
        _upload_layout(client, test_id)
        detected = _detect(client, test_id).json()
        manual = {
            "region_id": "manual-question",
            "kind": "question",
            "page_index": 0,
            "bbox": {"x0": 0.0, "y0": 0.0, "x1": 0.4, "y1": 0.1},
            "label": "問1",
            "confirmed": False,
            "text": "問1",
        }
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": [*detected["regions"], manual]},
        )

        again = _detect(client, test_id).json()
        assert any(r["region_id"] == "manual-question" for r in again["regions"])

    def test_is_refused_once_the_profile_is_confirmed(
        self, client: TestClient, data_root: Path
    ) -> None:
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1")
        _upload_layout(client, test_id)
        detected = _detect(client, test_id).json()
        # A confirmable region set needs a score the region path can read,
        # since this branch has no 採点基準 draft to take one from.
        regions = [
            *detected["regions"],
            {
                "region_id": "question-1",
                "kind": "question",
                "page_index": 0,
                "bbox": {"x0": 0.0, "y0": 0.0, "x1": 0.4, "y1": 0.1},
                "label": "問1",
                "confirmed": False,
                "text": "問1",
            },
            {
                "region_id": "score-1",
                "kind": "score",
                "page_index": 0,
                "bbox": {"x0": 0.8, "y0": 0.0, "x1": 0.9, "y1": 0.1},
                "label": "問1",
                "confirmed": False,
                "text": "5点",
            },
        ]
        saved = client.put(
            f"/tests/{test_id}/profile", headers=_auth(), json={"regions": regions}
        ).json()
        confirmed = client.post(
            f"/tests/{test_id}/profile/confirm",
            headers=_auth(),
            json={"revision": saved["revision"]},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert _detect(client, test_id).status_code == 409

    def test_says_why_detection_is_unavailable_without_failing_the_screen(
        self, data_root: Path
    ) -> None:
        """A host with no image-capable provider must still open the screen and
        let the reviewer draw the boxes by hand -- that is the documented
        fallback, not an error state.
        """
        app = create_app(
            api_token=_TOKEN,
            data_root=data_root,
            answer_area_detector=UnconfiguredAnswerAreaDetector(
                "AUTO_SCORING_AI_GRADING_TRANSPORT に画像を送れる provider がありません"
            ),
        )
        client = TestClient(app)
        test_id = _register_test(client)
        body = client.get(f"/tests/{test_id}/answer-layout", headers=_auth()).json()
        assert body["detection_available"] is False
        assert "AUTO_SCORING_AI_GRADING_TRANSPORT" in body["detection_unavailable_reason"]

        _confirm_questions(data_root, test_id, "問1")
        _upload_layout(client, test_id)
        assert _detect(client, test_id).status_code == 503


class TestConfirmGate:
    def test_an_unassigned_box_blocks_the_confirm(
        self, client: TestClient, data_root: Path, detector: _FakeDetector
    ) -> None:
        """`build_questions_and_rubrics` ignores a region whose label matches
        no question, so without this the model would have found a box, nobody
        would have assigned it, and it would vanish.
        """
        detector._body = _detection_body(_area(number=UNASSIGNED_QUESTION_LABEL))
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1")
        _upload_layout(client, test_id)
        saved = _detect(client, test_id).json()

        response = client.post(
            f"/tests/{test_id}/profile/confirm",
            headers=_auth(),
            json={"revision": saved["revision"]},
        )
        assert response.status_code == 422
        assert "assign" in response.json()["detail"]

    def test_an_undetected_question_does_not_block_the_confirm(
        self, client: TestClient, data_root: Path
    ) -> None:
        """Deliberately unlike Issue #103's unknown 配点.

        An unknown score confirmed anyway is a silently wrong
        ``Question.points`` nobody ever sees. A question with no answer area
        is sent to grading as the whole page and marked
        ``no_answer_area_defined`` -- it fails loudly, in front of a human.
        Stop what goes wrong quietly; let through what goes wrong loudly.
        """
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1", "問2")
        _upload_layout(client, test_id)
        detected = _detect(client, test_id).json()
        assert detected["undetected_question_numbers"] == ["問2"]

        regions = [
            *detected["regions"],
            {
                "region_id": "question-1",
                "kind": "question",
                "page_index": 0,
                "bbox": {"x0": 0.0, "y0": 0.0, "x1": 0.4, "y1": 0.1},
                "label": "問1",
                "confirmed": False,
                "text": "問1",
            },
            {
                "region_id": "score-1",
                "kind": "score",
                "page_index": 0,
                "bbox": {"x0": 0.8, "y0": 0.0, "x1": 0.9, "y1": 0.1},
                "label": "問1",
                "confirmed": False,
                "text": "5点",
            },
        ]
        saved = client.put(
            f"/tests/{test_id}/profile", headers=_auth(), json={"regions": regions}
        ).json()
        assert saved["undetected_question_numbers"] == ["問2"]

        response = client.post(
            f"/tests/{test_id}/profile/confirm",
            headers=_auth(),
            json={"revision": saved["revision"]},
        )
        assert response.status_code == 200, response.text

    def test_a_question_split_across_pages_says_what_to_do_about_it(
        self, client: TestClient, data_root: Path, detector: _FakeDetector
    ) -> None:
        """Measured, not hypothetical: one of the 11 real subjects prints one
        question's answer space across two pages ("その1"/"その2").

        `Question` holds one page and one rect, so this app cannot represent
        that question yet. Detection deliberately reports the areas on *both*
        pages rather than dropping half a student's answer -- so the reviewer
        meets this error, and it has to name the problem and the way out, not
        just restate the invariant.
        """
        detector._body = _detection_body(_area(page=1), _area(page=2))
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1")
        _upload_layout(client, test_id, pages=2)
        detected = _detect(client, test_id).json()
        assert len(detected["regions"]) == 2

        regions = [
            *detected["regions"],
            {
                "region_id": "question-1",
                "kind": "question",
                "page_index": 0,
                "bbox": {"x0": 0.0, "y0": 0.0, "x1": 0.4, "y1": 0.1},
                "label": "問1",
                "confirmed": False,
                "text": "問1",
            },
            {
                "region_id": "score-1",
                "kind": "score",
                "page_index": 0,
                "bbox": {"x0": 0.8, "y0": 0.0, "x1": 0.9, "y1": 0.1},
                "label": "問1",
                "confirmed": False,
                "text": "5点",
            },
        ]
        saved = client.put(
            f"/tests/{test_id}/profile", headers=_auth(), json={"regions": regions}
        ).json()
        response = client.post(
            f"/tests/{test_id}/profile/confirm",
            headers=_auth(),
            json={"revision": saved["revision"]},
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "複数ページにまたがっています" in detail
        assert "1ページ分しか扱えません" in detail
        # Names the way out, not only the rule.
        assert "残して" in detail

    def test_the_profile_response_always_carries_the_question_choices(
        self, client: TestClient, data_root: Path
    ) -> None:
        """The dropdown's options and the undetected list are derived on every
        response rather than stored, so an edit cannot leave them stale.
        """
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1", "問2")
        _upload_layout(client, test_id)
        _detect(client, test_id)
        body = client.get(f"/tests/{test_id}/profile", headers=_auth()).json()
        assert body["question_numbers"] == ["問1", "問2"]
        assert body["undetected_question_numbers"] == ["問2"]


class TestMissingQuestionsAreSplitByCause:
    """Issue #164. A blank fixture page has no printed box, so detection can
    only ever report a rectangle here -- which is the point: what varies is
    what the model *said* about the questions it did not locate."""

    def test_a_question_reported_absent_is_listed_apart_from_an_undetected_one(
        self, client: TestClient, data_root: Path, detector: _FakeDetector
    ) -> None:
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1", "問2", "問3")
        _upload_layout(client, test_id)
        detector.set_body(_detection_body(_area(number="問1"), absent=["問3"]))

        body = _detect(client, test_id).json()

        assert body["undetected_question_numbers"] == ["問2"]
        assert body["absent_question_numbers"] == ["問3"]

    def test_the_split_survives_a_save_and_reload(
        self, client: TestClient, data_root: Path, detector: _FakeDetector
    ) -> None:
        """It is stored, so a reviewer who comes back to the screen must see
        the same two lists -- otherwise the question silently changes from
        "the paper has no space for this" to "go and draw it"."""
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1", "問2")
        _upload_layout(client, test_id)
        detector.set_body(_detection_body(_area(number="問1"), absent=["問2"]))
        _detect(client, test_id)

        body = client.get(f"/tests/{test_id}/profile", headers=_auth()).json()

        assert body["absent_question_numbers"] == ["問2"]

    def test_drawing_the_box_anyway_takes_it_out_of_both_lists(
        self, client: TestClient, data_root: Path, detector: _FakeDetector
    ) -> None:
        """The reviewer can see the page and the model cannot be right about
        everything. Derived on every read, so nothing has to be un-stored."""
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1", "問2")
        _upload_layout(client, test_id)
        detector.set_body(_detection_body(_area(number="問1"), absent=["問2"]))
        detected = _detect(client, test_id).json()

        saved = client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={
                "regions": [
                    *detected["regions"],
                    {
                        "region_id": "drawn-by-hand",
                        "kind": "answer_area",
                        "page_index": 0,
                        "bbox": {"x0": 0.1, "y0": 0.5, "x1": 0.6, "y1": 0.7},
                        "label": "問2",
                        "confirmed": False,
                        "text": None,
                    },
                ]
            },
        ).json()

        assert saved["absent_question_numbers"] == []
        assert saved["undetected_question_numbers"] == []

    def test_a_rerun_replaces_what_the_previous_run_said(
        self, client: TestClient, data_root: Path, detector: _FakeDetector
    ) -> None:
        """Re-running detection after a provider failure is a normal thing to
        do, and a question the previous run called absent may be one this run
        finds. Merging the two would keep the older claim alive forever."""
        test_id = _register_test(client)
        _confirm_questions(data_root, test_id, "問1", "問2")
        _upload_layout(client, test_id)
        detector.set_body(_detection_body(_area(number="問1"), absent=["問2"]))
        _detect(client, test_id)

        detector.set_body(_detection_body(_area(number="問2"), absent=["問1"]))
        body = _detect(client, test_id).json()

        assert body["absent_question_numbers"] == ["問1"]
