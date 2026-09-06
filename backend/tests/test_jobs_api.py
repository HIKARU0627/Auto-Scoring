"""HTTP integration tests for the parallel job queue's API (Issue #18).

Exercises `auto_scoring.api.jobs_router` end to end through `TestClient` +
real SQLite, with the app's lifespan actually started (``with TestClient(app)
as client:``) so `auto_scoring.jobs.queue.JobQueueService`'s background
worker really runs -- a `FakeJobProcessor`/`FakeClock` keep it fast and
deterministic.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.domain.dependency_graph import (
    DependencyEdge,
    DependencyGraph,
    DependencyProvision,
)
from auto_scoring.domain.job_execution import ProcessingOutcome, ProcessingResult
from auto_scoring.domain.models import ErrorCategory, Job
from tests.fakes import FakeClock, FakeJobProcessor
from tests.support import (
    at,
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
    session_factory: sessionmaker[Session],
) -> None:
    # Deliberately not `with TestClient(app) as client:` -- the lifespan (and
    # so the background queue) never starts, so the planned jobs' initial
    # state is a stable snapshot instead of a race against a real,
    # near-instant FakeJobProcessor already having finished qa (and thus
    # released qb) by the time this response is built.
    app = create_app(api_token=_TOKEN, session_factory=session_factory)
    client = TestClient(app)
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


def test_cancel_endpoint_returns_202_for_a_running_job(
    session_factory: sessionmaker[Session],
) -> None:
    """Issue #18 review round 6, P2: cancelling a RUNNING job only
    *requests* cancellation -- the actual RUNNING -> CANCELLED write
    happens asynchronously, moments later, owned by the worker's own task,
    not this call. Answering 200 with that stale "still running" snapshot
    would read as if nothing happened; 202 signals the request was accepted
    but is not yet applied.
    """
    hold = asyncio.Event()
    processor = FakeJobProcessor(hold_event=hold)
    app = create_app(api_token=_TOKEN, session_factory=session_factory, job_processor=processor)
    with TestClient(app) as client:
        _seed_confirmed(session_factory, question_ids=["qa"])
        created = client.post("/submissions/sub-1/jobs", headers=_AUTH).json()
        job_id = created[0]["id"]
        _wait_until_job_state(client, job_id, "running")

        response = client.post(f"/jobs/{job_id}/cancel", headers=_AUTH)
        assert response.status_code == 202
        assert response.json()["state"] == "running"  # pre-cancellation snapshot, not stale 200

        hold.set()  # let the worker notice the cancellation and finalize it
        _wait_until_job_state(client, job_id, "cancelled")


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


class _BlocksFirstCallThenSucceeds:
    """Blocks forever on the first `process` call (until `hold` is set, or
    the task is cancelled); every later call succeeds immediately.

    Used only by the stale-running-task-cancellation test below: the
    reissued replacement for the same question would otherwise also block
    on a shared `hold_event` that the test never sets, hanging
    `JobQueueService.shutdown` forever (`shutdown` deliberately never
    force-cancels workers). Isolating "block" to the first call only lets
    the replacement complete normally once enqueued.
    """

    def __init__(self) -> None:
        self.hold = asyncio.Event()
        self.calls: list[Job] = []
        self.current_concurrency = 0
        self._blocked_once = False

    async def process(self, job: Job) -> ProcessingResult:
        self.current_concurrency += 1
        self.calls.append(job)
        try:
            if not self._blocked_once:
                self._blocked_once = True
                await self.hold.wait()
            return ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=True)
        finally:
            self.current_concurrency -= 1


def test_confirming_a_new_version_cancels_a_stale_running_jobs_task(
    session_factory: sessionmaker[Session],
) -> None:
    """Issue #18 review round 2, P1: a stale job that is RUNNING when a new
    dependency-graph version is confirmed must have its actual in-process
    task cancelled too, not just its DB row flipped to CANCELLED (confirm's
    own write already does that regardless of this fix) -- otherwise the
    external provider call keeps going indefinitely. Observed via the fake
    processor's own concurrency counter, which only drops back to 0 once the
    task's `await hold.wait()` is actually interrupted by cancellation --
    the DB row alone can't distinguish a real cancel from a silently-still-
    running task.
    """
    processor = _BlocksFirstCallThenSucceeds()
    app = create_app(api_token=_TOKEN, session_factory=session_factory, job_processor=processor)
    with TestClient(app) as client:
        _seed_confirmed(session_factory, question_ids=["qa"])
        created = client.post("/submissions/sub-1/jobs", headers=_AUTH).json()
        job_id = created[0]["id"]
        _wait_until_job_state(client, job_id, "running")
        assert processor.current_concurrency == 1

        # A human re-analyzes and confirms v2 while qa's job is still
        # RUNNING under v1.
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            draft_v2 = DependencyGraph.from_candidates(
                id="test-1:v2", test_id="test-1", version=2, question_ids=["qa"], created_at=at()
            )
            uow.dependency_graphs.save(draft_v2)
            uow.commit()
        confirm_response = client.post(
            "/tests/test-1/dependency-graph/confirm",
            json={"version": 2, "edges": []},
            headers=_AUTH,
        )
        assert confirm_response.status_code == 200, confirm_response.text

        deadline = time.monotonic() + 2.0
        while processor.current_concurrency != 0:
            if time.monotonic() > deadline:
                raise AssertionError(
                    "the stale RUNNING job's task was never cancelled -- it is still "
                    "awaiting the processor"
                )
            time.sleep(0.01)

        # The reissued replacement (a fresh job for qa at v2) should still
        # have gone on to complete normally through the same queue.
        replacement = next(
            job
            for job in client.get("/submissions/sub-1/jobs", headers=_AUTH).json()
            if job["dependency_graph_version"] == 2
        )
        _wait_until_job_state(client, replacement["id"], "succeeded")
