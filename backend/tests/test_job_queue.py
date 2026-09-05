"""Async, deterministic tests for `auto_scoring.jobs.queue.JobQueueService`
(Issue #18): concurrency bound, retry/backoff, cancel, and crash recovery,
all against a real on-disk SQLite database with a `FakeClock` and
`FakeJobProcessor` injected so nothing here depends on wall-clock time or a
real OCR/AI provider.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import datetime

import pytest
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.dependency_graph import (
    DependencyEdge,
    DependencyGraph,
    DependencyProvision,
)
from auto_scoring.domain.job_execution import ProcessingOutcome, ProcessingResult
from auto_scoring.domain.models import ErrorCategory, Job, JobKind, JobState
from auto_scoring.jobs.clock import Clock
from auto_scoring.jobs.queue import JobQueueService
from auto_scoring.jobs.settings import QueueSettings
from tests.fakes import FakeClock, FakeJobProcessor
from tests.support import (
    at,
    make_question,
    make_submission,
    make_test,
)
from tests.support import (
    seed_confirmed_dependency_graph as _seed,
)

EPOCH = datetime(2026, 1, 1)


def _edge(a: str, b: str) -> DependencyEdge:
    return DependencyEdge(
        from_question_id=a,
        to_question_id=b,
        provides=(DependencyProvision.SCORE,),
        rationale=f"{a}の結果を{b}が使用",
    )


async def _wait_until(
    predicate: Callable[[], bool], *, timeout: float = 5.0, interval: float = 0.01
) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting for condition")
        await asyncio.sleep(interval)


def _state(service: JobQueueService, job_id: str) -> JobState | None:
    job = service.get_job(job_id)
    return job.state if job is not None else None


def _job_id_for_question(service: JobQueueService, submission_id: str, question_id: str) -> str:
    jobs = service.list_for_submission(submission_id)
    matches = [j for j in jobs if j.question_id == question_id]
    assert len(matches) == 1, f"expected exactly one job for {question_id!r}, got {matches}"
    return matches[0].id


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(EPOCH)


@pytest.fixture
def fast_settings() -> QueueSettings:
    # Tiny backoff so a real (non-faked) sleep in a test would still be fast;
    # FakeClock.sleep doesn't actually wait regardless.
    return QueueSettings(
        max_concurrency=2, max_attempts=3, initial_backoff_seconds=1.0, backoff_multiplier=2.0
    )


# --------------------------------------------------------------------------- #
# Concurrency bound
# --------------------------------------------------------------------------- #
async def test_concurrency_never_exceeds_max_concurrency(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    question_ids = [f"q{i}" for i in range(6)]
    _seed(session_factory, question_ids=question_ids)
    processor = FakeJobProcessor(hold_seconds=0.05)
    settings = QueueSettings(max_concurrency=2)
    service = JobQueueService(session_factory, processor, settings=settings, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        await _wait_until(lambda: len(processor.calls) == len(question_ids))
        await _wait_until(
            lambda: all(
                _state(service, j.id) is JobState.SUCCEEDED
                for j in service.list_for_submission("sub-1")
            )
        )
    finally:
        await service.shutdown()
    assert processor.max_concurrency_seen <= 2


async def test_different_submissions_share_the_same_concurrency_cap(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """A human reviewing one submission does not stop another from
    processing (Issue #18 acceptance) -- and the same semaphore governs both.
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test(id="test-shared"))
        uow.questions.add(make_question(id="qa", test_id="test-shared", number="qa"))
        uow.submissions.add(make_submission(id="sub-a", test_id="test-shared"))
        uow.submissions.add(
            make_submission(id="sub-b", test_id="test-shared", source_pdf_sha256="1" * 64)
        )
        draft = DependencyGraph.from_candidates(
            id="test-shared:v1",
            test_id="test-shared",
            version=1,
            question_ids=["qa"],
            created_at=at(),
        )
        uow.dependency_graphs.save(draft)
        assert uow.dependency_graphs.try_confirm(draft.confirm(edges=[], confirmed_at=at())) is True
        uow.commit()

    processor = FakeJobProcessor(hold_seconds=0.05)
    service = JobQueueService(
        session_factory, processor, settings=QueueSettings(max_concurrency=2), clock=clock
    )
    await service.start()
    try:
        service.submit_submission(submission_id="sub-a")
        service.submit_submission(submission_id="sub-b")
        await _wait_until(lambda: len(processor.calls) == 2)
        await _wait_until(
            lambda: (
                _state(service, _job_id_for_question(service, "sub-a", "qa")) is JobState.SUCCEEDED
                and _state(service, _job_id_for_question(service, "sub-b", "qa"))
                is JobState.SUCCEEDED
            )
        )
    finally:
        await service.shutdown()
    assert processor.max_concurrency_seen <= 2


# --------------------------------------------------------------------------- #
# Retry / backoff
# --------------------------------------------------------------------------- #
async def test_retry_succeeds_after_transient_failures_with_exponential_backoff(
    session_factory: sessionmaker[Session], clock: FakeClock, fast_settings: QueueSettings
) -> None:
    _seed(session_factory, question_ids=["qa"])
    processor = FakeJobProcessor()
    processor.script(
        "sub-1",
        "qa",
        [
            ProcessingResult(
                outcome=ProcessingOutcome.FAILED, error_category=ErrorCategory.TIMEOUT
            ),
            ProcessingResult(
                outcome=ProcessingOutcome.FAILED, error_category=ErrorCategory.RATE_LIMITED
            ),
        ],
    )
    service = JobQueueService(session_factory, processor, settings=fast_settings, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_id = _job_id_for_question(service, "sub-1", "qa")
        await _wait_until(lambda: _state(service, job_id) is JobState.SUCCEEDED)
    finally:
        await service.shutdown()
    job = service.get_job(job_id)
    assert job is not None
    assert job.attempts == 3
    assert clock.sleep_calls == [1.0, 2.0]


async def test_429_and_5xx_do_not_retry_without_bound(
    session_factory: sessionmaker[Session], clock: FakeClock
) -> None:
    """Issue #18 acceptance: "429時に無制限retryしない"."""
    _seed(session_factory, question_ids=["qa"])
    processor = FakeJobProcessor(
        default=ProcessingResult(
            outcome=ProcessingOutcome.FAILED, error_category=ErrorCategory.RATE_LIMITED
        ),
    )
    settings = QueueSettings(max_attempts=2, initial_backoff_seconds=0.001, backoff_multiplier=2.0)
    service = JobQueueService(session_factory, processor, settings=settings, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_id = _job_id_for_question(service, "sub-1", "qa")
        await _wait_until(lambda: _state(service, job_id) is JobState.FAILED)
        # give any (incorrect) further retry a chance to happen before asserting
        await asyncio.sleep(0.05)
    finally:
        await service.shutdown()
    job = service.get_job(job_id)
    assert job is not None
    assert job.state is JobState.FAILED
    assert job.attempts == 2
    assert job.error_code is ErrorCategory.RATE_LIMITED
    assert len(processor.calls) == 2


async def test_permanent_error_fails_immediately_without_retry(
    session_factory: sessionmaker[Session], clock: FakeClock
) -> None:
    _seed(session_factory, question_ids=["qa"])
    processor = FakeJobProcessor(
        default=ProcessingResult(
            outcome=ProcessingOutcome.FAILED, error_category=ErrorCategory.PERMANENT
        ),
    )
    service = JobQueueService(
        session_factory, processor, settings=QueueSettings(max_attempts=5), clock=clock
    )
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_id = _job_id_for_question(service, "sub-1", "qa")
        await _wait_until(lambda: _state(service, job_id) is JobState.FAILED)
        await asyncio.sleep(0.05)
    finally:
        await service.shutdown()
    job = service.get_job(job_id)
    assert job is not None
    assert job.attempts == 1
    assert clock.sleep_calls == []
    assert len(processor.calls) == 1


# --------------------------------------------------------------------------- #
# Cancel
# --------------------------------------------------------------------------- #
async def test_cancel_a_queued_job_before_it_starts_prevents_processing(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    _seed(session_factory, question_ids=["qa", "qb"])
    hold = asyncio.Event()
    processor = FakeJobProcessor(hold_event=hold)
    service = JobQueueService(
        session_factory, processor, settings=QueueSettings(max_concurrency=1), clock=clock
    )
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_a = _job_id_for_question(service, "sub-1", "qa")
        job_b = _job_id_for_question(service, "sub-1", "qb")
        await _wait_until(lambda: _state(service, job_a) is JobState.RUNNING)
        # qb is still QUEUED (max_concurrency=1 -- qa holds the only slot).
        assert _state(service, job_b) is JobState.QUEUED
        cancelled = service.cancel_job(job_b)
        assert cancelled.state is JobState.CANCELLED
        hold.set()  # let qa finish
        await _wait_until(lambda: _state(service, job_a) is JobState.SUCCEEDED)
    finally:
        await service.shutdown()
    assert all(call.question_id != "qb" for call in processor.calls)
    assert _state(service, job_b) is JobState.CANCELLED


async def test_cancel_a_running_job_stops_it_and_marks_it_cancelled(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    _seed(session_factory, question_ids=["qa"])
    hold = asyncio.Event()

    class _HoldingProcessor:
        def __init__(self) -> None:
            self.calls: list[Job] = []

        async def process(self, job: Job) -> ProcessingResult:
            self.calls.append(job)
            await hold.wait()
            return ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=True)

    processor = _HoldingProcessor()
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_id = _job_id_for_question(service, "sub-1", "qa")
        await _wait_until(lambda: _state(service, job_id) is JobState.RUNNING)
        service.cancel_job(job_id)
        await _wait_until(lambda: _state(service, job_id) is JobState.CANCELLED)
    finally:
        hold.set()
        await service.shutdown()
    assert len(processor.calls) == 1


# --------------------------------------------------------------------------- #
# Crash recovery
# --------------------------------------------------------------------------- #
async def test_a_job_left_running_by_a_killed_process_is_requeued_and_completes_once(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    version = _seed(session_factory, question_ids=["qa"])
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.jobs.add(
            Job(
                id="job-interrupted",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qa",
                state=JobState.RUNNING,
                attempts=1,
                max_attempts=3,
                dependency_graph_version=version,
                created_at=at(),
                updated_at=at(),
            )
        )
        uow.commit()

    processor = FakeJobProcessor()
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    try:
        await _wait_until(lambda: _state(service, "job-interrupted") is JobState.SUCCEEDED)
    finally:
        await service.shutdown()
    all_jobs = service.list_for_submission("sub-1")
    assert [j.question_id for j in all_jobs] == ["qa"]  # no duplicate job was created
    assert len(processor.calls) == 1


async def test_a_job_left_running_with_no_attempts_remaining_fails_without_retry(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    version = _seed(session_factory, question_ids=["qa"])
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.jobs.add(
            Job(
                id="job-interrupted",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qa",
                state=JobState.RUNNING,
                attempts=3,
                max_attempts=3,
                dependency_graph_version=version,
                created_at=at(),
                updated_at=at(),
            )
        )
        uow.commit()

    processor = FakeJobProcessor()
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    try:
        await asyncio.sleep(0.05)
    finally:
        await service.shutdown()
    job = service.get_job("job-interrupted")
    assert job is not None
    assert job.state is JobState.FAILED
    assert job.error_code is ErrorCategory.PERMANENT
    assert processor.calls == []


# --------------------------------------------------------------------------- #
# DAG ordering through the real queue
# --------------------------------------------------------------------------- #
async def test_dependent_question_never_starts_before_its_prerequisite_completes(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    _seed(session_factory, question_ids=["qa", "qb", "qc"], edges=[_edge("qa", "qb")])
    processor = FakeJobProcessor()
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        await _wait_until(
            lambda: all(
                _state(service, j.id) is JobState.SUCCEEDED
                for j in service.list_for_submission("sub-1")
            )
        )
    finally:
        await service.shutdown()
    order = [call.question_id for call in processor.calls]
    assert order.index("qa") < order.index("qb")
    assert "qc" in order  # independent question ran too


async def test_merge_point_waits_for_every_prerequisite_and_locks_on_unusable_result(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    _seed(
        session_factory,
        question_ids=["qa", "qb", "qc"],
        edges=[_edge("qa", "qb"), _edge("qc", "qb")],
    )
    processor = FakeJobProcessor()
    processor.script(
        "sub-1", "qc", [ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=False)]
    )
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_b = _job_id_for_question(service, "sub-1", "qb")
        await _wait_until(
            lambda: (
                _state(service, _job_id_for_question(service, "sub-1", "qa")) is JobState.SUCCEEDED
            )
        )
        await _wait_until(
            lambda: (
                _state(service, _job_id_for_question(service, "sub-1", "qc")) is JobState.SUCCEEDED
            )
        )
        # qc succeeded but is not usable (locked_by_dependency) -- qb must
        # stay BLOCKED and must never have been handed to the processor.
        await asyncio.sleep(0.05)
    finally:
        await service.shutdown()
    assert _state(service, job_b) is JobState.BLOCKED
    assert all(call.question_id != "qb" for call in processor.calls)


async def test_mark_question_usable_releases_a_previously_locked_dependent(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    _seed(session_factory, question_ids=["qa", "qb"], edges=[_edge("qa", "qb")])
    processor = FakeJobProcessor()
    processor.script(
        "sub-1", "qa", [ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=False)]
    )
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_a = _job_id_for_question(service, "sub-1", "qa")
        job_b = _job_id_for_question(service, "sub-1", "qb")
        await _wait_until(lambda: _state(service, job_a) is JobState.SUCCEEDED)
        await asyncio.sleep(0.02)
        assert _state(service, job_b) is JobState.BLOCKED

        service.mark_question_usable(submission_id="sub-1", question_id="qa")
        await _wait_until(lambda: _state(service, job_b) is JobState.SUCCEEDED)
    finally:
        await service.shutdown()
    assert any(call.question_id == "qb" for call in processor.calls)


# --------------------------------------------------------------------------- #
# Manual retry API
# --------------------------------------------------------------------------- #
async def test_retry_job_requeues_a_failed_job(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    _seed(session_factory, question_ids=["qa"])
    processor = FakeJobProcessor(
        default=ProcessingResult(
            outcome=ProcessingOutcome.FAILED, error_category=ErrorCategory.PERMANENT
        )
    )
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_id = _job_id_for_question(service, "sub-1", "qa")
        await _wait_until(lambda: _state(service, job_id) is JobState.FAILED)

        processor.set_default(ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=True))
        service.retry_job(job_id)
        await _wait_until(lambda: _state(service, job_id) is JobState.SUCCEEDED)
    finally:
        await service.shutdown()
