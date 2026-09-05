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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.sqlalchemy_repositories import SqlAlchemyJobRepository
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.dependency_graph import (
    DependencyEdge,
    DependencyGraph,
    DependencyProvision,
)
from auto_scoring.domain.job_execution import ProcessingOutcome, ProcessingResult
from auto_scoring.domain.models import ErrorCategory, Job, JobKind, JobSaveConflict, JobState
from auto_scoring.jobs.clock import Clock
from auto_scoring.jobs.queue import JobNotFoundError, JobQueueService
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


# --------------------------------------------------------------------------- #
# Review round 1 regressions
# --------------------------------------------------------------------------- #
async def test_submit_and_cancel_from_a_different_thread_than_the_event_loop(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P1: FastAPI runs a synchronous route handler in a worker thread, not
    on the loop that owns this service's asyncio.Queue/Task objects.
    submit_submission/cancel_job must reach those objects safely (via
    loop.call_soon_threadsafe) even when called from such a thread.
    """
    _seed(session_factory, question_ids=["qa"])
    hold = asyncio.Event()
    processor = FakeJobProcessor(hold_event=hold)
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, lambda: service.submit_submission(submission_id="sub-1"))
        job_id = _job_id_for_question(service, "sub-1", "qa")
        await _wait_until(lambda: _state(service, job_id) is JobState.RUNNING)

        await loop.run_in_executor(None, lambda: service.cancel_job(job_id))
        await _wait_until(lambda: _state(service, job_id) is JobState.CANCELLED)
    finally:
        hold.set()
        await service.shutdown()


async def test_submit_submission_recovers_from_a_concurrent_idempotency_conflict(
    session_factory: sessionmaker[Session], clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2: two concurrent submit_submission calls can both observe "no
    existing job" for the same question and both attempt to insert one; the
    loser's add() hits the new unique constraint (add() flushes
    immediately). That must be treated as "someone else already created it"
    and retried from a fresh read, not surfaced as a raw IntegrityError/500.
    """
    _seed(session_factory, question_ids=["qa"])
    real_add = SqlAlchemyJobRepository.add
    calls = {"count": 0}

    def _add_that_conflicts_once(self: SqlAlchemyJobRepository, job: Job) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise IntegrityError(
                "insert", {}, Exception("uq_jobs_submission_question_graph_version")
            )
        real_add(self, job)

    monkeypatch.setattr(SqlAlchemyJobRepository, "add", _add_that_conflicts_once)

    service = JobQueueService(session_factory, FakeJobProcessor(), clock=clock)
    created = service.submit_submission(submission_id="sub-1")

    assert calls["count"] == 2  # first attempt conflicted, second succeeded
    assert len(created) == 1
    assert [j.question_id for j in service.list_for_submission("sub-1")] == ["qa"]


async def test_duplicate_enqueue_signal_does_not_lose_track_of_the_real_running_task(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P2: a duplicate dispatch signal for the same job id (e.g. start()'s
    recovered-then-swept QUEUED list, or two idempotent submit_submission
    calls) must not let a second, fast no-op task overwrite tracking for the
    real one -- otherwise cancel_job/shutdown can no longer find it once the
    real task is the only one still running.
    """
    _seed(session_factory, question_ids=["qa"])
    hold = asyncio.Event()
    processor = FakeJobProcessor(hold_event=hold)
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_id = _job_id_for_question(service, "sub-1", "qa")
        await _wait_until(lambda: _state(service, job_id) is JobState.RUNNING)

        # A duplicate signal for the same, already-running job id. _run_one
        # for this second signal sees the job is no longer QUEUED and
        # no-ops almost instantly.
        service.enqueue(job_id)
        await asyncio.sleep(0.05)  # let the duplicate's no-op task finish

        cancelled_snapshot = service.cancel_job(job_id)
        assert (
            cancelled_snapshot.state is JobState.RUNNING
        )  # cancel is async; this is the pre-cancel read
        hold.set()
        await _wait_until(lambda: _state(service, job_id) is JobState.CANCELLED)
    finally:
        await service.shutdown()


async def test_retry_honors_the_jobs_own_persisted_max_attempts(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P2: retry decisions must use the persisted Job's own max_attempts,
    not the service's current QueueSettings.max_attempts -- those can differ
    (settings changed since the job was created, a reissued/legacy job
    carrying a different value).
    """
    version = _seed(session_factory, question_ids=["qa"])
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.jobs.add(
            Job(
                id="job-1",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qa",
                state=JobState.QUEUED,
                max_attempts=1,
                dependency_graph_version=version,
                created_at=at(),
                updated_at=at(),
            )
        )
        uow.commit()

    processor = FakeJobProcessor(
        default=ProcessingResult(
            outcome=ProcessingOutcome.FAILED, error_category=ErrorCategory.TIMEOUT
        )
    )
    # The service's own settings would allow 5 attempts -- the job's
    # persisted max_attempts=1 must win.
    service = JobQueueService(
        session_factory, processor, settings=QueueSettings(max_attempts=5), clock=clock
    )
    await service.start()  # start()'s QUEUED sweep picks job-1 up
    try:
        await _wait_until(lambda: _state(service, "job-1") is JobState.FAILED)
        await asyncio.sleep(0.05)
    finally:
        await service.shutdown()
    job = service.get_job("job-1")
    assert job is not None
    assert job.attempts == 1
    assert len(processor.calls) == 1


class _HoldableClock:
    """A clock whose ``sleep`` blocks until the test releases ``hold``,
    for precisely observing whether a concurrency permit is held during a
    backoff sleep."""

    def __init__(self, start: datetime) -> None:
        self._now = start
        self.hold = asyncio.Event()

    def now(self) -> datetime:
        return self._now

    async def sleep(self, seconds: float) -> None:
        await self.hold.wait()


async def test_backoff_sleep_releases_the_concurrency_permit_for_other_submissions(
    session_factory: sessionmaker[Session],
) -> None:
    """P2: the backoff sleep after a retryable failure must happen outside
    the semaphore -- otherwise a failed job occupies a concurrency permit
    for the whole backoff window, and with max_concurrency=1 an independent
    submission's job could never even start until the sleep ends.
    """
    _seed(session_factory, test_id="test-a", submission_id="sub-a", question_ids=["qa"])
    _seed(session_factory, test_id="test-b", submission_id="sub-b", question_ids=["qb"])
    clock = _HoldableClock(EPOCH)
    processor = FakeJobProcessor()
    processor.script(
        "sub-a",
        "qa",
        [ProcessingResult(outcome=ProcessingOutcome.FAILED, error_category=ErrorCategory.TIMEOUT)],
    )
    service = JobQueueService(
        session_factory, processor, settings=QueueSettings(max_concurrency=1), clock=clock
    )
    await service.start()
    try:
        service.submit_submission(submission_id="sub-a")
        job_a = _job_id_for_question(service, "sub-a", "qa")
        await _wait_until(lambda: _state(service, job_a) is JobState.FAILED)

        # job A is now sleeping out its backoff (clock.sleep blocks on
        # `hold`, never set yet). With only 1 concurrency permit, job B can
        # only run at all if that permit was actually released before the
        # sleep, not held through it.
        service.submit_submission(submission_id="sub-b")
        job_b = _job_id_for_question(service, "sub-b", "qb")
        await _wait_until(lambda: _state(service, job_b) is JobState.SUCCEEDED)
    finally:
        clock.hold.set()
        await service.shutdown()


async def test_mark_question_usable_resolves_the_active_graph_version(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P2: mark_question_usable must resolve the submission's test's
    *currently active* confirmed dependency-graph version first, and only
    flip a completed job tagged with that version -- list_for_submission
    returns jobs oldest-first, so picking the first SUCCEEDED match
    regardless of version could revive a stale, superseded version's job
    instead of the active one's.
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test(id="test-1"))
        uow.questions.add(make_question(id="qa", test_id="test-1", number="qa"))
        uow.questions.add(make_question(id="qb", test_id="test-1", number="qb"))
        uow.submissions.add(make_submission(id="sub-1", test_id="test-1"))
        edge = _edge("qa", "qb")
        v1 = DependencyGraph.from_candidates(
            id="test-1:v1",
            test_id="test-1",
            version=1,
            question_ids=["qa", "qb"],
            edges=[edge],
            created_at=at(),
        )
        uow.dependency_graphs.save(v1)
        assert (
            uow.dependency_graphs.try_confirm(v1.confirm(edges=[edge], confirmed_at=at())) is True
        )
        v2 = DependencyGraph.from_candidates(
            id="test-1:v2",
            test_id="test-1",
            version=2,
            question_ids=["qa", "qb"],
            edges=[edge],
            created_at=at(),
        )
        uow.dependency_graphs.save(v2)
        assert (
            uow.dependency_graphs.try_confirm(v2.confirm(edges=[edge], confirmed_at=at())) is True
        )

        # v1's qa job: succeeded but locked (not usable) -- historical, must
        # stay untouched.
        uow.jobs.add(
            Job(
                id="job-qa-v1",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qa",
                state=JobState.SUCCEEDED,
                usable=False,
                dependency_graph_version=1,
                created_at=at(),
                updated_at=at(),
            )
        )
        # v2 (the active version)'s qa job: also succeeded but still locked.
        uow.jobs.add(
            Job(
                id="job-qa-v2",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qa",
                state=JobState.SUCCEEDED,
                usable=False,
                dependency_graph_version=2,
                created_at=at(seconds=10),
                updated_at=at(seconds=10),
            )
        )
        # v2's qb job: blocked on qa, at the active version.
        uow.jobs.add(
            Job(
                id="job-qb-v2",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qb",
                state=JobState.BLOCKED,
                blocked_on_question_id="qa",
                dependency_graph_version=2,
                created_at=at(seconds=10),
                updated_at=at(seconds=10),
            )
        )
        uow.commit()

    service = JobQueueService(session_factory, FakeJobProcessor(), clock=clock)
    service.mark_question_usable(submission_id="sub-1", question_id="qa")

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        qa_v1 = uow.jobs.get("job-qa-v1")
        qa_v2 = uow.jobs.get("job-qa-v2")
        qb_v2 = uow.jobs.get("job-qb-v2")
    assert qa_v1 is not None and qa_v1.usable is False  # untouched: stale version
    assert qa_v2 is not None and qa_v2.usable is True  # the active version's job is flipped
    assert qb_v2 is not None and qb_v2.state is JobState.QUEUED  # released


# --------------------------------------------------------------------------- #
# Review round 2 regressions
# --------------------------------------------------------------------------- #
def test_queue_settings_validates_retry_config_at_construction() -> None:
    """P2: a bad retry setting must fail at QueueSettings() construction,
    not lazily at the first job's failure inside _retry_policy_for (which
    would leave a RUNNING row already committed, stuck until a restart)."""
    with pytest.raises(ValueError):
        QueueSettings(initial_backoff_seconds=-1.0)
    with pytest.raises(ValueError):
        QueueSettings(backoff_multiplier=0.5)
    with pytest.raises(ValueError):
        QueueSettings(max_backoff_seconds=0.1, initial_backoff_seconds=1.0)


async def test_a_retryable_failed_job_is_recovered_at_startup(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P1: a job left FAILED (retryable error_code, attempts remaining) when
    the process was killed mid-backoff must be requeued at the next
    startup -- its in-process backoff timer died with the process, so
    nothing else would ever wake it up again.
    """
    version = _seed(session_factory, question_ids=["qa"])
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.jobs.add(
            Job(
                id="job-1",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qa",
                state=JobState.FAILED,
                attempts=1,
                max_attempts=3,
                error_code=ErrorCategory.TIMEOUT,
                last_error="timed out",
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
        await _wait_until(lambda: _state(service, "job-1") is JobState.SUCCEEDED)
    finally:
        await service.shutdown()
    job = service.get_job("job-1")
    assert job is not None
    assert job.attempts == 2  # requeued, then one more RUNNING attempt
    assert len(processor.calls) == 1


async def test_startup_does_not_recover_a_permanent_or_exhausted_failed_job(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    version = _seed(session_factory, question_ids=["qa", "qb"])
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.jobs.add(
            Job(
                id="permanent",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qa",
                state=JobState.FAILED,
                attempts=1,
                max_attempts=3,
                error_code=ErrorCategory.PERMANENT,
                dependency_graph_version=version,
                created_at=at(),
                updated_at=at(),
            )
        )
        uow.jobs.add(
            Job(
                id="exhausted",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qb",
                state=JobState.FAILED,
                attempts=3,
                max_attempts=3,
                error_code=ErrorCategory.TIMEOUT,
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
    assert _state(service, "permanent") is JobState.FAILED
    assert _state(service, "exhausted") is JobState.FAILED
    assert processor.calls == []


async def test_mark_question_usable_resumes_a_failed_prerequisite(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P1: a human can approve/correct a FAILED prerequisite's downstream
    effect too, not only a low-confidence SUCCEEDED one -- mark_usable must
    not require SUCCEEDED.
    """
    _seed(session_factory, question_ids=["qa", "qb"], edges=[_edge("qa", "qb")])
    processor = FakeJobProcessor(
        default=ProcessingResult(
            outcome=ProcessingOutcome.FAILED, error_category=ErrorCategory.PERMANENT
        )
    )
    # qb should succeed once released -- only qa is meant to fail here.
    processor.script(
        "sub-1", "qb", [ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=True)]
    )
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_a = _job_id_for_question(service, "sub-1", "qa")
        await _wait_until(lambda: _state(service, job_a) is JobState.FAILED)

        service.mark_question_usable(submission_id="sub-1", question_id="qa")
        job_b = _job_id_for_question(service, "sub-1", "qb")
        await _wait_until(lambda: _state(service, job_b) is JobState.SUCCEEDED)
    finally:
        await service.shutdown()
    job_a_final = service.get_job(job_a)
    assert job_a_final is not None
    assert job_a_final.state is JobState.FAILED  # still an honest record: it really failed
    assert job_a_final.usable is True


async def test_mark_question_usable_falls_back_to_a_stale_version_with_no_active_job(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P1: confirm only reissues jobs that were still incomplete when the
    graph advanced (Issue #26); a question whose job had already reached a
    terminal state under an older version is never reissued, so the active
    version can have no row for it at all even though the question is very
    much still part of the active graph. mark_question_usable must fall
    back to the most recent terminal job for that question at any version,
    or such a question could never be resumed and its dependents would stay
    BLOCKED permanently.
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test(id="test-1"))
        uow.questions.add(make_question(id="qa", test_id="test-1", number="qa"))
        uow.questions.add(make_question(id="qb", test_id="test-1", number="qb"))
        uow.submissions.add(make_submission(id="sub-1", test_id="test-1"))
        edge = _edge("qa", "qb")
        v1 = DependencyGraph.from_candidates(
            id="test-1:v1",
            test_id="test-1",
            version=1,
            question_ids=["qa", "qb"],
            edges=[edge],
            created_at=at(),
        )
        uow.dependency_graphs.save(v1)
        assert (
            uow.dependency_graphs.try_confirm(v1.confirm(edges=[edge], confirmed_at=at())) is True
        )
        v2 = DependencyGraph.from_candidates(
            id="test-1:v2",
            test_id="test-1",
            version=2,
            question_ids=["qa", "qb"],
            edges=[edge],
            created_at=at(),
        )
        uow.dependency_graphs.save(v2)
        assert (
            uow.dependency_graphs.try_confirm(v2.confirm(edges=[edge], confirmed_at=at())) is True
        )

        # v1's qa job succeeded but was locked -- never reissued to v2 since
        # it was already terminal (not "incomplete") when v2 was confirmed.
        uow.jobs.add(
            Job(
                id="job-qa-v1",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qa",
                state=JobState.SUCCEEDED,
                usable=False,
                dependency_graph_version=1,
                created_at=at(),
                updated_at=at(),
            )
        )
        # v2's qb job: blocked on qa, at the active version -- no v2 job
        # exists for qa at all.
        uow.jobs.add(
            Job(
                id="job-qb-v2",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qb",
                state=JobState.BLOCKED,
                blocked_on_question_id="qa",
                dependency_graph_version=2,
                created_at=at(seconds=10),
                updated_at=at(seconds=10),
            )
        )
        uow.commit()

    service = JobQueueService(session_factory, FakeJobProcessor(), clock=clock)
    service.mark_question_usable(submission_id="sub-1", question_id="qa")

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        qa_v1 = uow.jobs.get("job-qa-v1")
        qb_v2 = uow.jobs.get("job-qb-v2")
    assert qa_v1 is not None and qa_v1.usable is True
    assert qb_v2 is not None and qb_v2.state is JobState.QUEUED


async def test_cancel_job_retries_after_a_compare_and_set_conflict(
    session_factory: sessionmaker[Session], clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2: if another writer changes a job's state between cancel_job's read
    and its compare-and-set write, that must be retried from a fresh read,
    not surfaced as an unhandled JobSaveConflict/500.
    """
    _seed(session_factory, question_ids=["qa"])
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.jobs.add(
            Job(
                id="job-1",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qa",
                state=JobState.QUEUED,
                dependency_graph_version=1,
                created_at=at(),
                updated_at=at(),
            )
        )
        uow.commit()

    real_save = SqlAlchemyJobRepository.save
    calls = {"count": 0}

    def _save_that_conflicts_once(
        self: SqlAlchemyJobRepository, job: Job, *, expected_state: JobState
    ) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise JobSaveConflict(job.id, expected_state)
        real_save(self, job, expected_state=expected_state)

    monkeypatch.setattr(SqlAlchemyJobRepository, "save", _save_that_conflicts_once)

    service = JobQueueService(session_factory, FakeJobProcessor(), clock=clock)
    cancelled = service.cancel_job("job-1")

    assert calls["count"] == 2
    assert cancelled.state is JobState.CANCELLED
    final = service.get_job("job-1")
    assert final is not None
    assert final.state is JobState.CANCELLED


async def test_worker_count_is_bounded_regardless_of_backlog_size(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P2: a large recovered/submitted backlog must not create one task per
    job -- only max_concurrency worker tasks should ever exist, however many
    jobs are queued at once.
    """
    question_ids = [f"q{i}" for i in range(50)]
    _seed(session_factory, question_ids=question_ids)
    hold = asyncio.Event()
    processor = FakeJobProcessor(hold_event=hold)
    service = JobQueueService(
        session_factory, processor, settings=QueueSettings(max_concurrency=2), clock=clock
    )
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        await _wait_until(lambda: processor.current_concurrency == 2)
        assert len(service._workers) == 2
    finally:
        hold.set()
        await service.shutdown()


# --------------------------------------------------------------------------- #
# Review round 3 regressions
# --------------------------------------------------------------------------- #
async def test_mark_question_usable_aborts_when_a_concurrent_retry_changes_the_jobs_state(
    session_factory: sessionmaker[Session], clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1: mark_question_usable's write must be a compare-and-set on the
    exact state it read, not an unconditional usable=True write -- otherwise
    a concurrent retry_job moving the same row FAILED -> QUEUED between this
    call's read and its write could still have both operations commit, with
    this call going on to release a dependent on the strength of a
    prerequisite that, in reality, is already being reprocessed.
    """
    version = _seed(session_factory, question_ids=["qa", "qb"], edges=[_edge("qa", "qb")])
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.jobs.add(
            Job(
                id="job-qa",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qa",
                state=JobState.FAILED,
                attempts=1,
                max_attempts=3,
                error_code=ErrorCategory.TIMEOUT,
                dependency_graph_version=version,
                created_at=at(),
                updated_at=at(),
            )
        )
        uow.jobs.add(
            Job(
                id="job-qb",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qb",
                state=JobState.BLOCKED,
                blocked_on_question_id="qa",
                dependency_graph_version=version,
                created_at=at(),
                updated_at=at(),
            )
        )
        uow.commit()

    real_mark_usable = SqlAlchemyJobRepository.mark_usable
    calls = {"count": 0}

    def _mark_usable_racing_a_concurrent_retry(
        self: SqlAlchemyJobRepository, job_id: str, *, usable: bool, expected_state: JobState
    ) -> bool:
        calls["count"] += 1
        if calls["count"] == 1:
            # Simulate a concurrent retry_job winning the race between this
            # call's own read and its compare-and-set: flip the row to
            # QUEUED first, durably, on a separate unit of work.
            with SqlAlchemyUnitOfWork(session_factory) as inner:
                job = inner.jobs.get(job_id)
                assert job is not None
                requeued = job.transitioned_to(JobState.QUEUED, updated_at=at())
                inner.jobs.save(requeued, expected_state=JobState.FAILED)
                inner.commit()
        return real_mark_usable(self, job_id, usable=usable, expected_state=expected_state)

    monkeypatch.setattr(
        SqlAlchemyJobRepository, "mark_usable", _mark_usable_racing_a_concurrent_retry
    )

    service = JobQueueService(session_factory, FakeJobProcessor(), clock=clock)
    with pytest.raises(JobNotFoundError):
        service.mark_question_usable(submission_id="sub-1", question_id="qa")

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        qa_final = uow.jobs.get("job-qa")
        qb_final = uow.jobs.get("job-qb")
    assert qa_final is not None
    assert qa_final.state is JobState.QUEUED  # the concurrent retry's write stands
    assert qa_final.usable is None  # never flipped: this call's CAS lost
    assert qb_final is not None
    assert qb_final.state is JobState.BLOCKED  # never spuriously released


class _ManualBackoffClock:
    """A clock whose ``sleep`` blocks on a fresh, per-call `asyncio.Event`
    kept in `pending` -- lets a test release one specific backoff timer
    without affecting any other still-sleeping timer."""

    def __init__(self, start: datetime) -> None:
        self._now = start
        self.pending: list[asyncio.Event] = []

    def now(self) -> datetime:
        return self._now

    async def sleep(self, seconds: float) -> None:
        event = asyncio.Event()
        self.pending.append(event)
        await event.wait()


async def test_a_stale_backoff_timer_does_not_requeue_a_newer_failed_attempt(
    session_factory: sessionmaker[Session],
) -> None:
    """P1: if a manual retry_job requeues a job while its earlier backoff
    timer is still sleeping, and the new attempt fails again before that
    stale timer wakes, the stale timer must not requeue the newer failure --
    it belongs to an earlier attempt and would otherwise either bypass the
    newer attempt's own, correctly-timed backoff or wrongly revive a
    newer failure that had already exhausted its retries.
    """
    _seed(session_factory, question_ids=["qa"])
    clock = _ManualBackoffClock(EPOCH)
    processor = FakeJobProcessor(
        default=ProcessingResult(
            outcome=ProcessingOutcome.FAILED, error_category=ErrorCategory.TIMEOUT
        )
    )
    service = JobQueueService(
        session_factory, processor, settings=QueueSettings(max_attempts=5), clock=clock
    )
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_id = _job_id_for_question(service, "sub-1", "qa")
        await _wait_until(lambda: _state(service, job_id) is JobState.FAILED)
        await _wait_until(lambda: len(clock.pending) == 1)
        first_attempt = service.get_job(job_id)
        assert first_attempt is not None and first_attempt.attempts == 1

        # A manual retry while the first backoff timer is still sleeping.
        service.retry_job(job_id)
        await _wait_until(
            lambda: (
                (job := service.get_job(job_id)) is not None
                and job.state is JobState.FAILED
                and job.attempts == 2
            )
        )
        await _wait_until(lambda: len(clock.pending) == 2)

        # Release only the first, now-stale timer; the second (current)
        # attempt's own timer is left sleeping.
        clock.pending[0].set()
        await asyncio.sleep(0.05)  # give it a chance to (incorrectly) act

        job = service.get_job(job_id)
        assert job is not None
        assert job.state is JobState.FAILED  # not requeued by the stale timer
        assert job.attempts == 2  # untouched
    finally:
        for event in clock.pending:
            event.set()
        await service.shutdown()


async def test_a_finalize_conflict_does_not_kill_the_worker(
    session_factory: sessionmaker[Session], clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1: if a job's RUNNING row is changed concurrently (e.g. cancelled via
    a dependency-graph confirm reissue) between _run_one's own read and
    _finalize_result's compare-and-set write, the resulting JobSaveConflict
    must be absorbed as a no-op, not allowed to propagate out of
    _worker_loop -- otherwise it permanently removes one of the pool's fixed
    workers, and at max_concurrency=1 the whole queue stops forever.
    """
    _seed(session_factory, test_id="test-a", submission_id="sub-a", question_ids=["qa"])
    _seed(session_factory, test_id="test-b", submission_id="sub-b", question_ids=["qb"])
    real_save = SqlAlchemyJobRepository.save
    finalize_calls = {"count": 0}

    def _save_that_conflicts_once_on_finalize(
        self: SqlAlchemyJobRepository, job: Job, *, expected_state: JobState
    ) -> None:
        if expected_state is JobState.RUNNING:
            finalize_calls["count"] += 1
            if finalize_calls["count"] == 1:
                raise JobSaveConflict(job.id, expected_state)
        real_save(self, job, expected_state=expected_state)

    monkeypatch.setattr(SqlAlchemyJobRepository, "save", _save_that_conflicts_once_on_finalize)

    processor = FakeJobProcessor()
    service = JobQueueService(
        session_factory, processor, settings=QueueSettings(max_concurrency=1), clock=clock
    )
    await service.start()
    try:
        service.submit_submission(submission_id="sub-a")
        job_a = _job_id_for_question(service, "sub-a", "qa")
        # job_a's own RUNNING -> SUCCEEDED save hits the injected conflict
        # and is absorbed; give it a moment to be finalized (as a no-op).
        await asyncio.sleep(0.05)
        assert finalize_calls["count"] == 1
        assert _state(service, job_a) is JobState.RUNNING  # left for the real winner to own

        # The worker must have returned to the pool and be free to pick up
        # an unrelated submission's job -- it must not have died with the
        # absorbed conflict.
        service.submit_submission(submission_id="sub-b")
        job_b = _job_id_for_question(service, "sub-b", "qb")
        await _wait_until(lambda: _state(service, job_b) is JobState.SUCCEEDED)
    finally:
        await service.shutdown()


async def test_startup_sweep_does_not_requeue_an_approved_failed_job(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P1: a retryable FAILED job whose downstream effect a human already
    approved via mark_question_usable (Job.usable is not None) must not be
    swept up by start()'s automatic-retry recovery -- requeuing it would
    silently discard that approval the next time it finalizes
    (transitioned_to always resets usable on a fresh transition), even
    though a dependent may already have been released on the strength of it.
    """
    version = _seed(session_factory, question_ids=["qa"])
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.jobs.add(
            Job(
                id="job-1",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qa",
                state=JobState.FAILED,
                attempts=1,
                max_attempts=3,
                error_code=ErrorCategory.TIMEOUT,
                usable=True,  # already approved by a human
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
    job = service.get_job("job-1")
    assert job is not None
    assert job.state is JobState.FAILED  # left exactly as approved
    assert job.usable is True
    assert processor.calls == []


async def test_backoff_requeue_does_not_override_an_approval_made_while_sleeping(
    session_factory: sessionmaker[Session],
) -> None:
    """P1: mirror of the startup-sweep guard above, for the in-process
    backoff-timer path -- if a human approves a FAILED job's downstream
    effect (mark_question_usable) while its backoff timer is still sleeping,
    the timer must not requeue it once it wakes; that would silently clear
    the just-granted approval.
    """
    _seed(session_factory, question_ids=["qa", "qb"], edges=[_edge("qa", "qb")])
    clock = _HoldableClock(EPOCH)
    processor = FakeJobProcessor()
    processor.script(
        "sub-1",
        "qa",
        [ProcessingResult(outcome=ProcessingOutcome.FAILED, error_category=ErrorCategory.TIMEOUT)],
    )
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_a = _job_id_for_question(service, "sub-1", "qa")
        await _wait_until(lambda: _state(service, job_a) is JobState.FAILED)
        # job_a is now sleeping out its backoff (clock.sleep blocks on hold).

        service.mark_question_usable(submission_id="sub-1", question_id="qa")
        job_b = _job_id_for_question(service, "sub-1", "qb")
        await _wait_until(lambda: _state(service, job_b) is JobState.QUEUED)

        clock.hold.set()  # let the now-stale backoff timer wake up
        await asyncio.sleep(0.05)

        job_a_final = service.get_job(job_a)
        assert job_a_final is not None
        assert job_a_final.state is JobState.FAILED  # not requeued
        assert job_a_final.usable is True  # approval preserved
    finally:
        clock.hold.set()
        await service.shutdown()


async def test_retry_job_retries_after_a_compare_and_set_conflict(
    session_factory: sessionmaker[Session], clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2: if another writer changes a job's state between retry_job's read
    and its compare-and-set write (two concurrent manual retries, or a
    backoff-driven requeue), that must be retried from a fresh read, not
    surfaced as an unhandled JobSaveConflict/500.
    """
    version = _seed(session_factory, question_ids=["qa"])
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.jobs.add(
            Job(
                id="job-1",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qa",
                state=JobState.FAILED,
                attempts=1,
                max_attempts=3,
                error_code=ErrorCategory.TIMEOUT,
                dependency_graph_version=version,
                created_at=at(),
                updated_at=at(),
            )
        )
        uow.commit()

    real_save = SqlAlchemyJobRepository.save
    calls = {"count": 0}

    def _save_that_conflicts_once(
        self: SqlAlchemyJobRepository, job: Job, *, expected_state: JobState
    ) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise JobSaveConflict(job.id, expected_state)
        real_save(self, job, expected_state=expected_state)

    monkeypatch.setattr(SqlAlchemyJobRepository, "save", _save_that_conflicts_once)

    service = JobQueueService(session_factory, FakeJobProcessor(), clock=clock)
    retried = service.retry_job("job-1")

    assert calls["count"] == 2
    assert retried.state is JobState.QUEUED
    final = service.get_job("job-1")
    assert final is not None
    assert final.state is JobState.QUEUED


async def test_shutdown_stops_a_worker_after_its_current_job_instead_of_draining_the_backlog(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P2: shutdown's _STOP sentinels sit at the *back* of the FIFO queue --
    without the _closing flag, a worker would keep dequeuing and processing
    every already-QUEUED job ahead of its own sentinel before honoring
    shutdown, however large that persisted backlog is. _closing must let a
    worker stop as soon as it dequeues anything once shutdown has begun,
    leaving the rest of the backlog QUEUED in the DB for start()'s next
    sweep.
    """
    question_ids = [f"q{i}" for i in range(5)]
    _seed(session_factory, question_ids=question_ids)
    hold = asyncio.Event()
    processor = FakeJobProcessor(hold_event=hold)
    service = JobQueueService(
        session_factory, processor, settings=QueueSettings(max_concurrency=1), clock=clock
    )
    await service.start()
    service.submit_submission(submission_id="sub-1")
    await _wait_until(lambda: processor.current_concurrency == 1)

    shutdown_task = asyncio.create_task(service.shutdown())
    await asyncio.sleep(0.02)  # let shutdown mark _closing and queue its _STOP
    hold.set()  # release the one job the worker is already holding
    await shutdown_task

    assert len(processor.calls) == 1  # never drained the rest of the backlog
    remaining = {job.question_id: job.state for job in service.list_for_submission("sub-1")}
    processed_question_id = processor.calls[0].question_id
    for question_id, state in remaining.items():
        if question_id == processed_question_id:
            assert state is JobState.SUCCEEDED
        else:
            assert state is JobState.QUEUED  # abandoned in the DB, not processed
