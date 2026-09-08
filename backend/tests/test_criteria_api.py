"""API-level tests for 配点と採点基準 (Issue #103).

Drives the four endpoints against a real app, a real SQLite file and a real
`LocalFileStore`, with a fake `CriteriaExtractor` standing in for the model
so the same input always produces the same output. Real extraction is
non-deterministic by nature (Issue #95 recorded that as the reason human
review is mandatory), so what is pinned here is everything *around* the
model: the 不明 gate, what a malformed response does, and the
`Question`/`Rubric` rows a confirm produces.

Every fixture is synthetic (Issue #103 acceptance criterion 8).
"""

from __future__ import annotations

import threading
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.criteria_extraction.source import MAX_CRITERIA_PAGES
from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url
from auto_scoring.domain.ai_provider import ProviderUnavailable, SchemaViolation
from auto_scoring.domain.criteria_extraction import (
    CriteriaExtractionOutput,
    CriteriaExtractionRequest,
    CriterionKind,
    ExtractedCriterionOutput,
    ExtractedQuestionOutput,
)
from auto_scoring.domain.models import ScoringMethod
from auto_scoring.domain.pdf_intake import IntakeLimits

_TOKEN = "criteria-token"


class _FakeExtractor:
    """Returns a canned result, or raises whatever it was told to raise."""

    name = "fake"

    def __init__(
        self, output: CriteriaExtractionOutput | None = None, error: Exception | None = None
    ) -> None:
        self.output = output or CriteriaExtractionOutput()
        self.error = error
        self.requests: list[CriteriaExtractionRequest] = []

    def extract(self, request: CriteriaExtractionRequest) -> CriteriaExtractionOutput:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.output


def _pdf_bytes(*, pages: int = 2) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TOKEN}"}


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "app-data"


@pytest.fixture
def extractor() -> _FakeExtractor:
    return _FakeExtractor(
        CriteriaExtractionOutput(
            questions=(
                ExtractedQuestionOutput(
                    number="問1",
                    points=5,
                    model_answer="模範解答1",
                    criteria=(
                        ExtractedCriterionOutput(
                            description="要点に触れている", kind=CriterionKind.ADD, points=3
                        ),
                        ExtractedCriterionOutput(
                            description="字数を満たす", kind=CriterionKind.ADD, points=2
                        ),
                    ),
                    source_pages=(1,),
                ),
                ExtractedQuestionOutput(
                    number="問2",
                    points=None,
                    model_answer="模範解答2",
                    criteria=(),
                    source_pages=(2,),
                    note="配点の記載が読み取れませんでした",
                ),
            ),
            total_points=20,
            unreadable_pages=(2,),
        )
    )


@pytest.fixture
def client(data_root: Path, extractor: _FakeExtractor) -> TestClient:
    app = create_app(
        api_token=_TOKEN,
        data_root=data_root,
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
        criteria_extractor=extractor,
    )
    return TestClient(app)


def _session_factory(data_root: Path) -> sessionmaker[Session]:
    return build_session_factory(create_sqlite_engine(sqlite_url(data_root / "database.sqlite")))


def _register_test(client: TestClient) -> str:
    response = client.post(
        "/tests",
        headers=_auth(),
        data={"name": "第1回", "subject": "テスト科目"},
        files={
            "model_answer": ("model-answer.pdf", _pdf_bytes(), "application/pdf"),
            "manual": ("criteria.pdf", _pdf_bytes(), "application/pdf"),
        },
    )
    assert response.status_code == 201, response.text
    test_id: str = response.json()["id"]
    return test_id


def _questions(data_root: Path, test_id: str) -> list[Any]:
    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        return list(uow.questions.list_for_test(test_id))


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #


def test_extract_returns_a_draft_with_unknown_points_preserved(
    client: TestClient, extractor: _FakeExtractor
) -> None:
    test_id = _register_test(client)
    response = client.post(f"/tests/{test_id}/criteria/extract", headers=_auth())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "draft"
    assert body["extracted"] is True
    assert [q["points"] for q in body["questions"]] == [5, None]
    assert body["unreadable_pages"] == [2]
    # Every page was rendered and sent -- images are the primary input, not
    # a fallback taken only when a text layer is missing.
    assert len(extractor.requests) == 1
    assert len(extractor.requests[0].page_images) == 2


def test_totals_report_the_known_sum_and_the_unknown_count(client: TestClient) -> None:
    test_id = _register_test(client)
    totals = client.post(f"/tests/{test_id}/criteria/extract", headers=_auth()).json()["totals"]
    assert totals["known_points"] == 5
    assert totals["unknown_count"] == 1
    assert totals["is_complete"] is False
    # No discrepancy is claimed while a value is still missing: the gap is
    # already explained by 問2 being 不明.
    assert totals["declared_total_points"] == 20
    assert totals["declared_difference"] is None


def test_a_malformed_model_response_saves_nothing(
    client: TestClient, data_root: Path, extractor: _FakeExtractor
) -> None:
    """Issue #103 acceptance criterion 6. The response is a 502 and no draft
    exists afterwards -- a half-parsed set of point values on screen would be
    indistinguishable from one the model actually read."""
    extractor.error = SchemaViolation("fake response failed schema validation")
    test_id = _register_test(client)
    response = client.post(f"/tests/{test_id}/criteria/extract", headers=_auth())
    assert response.status_code == 502
    assert "保存していません" in response.json()["detail"]
    assert client.get(f"/tests/{test_id}/criteria", headers=_auth()).status_code == 404
    assert not (data_root / "tests" / test_id / "criteria.json").exists()


def test_an_unavailable_provider_is_503_and_hand_entry_still_works(
    client: TestClient, extractor: _FakeExtractor
) -> None:
    """Issue #95 決定 8: extraction failing must not be the end of the road."""
    extractor.error = ProviderUnavailable("no image-capable transport")
    test_id = _register_test(client)
    assert client.post(f"/tests/{test_id}/criteria/extract", headers=_auth()).status_code == 503

    saved = client.put(
        f"/tests/{test_id}/criteria",
        headers=_auth(),
        json={
            "questions": [
                {
                    "number": "問1",
                    "points": 7,
                    "model_answer": "手で入れた模範解答",
                    "criteria": [{"description": "手で入れた基準", "kind": "add", "points": 7}],
                    "source_pages": [],
                    "note": None,
                }
            ],
            "declared_total_points": None,
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["extracted"] is False
    assert saved.json()["totals"]["known_points"] == 7


def test_estimate_reports_the_pages_without_calling_the_provider(
    client: TestClient, extractor: _FakeExtractor
) -> None:
    """Code review P2-2: pressing 抽出 uploads every page to a paid provider,
    so the reviewer gets to see the size first."""
    test_id = _register_test(client)
    response = client.get(f"/tests/{test_id}/criteria/estimate", headers=_auth())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_count"] == 2
    assert body["max_pages"] == MAX_CRITERIA_PAGES
    # Asking what it would cost must not cost anything.
    assert extractor.requests == []


def test_estimate_says_it_cannot_price_rather_than_quoting_zero(
    client: TestClient,
) -> None:
    """``null`` is not zero. Zero would be a reviewer stating their usage is
    free; null is this app admitting it does not know a per-page price -- the
    same distinction Issue #101 settled on for the intake screen."""
    test_id = _register_test(client)
    body = client.get(f"/tests/{test_id}/criteria/estimate", headers=_auth()).json()
    assert body["unit_cost"] is None
    assert body["estimated_cost"] is None


def test_estimate_is_404_for_an_unknown_test_and_409_without_the_pdf(
    client: TestClient, data_root: Path
) -> None:
    assert client.get("/tests/missing/criteria/estimate", headers=_auth()).status_code == 404
    test_id = _register_test(client)
    (data_root / "tests" / test_id / "manual.pdf").unlink()
    assert client.get(f"/tests/{test_id}/criteria/estimate", headers=_auth()).status_code == 409


def test_rendering_holds_the_shared_pdfium_lock_and_the_provider_call_does_not(
    data_root: Path, extractor: _FakeExtractor
) -> None:
    """Issue #103 code review P1.

    pypdfium2 is not safe to call from several threads at once, so the render
    has to happen under the lock `create_app` shares with answer intake, PDF
    export and profile analysis. The provider call must **not**: it takes
    7-53 seconds on the measured material, and holding a global PDF lock
    across it would stop every other PDF operation in the app for that long.

    Checked by observing the lock from inside each step rather than by
    reading the code, so a future refactor that widens or drops the critical
    section fails here.
    """
    pdfium_lock = threading.Lock()
    held_during_render: list[bool] = []
    held_during_extract: list[bool] = []

    real_page_count = PdfiumPypdfEngine().page_count

    class _ObservingEngine(PdfiumPypdfEngine):
        def render_page_png(self, source: Path, page_index: int, *, scale: float) -> bytes:
            # `acquire(blocking=False)` fails exactly when the lock is
            # already held -- by this same thread, here.
            held_during_render.append(not pdfium_lock.acquire(blocking=False))
            if held_during_render[-1] is False:
                pdfium_lock.release()
            return super().render_page_png(source, page_index, scale=scale)

    def observing_extract(request: CriteriaExtractionRequest) -> CriteriaExtractionOutput:
        held_during_extract.append(not pdfium_lock.acquire(blocking=False))
        if held_during_extract[-1] is False:
            pdfium_lock.release()
        return CriteriaExtractionOutput()

    extractor.extract = observing_extract  # type: ignore[method-assign]
    app = create_app(
        api_token=_TOKEN,
        data_root=data_root,
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
        criteria_extractor=extractor,
        pdf_engine=_ObservingEngine(),
        pdfium_lock=pdfium_lock,
    )
    client = TestClient(app)
    test_id = _register_test(client)
    assert client.post(f"/tests/{test_id}/criteria/extract", headers=_auth()).status_code == 200

    assert real_page_count is not None
    assert held_during_render and all(held_during_render), "render ran without the PDFium lock"
    assert held_during_extract == [False], "the provider call held the PDFium lock"


def test_repeated_question_numbers_do_not_make_the_request_fall_over(
    client: TestClient, extractor: _FakeExtractor
) -> None:
    """Issue #103 acceptance criterion 1 (落ちないこと), found by running the
    extraction over the real material: a document whose sections restart
    their numbering makes the model report 問1 twice.

    Both rows survive with their own points, under numbers a reviewer can
    tell apart, and the second one says why it was renamed.
    """
    extractor.output = CriteriaExtractionOutput(
        questions=(
            ExtractedQuestionOutput(number="問1", points=5, model_answer="解答A"),
            ExtractedQuestionOutput(number="問1", points=8, model_answer="解答B"),
        )
    )
    test_id = _register_test(client)
    response = client.post(f"/tests/{test_id}/criteria/extract", headers=_auth())
    assert response.status_code == 200, response.text
    questions = response.json()["questions"]
    assert [question["points"] for question in questions] == [5, 8]
    assert len({question["number"] for question in questions}) == 2
    assert "設問番号" in questions[1]["note"]
    assert response.json()["totals"]["known_points"] == 13


def test_extract_is_rejected_once_confirmed(client: TestClient) -> None:
    test_id = _register_test(client)
    _extract_and_complete(client, test_id)
    assert client.post(f"/tests/{test_id}/criteria/extract", headers=_auth()).status_code == 409


# --------------------------------------------------------------------------- #
# Review and confirm
# --------------------------------------------------------------------------- #


def _extract_and_complete(client: TestClient, test_id: str) -> dict[str, Any]:
    """Extract, fill in the 不明 by hand, and confirm -- the normal path."""
    draft = client.post(f"/tests/{test_id}/criteria/extract", headers=_auth()).json()
    questions = [dict(question) for question in draft["questions"]]
    questions[1]["points"] = 15
    saved = client.put(
        f"/tests/{test_id}/criteria",
        headers=_auth(),
        json={"questions": questions, "declared_total_points": 20},
    )
    assert saved.status_code == 200, saved.text
    confirmed = client.post(
        f"/tests/{test_id}/criteria/confirm",
        headers=_auth(),
        json={"revision": saved.json()["revision"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    body: dict[str, Any] = confirmed.json()
    return body


@pytest.mark.parametrize(
    ("bad_points", "why"),
    [
        (True, "a JSON boolean would otherwise be stored as 1 point"),
        ("5", "a JSON string would otherwise be coerced to 5"),
        (5.0, "a JSON float would otherwise be truncated to 5"),
    ],
)
def test_saving_refuses_a_points_value_that_is_not_an_integer(
    client: TestClient, data_root: Path, bad_points: object, why: str
) -> None:
    """Code review P2-1: the human-editing path was the one place that
    coerced.

    The LLM boundary and the file boundary both reject these already. A
    reviewer's PUT is no more trustworthy than either, and the consequence is
    the same -- a maximum nobody typed, applied to every submission.
    """
    test_id = _register_test(client)
    response = client.put(
        f"/tests/{test_id}/criteria",
        headers=_auth(),
        json={
            "questions": [
                {
                    "number": "問1",
                    "points": bad_points,
                    "model_answer": "模範解答",
                    "criteria": [],
                    "source_pages": [],
                    "note": None,
                }
            ],
            "declared_total_points": None,
        },
    )
    assert response.status_code == 422, why
    # Nothing was stored, so a retry starts from a clean state.
    assert client.get(f"/tests/{test_id}/criteria", headers=_auth()).status_code == 404


def test_saving_refuses_a_non_integer_criterion_score_or_declared_total(
    client: TestClient,
) -> None:
    """The same rule on the other two numbers a reviewer can type."""
    test_id = _register_test(client)
    base: dict[str, Any] = {
        "number": "問1",
        "points": 5,
        "model_answer": "模範解答",
        "criteria": [],
        "source_pages": [],
        "note": None,
    }
    with_bad_criterion = dict(base)
    with_bad_criterion["criteria"] = [{"description": "基準", "kind": "add", "points": True}]
    assert (
        client.put(
            f"/tests/{test_id}/criteria",
            headers=_auth(),
            json={"questions": [with_bad_criterion], "declared_total_points": None},
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"/tests/{test_id}/criteria",
            headers=_auth(),
            json={"questions": [base], "declared_total_points": True},
        ).status_code
        == 422
    )


def test_saving_still_accepts_ordinary_integers_and_enum_strings(
    client: TestClient,
) -> None:
    """The pair to the two tests above -- strictness was narrowed to the
    integers precisely so an enum still arrives as the JSON string it has to
    be."""
    test_id = _register_test(client)
    response = client.put(
        f"/tests/{test_id}/criteria",
        headers=_auth(),
        json={
            "questions": [
                {
                    "number": "問1",
                    "points": 5,
                    "model_answer": "模範解答",
                    "criteria": [{"description": "減点条件", "kind": "deduct", "points": 2}],
                    "source_pages": [1],
                    "note": None,
                }
            ],
            "declared_total_points": 5,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["questions"][0]["criteria"][0]["kind"] == "deduct"


def test_confirm_refuses_a_non_integer_revision(client: TestClient) -> None:
    test_id = _register_test(client)
    client.post(f"/tests/{test_id}/criteria/extract", headers=_auth())
    assert (
        client.post(
            f"/tests/{test_id}/criteria/confirm", headers=_auth(), json={"revision": True}
        ).status_code
        == 422
    )


def test_confirm_is_refused_while_any_points_are_unknown(
    client: TestClient, data_root: Path
) -> None:
    """The gate. 422, and not one `Question` row is written."""
    test_id = _register_test(client)
    draft = client.post(f"/tests/{test_id}/criteria/extract", headers=_auth()).json()
    response = client.post(
        f"/tests/{test_id}/criteria/confirm",
        headers=_auth(),
        json={"revision": draft["revision"]},
    )
    assert response.status_code == 422
    assert "不明" in response.json()["detail"]
    assert _questions(data_root, test_id) == []


def test_confirm_writes_questions_and_rubrics(client: TestClient, data_root: Path) -> None:
    test_id = _register_test(client)
    body = _extract_and_complete(client, test_id)
    assert body["status"] == "confirmed"
    assert body["totals"] == {
        "known_points": 20,
        "unknown_count": 0,
        "declared_total_points": 20,
        "declared_difference": None,
        "is_complete": True,
    }

    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        questions = sorted(uow.questions.list_for_test(test_id), key=lambda q: q.number)
        assert [(q.number, q.points) for q in questions] == [("問1", 5), ("問2", 15)]
        # A question that exists only in the criteria draft has no
        # coordinates, and that is recorded honestly rather than guessed:
        # `submission_intake` flags it for review instead of cropping from
        # made-up numbers.
        assert all(question.answer_area is None for question in questions)
        assert all(question.page == 1 for question in questions)
        # The model answer came out of the same 採点基準PDF, which is what
        # lets `grading_processor` run at all (it refuses a blank one).
        assert questions[0].model_answer == "模範解答1"
        rubric = uow.rubrics.get_for_question(questions[0].id)
        assert rubric is not None
        assert [(c.description, c.max_points) for c in rubric.criteria] == [
            ("要点に触れている", 3),
            ("字数を満たす", 2),
        ]


def test_a_wholly_deductive_question_becomes_a_subtractive_one(
    client: TestClient, data_root: Path, extractor: _FakeExtractor
) -> None:
    """One measured subject is written entirely as deductions. The scoring
    method has to travel with the rubric, or the provider is told to add
    points for clauses that describe taking them away."""
    extractor.output = CriteriaExtractionOutput(
        questions=(
            ExtractedQuestionOutput(
                number="問1",
                points=10,
                model_answer="模範解答",
                criteria=(
                    ExtractedCriterionOutput(
                        description="文意が通らない", kind=CriterionKind.DEDUCT, points=3
                    ),
                    ExtractedCriterionOutput(
                        description="字数不足", kind=CriterionKind.DEDUCT, points=2
                    ),
                ),
            ),
        )
    )
    test_id = _register_test(client)
    draft = client.post(f"/tests/{test_id}/criteria/extract", headers=_auth()).json()
    client.post(
        f"/tests/{test_id}/criteria/confirm",
        headers=_auth(),
        json={"revision": draft["revision"]},
    )
    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        question = uow.questions.list_for_test(test_id)[0]
        assert question.scoring_method is ScoringMethod.SUBTRACTIVE


def test_a_mixed_question_keeps_its_deductions_labelled(
    client: TestClient, data_root: Path, extractor: _FakeExtractor
) -> None:
    """`ScoringMethod` has no "mixed" value, so the kind is carried in the
    criterion's own text instead -- never dropped, because a deduction read
    as an addition inverts the grade."""
    extractor.output = CriteriaExtractionOutput(
        questions=(
            ExtractedQuestionOutput(
                number="問1",
                points=10,
                model_answer="模範解答",
                criteria=(
                    ExtractedCriterionOutput(
                        description="要点に触れている", kind=CriterionKind.ADD, points=8
                    ),
                    ExtractedCriterionOutput(
                        description="誤字がある", kind=CriterionKind.DEDUCT, points=2
                    ),
                ),
            ),
        )
    )
    test_id = _register_test(client)
    draft = client.post(f"/tests/{test_id}/criteria/extract", headers=_auth()).json()
    client.post(
        f"/tests/{test_id}/criteria/confirm",
        headers=_auth(),
        json={"revision": draft["revision"]},
    )
    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        question = uow.questions.list_for_test(test_id)[0]
        assert question.scoring_method is ScoringMethod.ADDITIVE
        rubric = uow.rubrics.get_for_question(question.id)
        assert rubric is not None
        assert [c.description for c in rubric.criteria] == ["要点に触れている", "減点: 誤字がある"]


def test_confirm_with_a_stale_revision_is_rejected(client: TestClient) -> None:
    """The compare-and-set. What is being attested to here is the maximum
    every grade is computed against, so confirming a set somebody else has
    since changed must fail rather than silently approve it."""
    test_id = _register_test(client)
    draft = client.post(f"/tests/{test_id}/criteria/extract", headers=_auth()).json()
    questions = [dict(question) for question in draft["questions"]]
    questions[1]["points"] = 15
    client.put(
        f"/tests/{test_id}/criteria",
        headers=_auth(),
        json={"questions": questions, "declared_total_points": 20},
    )
    response = client.post(
        f"/tests/{test_id}/criteria/confirm",
        headers=_auth(),
        json={"revision": draft["revision"]},
    )
    assert response.status_code == 409


def test_a_confirmed_set_cannot_be_edited_or_reconfirmed(client: TestClient) -> None:
    test_id = _register_test(client)
    body = _extract_and_complete(client, test_id)
    assert (
        client.put(
            f"/tests/{test_id}/criteria",
            headers=_auth(),
            json={"questions": [], "declared_total_points": None},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/tests/{test_id}/criteria/confirm",
            headers=_auth(),
            json={"revision": body["revision"]},
        ).status_code
        == 409
    )


def test_get_is_404_before_anything_has_been_extracted_or_entered(client: TestClient) -> None:
    test_id = _register_test(client)
    assert client.get(f"/tests/{test_id}/criteria", headers=_auth()).status_code == 404


def test_unknown_test_is_404(client: TestClient) -> None:
    for method, path in (
        ("post", "/tests/missing/criteria/extract"),
        ("get", "/tests/missing/criteria"),
    ):
        response = getattr(client, method)(path, headers=_auth())
        assert response.status_code == 404


def test_declared_total_mismatch_is_reported_once_everything_is_known(
    client: TestClient, extractor: _FakeExtractor
) -> None:
    """The cheapest available signal that a question was missed."""
    extractor.output = CriteriaExtractionOutput(
        questions=(ExtractedQuestionOutput(number="問1", points=5, model_answer="模範解答"),),
        total_points=20,
    )
    test_id = _register_test(client)
    totals = client.post(f"/tests/{test_id}/criteria/extract", headers=_auth()).json()["totals"]
    assert totals["declared_difference"] == 15


def test_confirming_the_profile_afterwards_keeps_the_confirmed_points(
    client: TestClient, data_root: Path
) -> None:
    """Order-independence, the reason both confirms share one builder.

    `confirm_profile` rebuilds the whole Question set. Without it reading the
    confirmed 採点基準, the reviewer would confirm their regions and silently
    lose every 配点 they had just signed off on.
    """
    test_id = _register_test(client)
    _extract_and_complete(client, test_id)

    regions = [
        {
            "region_id": "r1",
            "kind": "question",
            "page_index": 1,
            "bbox": {"x0": 0.1, "y0": 0.1, "x1": 0.4, "y1": 0.2},
            "label": "問1",
            "confirmed": False,
            "text": "設問本文",
        },
        {
            "region_id": "r2",
            "kind": "answer_area",
            "page_index": 1,
            "bbox": {"x0": 0.1, "y0": 0.3, "x1": 0.9, "y1": 0.7},
            "label": "問1",
            "confirmed": False,
            "text": None,
        },
    ]
    # A profile has to exist before it can be replaced; the registration
    # PDFs here are blank, so this produces an empty candidate set and the
    # PUT below supplies the regions -- the manual-fallback path
    # `test_test_registration_api.py` documents.
    assert client.post(f"/tests/{test_id}/profile/analyze", headers=_auth()).status_code == 200
    saved = client.put(f"/tests/{test_id}/profile", headers=_auth(), json={"regions": regions})
    assert saved.status_code == 200, saved.text
    confirmed = client.post(
        f"/tests/{test_id}/profile/confirm",
        headers=_auth(),
        json={"revision": saved.json()["revision"]},
    )
    assert confirmed.status_code == 200, confirmed.text

    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        questions = sorted(uow.questions.list_for_test(test_id), key=lambda q: q.number)
        # 問1 kept its confirmed points *and* gained the coordinates the
        # regions carry; 問2, which has no region at all, is still there.
        assert [(q.number, q.points) for q in questions] == [("問1", 5), ("問2", 15)]
        assert questions[0].answer_area is not None
        assert questions[0].page == 2
        assert questions[1].answer_area is None


def test_an_unconfirmed_criteria_draft_does_not_reach_the_profile_confirm(
    client: TestClient, data_root: Path
) -> None:
    """A draft nobody has signed off on must not become `Question.points` by
    the side door -- that would bypass the 不明 gate entirely."""
    test_id = _register_test(client)
    client.post(f"/tests/{test_id}/criteria/extract", headers=_auth())

    regions = [
        {
            "region_id": "r1",
            "kind": "question",
            "page_index": 0,
            "bbox": {"x0": 0.1, "y0": 0.1, "x1": 0.4, "y1": 0.2},
            "label": "問1",
            "confirmed": False,
            "text": "設問本文",
        },
        {
            "region_id": "r2",
            "kind": "score",
            "page_index": 0,
            "bbox": {"x0": 0.5, "y0": 0.1, "x1": 0.6, "y1": 0.2},
            "label": "問1",
            "confirmed": False,
            "text": "9",
        },
    ]
    assert client.post(f"/tests/{test_id}/profile/analyze", headers=_auth()).status_code == 200
    saved = client.put(f"/tests/{test_id}/profile", headers=_auth(), json={"regions": regions})
    client.post(
        f"/tests/{test_id}/profile/confirm",
        headers=_auth(),
        json={"revision": saved.json()["revision"]},
    )
    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        questions = uow.questions.list_for_test(test_id)
        # The SCORE region's own 9 -- the pre-Issue-#103 fallback -- not the
        # unconfirmed draft's 5, and 問2 (draft-only) does not exist at all.
        assert [(q.number, q.points) for q in questions] == [("問1", 9)]
