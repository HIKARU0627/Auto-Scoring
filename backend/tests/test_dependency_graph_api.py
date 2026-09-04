"""API/DB integration tests for the dependency-graph endpoints (Issue #26).

Exercises the four required fixture shapes (independent / serial /
branch-merge / cycle) end to end through HTTP + real SQLite, plus the
"AI candidate is wrong, a human corrects it, only the confirmed graph is
usable" acceptance scenario.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.domain.dependency_graph import can_start_submission_processing
from tests.support import make_question, make_test

_TOKEN = "dag-test-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}

UowFactory = Callable[[], SqlAlchemyUnitOfWork]


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> TestClient:
    app = create_app(api_token=_TOKEN, session_factory=session_factory)
    return TestClient(app)


def _seed_questions(make_uow: UowFactory, numbers: list[tuple[str, str, int]]) -> None:
    """``numbers`` is a list of ``(question_id, number, page)``."""
    with make_uow() as uow:
        uow.tests.add(make_test())
        for question_id, number, page in numbers:
            uow.questions.add(make_question(id=question_id, number=number, page=page))
        uow.commit()


def _analyze(client: TestClient, overrides: list[dict[str, str]] | None = None) -> dict[str, Any]:
    response = client.post(
        "/tests/test-1/dependency-graph/analyze",
        json={"overrides": overrides or []},
        headers=_AUTH,
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


# --------------------------------------------------------------------------- #
# Fixture 1: all independent
# --------------------------------------------------------------------------- #
def test_all_independent_questions_land_in_one_layer(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1), ("q3", "問3", 1)])

    body = _analyze(client)

    assert body["status"] == "draft"
    assert body["edges"] == []
    assert body["layers"] == [["q1", "q2", "q3"]]


# --------------------------------------------------------------------------- #
# Fixture 2: fully serial (also covers the multi-page acceptance criterion)
# --------------------------------------------------------------------------- #
def test_fully_serial_chain_across_pages(client: TestClient, make_uow: UowFactory) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1), ("q3", "問3", 2)])

    body = _analyze(
        client,
        overrides=[
            {"question_id": "q2", "prompt_text": "問1の答えを踏まえて説明せよ。"},
            {"question_id": "q3", "prompt_text": "問2の結果を用いて英作文せよ。"},
        ],
    )

    assert body["layers"] == [["q1"], ["q2"], ["q3"]]
    assert {(e["from_question_id"], e["to_question_id"]) for e in body["edges"]} == {
        ("q1", "q2"),
        ("q2", "q3"),
    }


# --------------------------------------------------------------------------- #
# Fixture 3: branch and merge
# --------------------------------------------------------------------------- #
def test_branch_and_merge(client: TestClient, make_uow: UowFactory) -> None:
    _seed_questions(
        make_uow, [("q1", "問1", 1), ("q2", "問2", 1), ("q3", "問3", 1), ("q4", "問4", 1)]
    )

    body = _analyze(
        client,
        overrides=[
            {"question_id": "q2", "prompt_text": "問1を踏まえて答えよ。"},
            {"question_id": "q3", "prompt_text": "問1を踏まえて答えよ。"},
            {"question_id": "q4", "prompt_text": "問2に基づいて、また問3に基づいて答えよ。"},
        ],
    )

    assert body["layers"] == [["q1"], ["q2", "q3"], ["q4"]]


# --------------------------------------------------------------------------- #
# Fixture 4: cycle is rejected, not saved
# --------------------------------------------------------------------------- #
def test_cyclic_candidates_are_rejected_and_not_saved(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1)])

    response = client.post(
        "/tests/test-1/dependency-graph/analyze",
        json={
            "overrides": [
                {"question_id": "q1", "prompt_text": "問2を参照して答えよ。"},
                {"question_id": "q2", "prompt_text": "問1を参照して答えよ。"},
            ]
        },
        headers=_AUTH,
    )
    assert response.status_code == 422
    assert "cycle" in response.json()["detail"].lower()

    # Nothing was persisted.
    get_response = client.get("/tests/test-1/dependency-graph", headers=_AUTH)
    assert get_response.status_code == 404


# --------------------------------------------------------------------------- #
# Human corrects an AI candidate; only the confirmed graph is usable
# --------------------------------------------------------------------------- #
def test_human_correction_confirm_gates_submission_processing(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1)])

    draft = _analyze(
        client,
        overrides=[{"question_id": "q2", "prompt_text": "問1を参照して答えよ(誤検出)。"}],
    )
    assert draft["status"] == "draft"
    assert {(e["from_question_id"], e["to_question_id"]) for e in draft["edges"]} == {("q1", "q2")}

    # The AI candidate is wrong (no real dependency): a human confirms with an
    # empty edge list, correcting it.
    confirm_response = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"edges": []},
        headers=_AUTH,
    )
    assert confirm_response.status_code == 200, confirm_response.text
    confirmed = confirm_response.json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["edges"] == []

    # A second confirm on the now-CONFIRMED graph is rejected: a new version
    # must be analyzed first.
    conflict = client.post(
        "/tests/test-1/dependency-graph/confirm", json={"edges": []}, headers=_AUTH
    )
    assert conflict.status_code == 409

    with make_uow() as uow:
        stored = uow.dependency_graphs.get_latest("test-1")
    assert stored is not None
    assert can_start_submission_processing(stored) is True


def test_draft_alone_does_not_allow_submission_processing(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1)])
    _analyze(client)

    with make_uow() as uow:
        latest = uow.dependency_graphs.get_latest("test-1")
    assert can_start_submission_processing(latest) is False


# --------------------------------------------------------------------------- #
# Versioning
# --------------------------------------------------------------------------- #
def test_reanalyzing_after_confirm_starts_a_new_version(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1)])
    _analyze(client)
    client.post("/tests/test-1/dependency-graph/confirm", json={"edges": []}, headers=_AUTH)

    second = _analyze(client)
    assert second["version"] == 2
    assert second["status"] == "draft"

    versions = client.get("/tests/test-1/dependency-graph/versions", headers=_AUTH).json()
    assert [v["version"] for v in versions] == [1, 2]
    assert versions[0]["status"] == "confirmed"
    assert versions[1]["status"] == "draft"


# --------------------------------------------------------------------------- #
# Auth / not-found
# --------------------------------------------------------------------------- #
def test_dependency_graph_routes_require_bearer_token(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1)])
    response = client.post("/tests/test-1/dependency-graph/analyze", json={"overrides": []})
    assert response.status_code == 401


def test_analyze_with_no_questions_is_not_found(client: TestClient) -> None:
    response = client.post(
        "/tests/missing-test/dependency-graph/analyze", json={"overrides": []}, headers=_AUTH
    )
    assert response.status_code == 404
