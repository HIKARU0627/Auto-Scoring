"""HTTP integration tests for the parallel job queue's API (Issue #18).

Exercises `auto_scoring.api.jobs_router` end to end through `TestClient` +
real SQLite, with the app's lifespan actually started (``with TestClient(app)
as client:``) so `auto_scoring.jobs.queue.JobQueueService`'s background
worker really runs -- a `FakeJobProcessor`/`FakeClock` keep it fast and
deterministic.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.domain.dependency_graph import DependencyEdge, DependencyProvision
from auto_scoring.domain.job_execution import ProcessingOutcome, ProcessingResult
from auto_scoring.domain.models import ErrorCategory
from tests.fakes import FakeClock, FakeJobProcessor
from tests.support import (
    make_question,
    make_submission,
    make_test,
)
from tests.support import (
    seed_confirmed_dependency_graph as _seed_confirmed,
)

_TOKEN = "jobs-test-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}

UowFactory = Callable[[], SqlAlchemyUnitOfWork]


@pytest.fixture
def processor() -> FakeJobProcessor:
    return FakeJobProcessor()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 1, 1))


@pytest.fixture
def client(
    session_factory: sessionmaker[Session], processor: FakeJobProcessor, clock: FakeClock
) -> Iterator[TestClient]:
    app = create_app(
        api_token=_TOKEN, session_factory=session_factory, job_processor=processor, clock=clock
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


def test_create_submission_jobs_without_a_confirmed_graph_returns_409(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test(id="test-1"))
        uow.questions.add(make_question(id="qa", test_id="test-1", number="qa"))
        uow.submissions.add(make_submission(id="sub-1", test_id="test-1"))
        uow.commit()

    response = client.post("/submissions/sub-1/jobs", headers=_AUTH)
    assert response.status_code == 409


def test_create_submission_jobs_returns_the_planned_jobs(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_confirmed(session_factory, question_ids=["qa", "qb"], edges=[_edge("qa", "qb")])

    response = client.post("/submissions/sub-1/jobs", headers=_AUTH)
    assert response.status_code == 200, response.text
    jobs = {job["question_id"]: job for job in response.json()}
    assert jobs["qa"]["state"] == "queued"
    assert jobs["qb"]["state"] == "blocked"
    assert jobs["qb"]["blocked_on_question_id"] == "qa"


def test_create_submission_jobs_is_idempotent(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_confirmed(session_factory, question_ids=["qa"])

    first = client.post("/submissions/sub-1/jobs", headers=_AUTH)
    second = client.post("/submissions/sub-1/jobs", headers=_AUTH)
    assert first.status_code == 200 and second.status_code == 200
    assert [job["id"] for job in first.json()] == [job["id"] for job in second.json()]

    listing = client.get("/submissions/sub-1/jobs", headers=_AUTH)
    assert len(listing.json()) == 1


def test_list_submission_jobs(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    _seed_confirmed(session_factory, question_ids=["qa", "qb"])
    client.post("/submissions/sub-1/jobs", headers=_AUTH)

    response = client.get("/submissions/sub-1/jobs", headers=_AUTH)
    assert response.status_code == 200
    assert {job["question_id"] for job in response.json()} == {"qa", "qb"}


def test_get_job_not_found_returns_404(client: TestClient) -> None:
    response = client.get("/jobs/does-not-exist", headers=_AUTH)
    assert response.status_code == 404


def test_a_submitted_job_runs_to_completion_through_the_real_queue(
    client: TestClient, session_factory: sessionmaker[Session], processor: FakeJobProcessor
) -> None:
    _seed_confirmed(session_factory, question_ids=["qa"])
    created = client.post("/submissions/sub-1/jobs", headers=_AUTH).json()
    job_id = created[0]["id"]

    body = _wait_until_job_state(client, job_id, "succeeded")
    assert body["usable"] is True
    assert len(processor.calls) == 1


def test_retry_endpoint_requeues_a_failed_job(
    client: TestClient, session_factory: sessionmaker[Session], processor: FakeJobProcessor
) -> None:
    processor.set_default(
        ProcessingResult(outcome=ProcessingOutcome.FAILED, error_category=ErrorCategory.PERMANENT)
    )
    _seed_confirmed(session_factory, question_ids=["qa"])
    created = client.post("/submissions/sub-1/jobs", headers=_AUTH).json()
    job_id = created[0]["id"]

    body = _wait_until_job_state(client, job_id, "failed")
    assert body["error_code"] == "permanent"

    processor.set_default(ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=True))
    retry_response = client.post(f"/jobs/{job_id}/retry", headers=_AUTH)
    assert retry_response.status_code == 200

    body = _wait_until_job_state(client, job_id, "succeeded")
    assert body["state"] == "succeeded"


def test_retry_endpoint_rejects_a_job_that_is_not_failed(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_confirmed(session_factory, question_ids=["qa"])
    created = client.post("/submissions/sub-1/jobs", headers=_AUTH).json()
    job_id = created[0]["id"]
    _wait_until_job_state(client, job_id, "succeeded")

    response = client.post(f"/jobs/{job_id}/retry", headers=_AUTH)
    assert response.status_code == 409


def test_cancel_endpoint_cancels_a_blocked_job(session_factory: sessionmaker[Session]) -> None:
    # A processor slow enough that qa is still RUNNING when the cancel call
    # for qb (still BLOCKED behind it) reaches the server -- with the
    # default near-instant fake processor, the background queue can (and
    # sometimes does) race ahead and release+finish qb before this test's
    # second HTTP call even starts.
    slow_processor = FakeJobProcessor(hold_seconds=0.3)
    app = create_app(
        api_token=_TOKEN, session_factory=session_factory, job_processor=slow_processor
    )
    with TestClient(app) as client:
        _seed_confirmed(session_factory, question_ids=["qa", "qb"], edges=[_edge("qa", "qb")])
        created = client.post("/submissions/sub-1/jobs", headers=_AUTH).json()
        job_b = next(job for job in created if job["question_id"] == "qb")
        assert job_b["state"] == "blocked"

        response = client.post(f"/jobs/{job_b['id']}/cancel", headers=_AUTH)
        assert response.status_code == 200
        assert response.json()["state"] == "cancelled"


def test_cancel_endpoint_rejects_an_already_succeeded_job(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_confirmed(session_factory, question_ids=["qa"])
    created = client.post("/submissions/sub-1/jobs", headers=_AUTH).json()
    job_id = created[0]["id"]
    _wait_until_job_state(client, job_id, "succeeded")

    response = client.post(f"/jobs/{job_id}/cancel", headers=_AUTH)
    assert response.status_code == 409


def test_resume_endpoint_releases_a_dependent_locked_by_low_confidence(
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
    time.sleep(0.05)
    still_blocked = client.get(f"/jobs/{job_b}", headers=_AUTH).json()
    assert still_blocked["state"] == "blocked"

    response = client.post("/submissions/sub-1/questions/qa/resume", headers=_AUTH)
    assert response.status_code == 204

    body = _wait_until_job_state(client, job_b, "succeeded")
    assert body["state"] == "succeeded"


def test_endpoints_require_a_bearer_token(client: TestClient) -> None:
    response = client.get("/submissions/sub-1/jobs")
    assert response.status_code == 401
