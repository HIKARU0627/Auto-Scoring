"""HTTP integration tests for `auto_scoring.api.recognitions_router` (Issue #19).

Exercises the manual-entry review path end to end through `TestClient` + real
SQLite, with the app's lifespan actually started so
`auto_scoring.jobs.queue.JobQueueService`'s background worker really runs --
a `FakeJobProcessor` keeps it fast and deterministic (no real OCR call).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.domain.dependency_graph import DependencyEdge, DependencyProvision
from auto_scoring.domain.job_execution import ProcessingOutcome, ProcessingResult
from tests.fakes import FakeClock, FakeJobProcessor
from tests.support import make_answer_image
from tests.support import (
    seed_confirmed_dependency_graph as _seed_confirmed,
)

_TOKEN = "recognitions-test-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


@pytest.fixture
def processor() -> FakeJobProcessor:
    return FakeJobProcessor()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 1, 1))


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "app-data"


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    processor: FakeJobProcessor,
    clock: FakeClock,
    data_root: Path,
) -> Iterator[TestClient]:
    app = create_app(
        api_token=_TOKEN,
        session_factory=session_factory,
        job_processor=processor,
        clock=clock,
        data_root=data_root,
    )
    with TestClient(app) as test_client:
        yield test_client


def _edge(a: str, b: str) -> DependencyEdge:
    return DependencyEdge(
        from_question_id=a,
        to_question_id=b,
        provides=(DependencyProvision.SCORE,),
        rationale=f"{a}の結果を{b}が使用",
    )


def _wait_until_job_state(
    client: TestClient, job_id: str, state: str, *, timeout: float = 5.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        response = client.get(f"/jobs/{job_id}", headers=_AUTH)
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        if body["state"] == state:
            return body
        if time.monotonic() > deadline:
            raise AssertionError(f"job {job_id} never reached {state!r}, last body: {body}")
        time.sleep(0.01)


def test_get_answer_image_returns_404_when_none_recorded(client: TestClient) -> None:
    response = client.get("/submissions/sub-1/questions/qa/answer-image", headers=_AUTH)
    assert response.status_code == 404


def test_get_answer_image_round_trips_the_stored_bytes(
    client: TestClient, session_factory: sessionmaker[Session], data_root: Path
) -> None:
    store = LocalFileStore(data_root)
    _seed_confirmed(session_factory, question_ids=["qa"])
    image = make_answer_image(question_id="qa")
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.answer_images.add(image)
        uow.commit()
    store.write_atomic(store.root / image.image_path, b"\x89PNG\r\n\x1a\n-fake-")

    response = client.get("/submissions/sub-1/questions/qa/answer-image", headers=_AUTH)

    assert response.status_code == 200
    assert response.content == b"\x89PNG\r\n\x1a\n-fake-"
    assert response.headers["content-type"] == "image/png"


def test_list_recognitions_is_empty_before_any_recognition(client: TestClient) -> None:
    response = client.get("/submissions/sub-1/questions/qa/recognitions", headers=_AUTH)
    assert response.status_code == 200
    assert response.json() == []


def test_manual_recognition_is_persisted_as_human_source(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_confirmed(session_factory, question_ids=["qa"])
    created = client.post("/submissions/sub-1/jobs", headers=_AUTH).json()
    job_id = created[0]["id"]
    _wait_until_job_state(client, job_id, "succeeded")

    response = client.post(
        "/submissions/sub-1/questions/qa/recognitions",
        json={"text": "手動で読み取ったテキスト"},
        headers=_AUTH,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source"] == "human"
    assert body["confidence"] == 1.0
    assert body["text"] == "手動で読み取ったテキスト"

    history = client.get("/submissions/sub-1/questions/qa/recognitions", headers=_AUTH).json()
    assert len(history) == 1
    assert history[0]["id"] == body["id"]


def test_manual_recognition_releases_a_dependent_locked_by_low_confidence(
    client: TestClient, session_factory: sessionmaker[Session], processor: FakeJobProcessor
) -> None:
    processor.script(
        "sub-1", "qa", [ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=False)]
    )
    _seed_confirmed(session_factory, question_ids=["qa", "qb"], edges=[_edge("qa", "qb")])
    created = client.post("/submissions/sub-1/jobs", headers=_AUTH).json()
    job_a = next(job for job in created if job["question_id"] == "qa")["id"]
    job_b = next(job for job in created if job["question_id"] == "qb")["id"]
    _wait_until_job_state(client, job_a, "succeeded")
    still_blocked = client.get(f"/jobs/{job_b}", headers=_AUTH).json()
    assert still_blocked["state"] == "blocked"

    response = client.post(
        "/submissions/sub-1/questions/qa/recognitions",
        json={"text": "手動入力"},
        headers=_AUTH,
    )
    assert response.status_code == 201, response.text

    body = _wait_until_job_state(client, job_b, "succeeded")
    assert body["state"] == "succeeded"


def test_manual_recognition_rejects_overlong_text(client: TestClient) -> None:
    response = client.post(
        "/submissions/sub-1/questions/qa/recognitions",
        json={"text": "a" * 10_001},
        headers=_AUTH,
    )
    assert response.status_code == 422
