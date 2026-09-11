"""API tests for AI usage endpoints (Issue #187)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.domain.models import GradeResult, GradingSource, Score
from tests.support import make_question, make_submission, make_test

_TOKEN = "ai-usage-test-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "app-data"


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    data_root: Path,
) -> Iterator[TestClient]:
    app = create_app(api_token=_TOKEN, session_factory=session_factory, data_root=data_root)
    with TestClient(app) as test_client:
        yield test_client


def _seed_submission_with_ai_grade(session_factory: sessionmaker[Session]) -> str:
    submission = make_submission()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question())
        uow.submissions.add(submission)
        uow.grades.add(
            GradeResult(
                id="grade-usage-1",
                submission_id=submission.id,
                question_id="q-1",
                source=GradingSource.AI,
                score=Score(awarded=1, maximum=5),
                confidence=0.9,
                created_at=datetime.now(UTC),
                provider="openrouter",
                model="test/model",
                prompt_version="v1",
                input_tokens=1000,
                output_tokens=250,
            )
        )
        uow.commit()
    return submission.id


def test_submission_ai_usage_without_unit_cost(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    submission_id = _seed_submission_with_ai_grade(session_factory)
    response = client.get(f"/submissions/{submission_id}/ai-usage", headers=_AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["input_tokens"] == 1000
    assert body["output_tokens"] == 250
    assert body["token_unit_cost"] is None
    assert body["estimated_cost"] is None
    assert body["usage_availability"] == "known"


def test_grading_cost_round_trip(client: TestClient) -> None:
    assert client.get("/grading-cost", headers=_AUTH).json() == {"token_unit_cost": None}
    saved = client.put("/grading-cost", headers=_AUTH, json={"token_unit_cost": 0.05})
    assert saved.status_code == 200
    assert client.get("/grading-cost", headers=_AUTH).json() == {"token_unit_cost": 0.05}


def test_submission_ai_usage_with_unit_cost(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client.put("/grading-cost", headers=_AUTH, json={"token_unit_cost": 1.0})
    submission_id = _seed_submission_with_ai_grade(session_factory)
    body = client.get(f"/submissions/{submission_id}/ai-usage", headers=_AUTH).json()
    assert body["estimated_cost"] == pytest.approx(1.25)


def test_verify_openrouter_returns_provider_balance_separately() -> None:
    import httpx

    from auto_scoring.adapters.credentials.verification import (
        _read_key_response,
    )

    response = httpx.Response(
        200,
        json={"data": {"usage": 12.5, "limit": 100.0}},
    )
    outcome = _read_key_response(response)
    assert outcome.provider_account_usage == 12.5
    assert outcome.provider_account_limit == 100.0
