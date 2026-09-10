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
from datetime import datetime, timedelta

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
from auto_scoring.domain.models import (
    ErrorCategory,
    Job,
    JobKind,
    JobSaveConflict,
    JobState,
    SubmissionState,
)
from auto_scoring.jobs.clock import Clock
from auto_scoring.jobs.queue import (
    JobCancelRejectedError,
    JobQueueService,
    JobResumeConflictError,
    JobRetryRejectedError,
)
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
async def test_retry_succeeds_after_a_timeout_then_a_rate_limit_with_each_ones_own_schedule(
    session_factory: sessionmaker[Session], clock: FakeClock, fast_settings: QueueSettings
) -> None:
    """TIMEOUT uses `QueueSettings`' plain exponential schedule; RATE_LIMITED
    (Issue #153) uses its own, separate one -- pinned here by injecting
    jitter=0.0 (the minimum of the "equal jitter" range) so the second delay
    is exactly reproducible instead of merely "greater than the first"."""
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
    service = JobQueueService(
        session_factory,
        processor,
        settings=fast_settings,
        clock=clock,
        random_source=lambda: 0.0,
    )
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
    # 1.0s: TIMEOUT's own (unchanged) delay_seconds(1) with fast_settings'
    # initial_backoff_seconds=1.0. 5.0s: RATE_LIMITED's default schedule
    # (initial 5.0s * 2^(2-1) = 10.0, halved by "equal jitter" at jitter=0.0)
    # -- *not* fast_settings' 1s/2s schedule, and not delay_seconds(2)==2.0.
    assert clock.sleep_calls == [1.0, 5.0]


async def test_5xx_does_not_retry_past_max_attempts(
    session_factory: sessionmaker[Session], clock: FakeClock
) -> None:
    """Issue #18 acceptance: "429時に無制限retryしない" -- unaffected by
    Issue #153 for SERVER_ERROR/TIMEOUT, which still stop at max_attempts."""
    _seed(session_factory, question_ids=["qa"])
    processor = FakeJobProcessor(
        default=ProcessingResult(
            outcome=ProcessingOutcome.FAILED, error_category=ErrorCategory.SERVER_ERROR
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
    assert job.error_code is ErrorCategory.SERVER_ERROR
    assert len(processor.calls) == 2


async def test_rate_limited_failures_keep_retrying_past_five_seconds_of_total_wait(
    session_factory: sessionmaker[Session], clock: FakeClock
) -> None:
    """Issue #153: real incident. A real run hit 429 twice and the job
    exhausted all 3 attempts (the old 1s + 2s schedule, `max_attempts=3`)
    within 5 seconds, handing the question to a human even though a later
    manual retry from the review screen succeeded immediately. Waiting
    longer would have worked; three quick attempts just re-hit the same
    provider congestion window three times.

    Against the pre-fix `RetryPolicy`/`QueueSettings` (`max_attempts=3`,
    `initial_backoff_seconds=1.0`, `backoff_multiplier=2.0` applied to every
    retryable category alike), this test fails: the job gives up
    (`state is FAILED`) after only 3 attempts and 1.0 + 2.0 == 3.0 seconds of
    total simulated wait -- well under 5. This was confirmed red against
    that implementation before `RetryPolicy` grew a separate RATE_LIMITED
    schedule and wait-time budget (see PR description / worker report).
    """
    _seed(session_factory, question_ids=["qa"])
    processor = FakeJobProcessor(
        default=ProcessingResult(
            outcome=ProcessingOutcome.FAILED, error_category=ErrorCategory.RATE_LIMITED
        ),
    )
    # Plain production-shaped defaults: QueueSettings()'s own max_attempts=3
    # must not cut this short -- RATE_LIMITED is bounded by the wait-time
    # budget instead (Issue #153 decision).
    service = JobQueueService(session_factory, processor, settings=QueueSettings(), clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_id = _job_id_for_question(service, "sub-1", "qa")
        # Waits for the *final* terminal FAILED, not merely the first time
        # the state reads FAILED: for a retryable category FAILED is a
        # transient state the retry scheduler flips back to QUEUED moments
        # later, and `FakeClock.sleep` doesn't actually block real time, so
        # polling on state alone can observe an intermediate attempt's
        # FAILED row before the scheduler gets to run again -- checking
        # `attempts` reached the deterministic give-up count (independent of
        # jitter, which only affects the actual delay, not the nominal
        # cumulative budget decision) makes this wait race-free rather than
        # papering over the race with an extra fixed sleep.
        await _wait_until(
            lambda: (
                (job := service.get_job(job_id)) is not None
                and job.state is JobState.FAILED
                and job.attempts == 6
            ),
            timeout=10.0,
        )
    finally:
        await service.shutdown()
    job = service.get_job(job_id)
    assert job is not None
    assert job.state is JobState.FAILED
    assert job.error_code is ErrorCategory.RATE_LIMITED
    # max_attempts=3 (QueueSettings()'s own default) did not cut this short:
    # the job ran 6 attempts, and the total simulated wait comfortably
    # clears the 5-second window that lost the real run's question to a
    # human.
    assert job.attempts == 6
    assert sum(clock.sleep_calls) > 5.0


async def test_rate_limited_gives_up_once_the_wait_time_budget_is_spent(
    session_factory: sessionmaker[Session], clock: FakeClock
) -> None:
    """Issue #153 acceptance: once the (default 120s) budget is spent, the
    job gives up and the failure is legible as provider congestion, not a
    generic error -- `ErrorCategory.RATE_LIMITED` plus its own message."""
    _seed(session_factory, question_ids=["qa"])
    processor = FakeJobProcessor(
        default=ProcessingResult(
            outcome=ProcessingOutcome.FAILED,
            error_category=ErrorCategory.RATE_LIMITED,
            error_message="rate limited",
        ),
    )
    settings = QueueSettings(
        rate_limited_initial_backoff_seconds=5.0,
        rate_limited_backoff_multiplier=2.0,
        rate_limited_max_backoff_seconds=60.0,
        rate_limited_budget_seconds=120.0,
    )
    service = JobQueueService(
        session_factory, processor, settings=settings, clock=clock, random_source=lambda: 0.0
    )
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_id = _job_id_for_question(service, "sub-1", "qa")
        # See the identical comment in
        # test_rate_limited_failures_keep_retrying_past_five_seconds_of_total_wait
        # for why this waits on the exact terminal attempts count rather
        # than on state alone.
        await _wait_until(
            lambda: (
                (job := service.get_job(job_id)) is not None
                and job.state is JobState.FAILED
                and job.attempts == 6
            ),
            timeout=10.0,
        )
    finally:
        await service.shutdown()
    job = service.get_job(job_id)
    assert job is not None
    # Nominal schedule (5, 10, 20, 40, 60, 60, ...): cumulative before the
    # 6th attempt is 5+10+20+40=75 (<120, retried); before the 7th it is
    # 75+60=135 (>=120, gives up) -- so exactly 6 attempts are made.
    assert job.attempts == 6
    assert job.error_code is ErrorCategory.RATE_LIMITED
    assert job.last_error == "rate limited"


async def test_rate_limited_honours_retry_after_instead_of_the_exponential_schedule(
    session_factory: sessionmaker[Session], clock: FakeClock
) -> None:
    """Issue #153 decision: "Retry-After があれば必ず尊重する"."""
    _seed(session_factory, question_ids=["qa"])
    processor = FakeJobProcessor()
    processor.script(
        "sub-1",
        "qa",
        [
            ProcessingResult(
                outcome=ProcessingOutcome.FAILED,
                error_category=ErrorCategory.RATE_LIMITED,
                retry_after_seconds=17.0,
            ),
        ],
    )
    service = JobQueueService(
        session_factory,
        processor,
        settings=QueueSettings(),
        clock=clock,
        # jitter=0.99 would move the plain exponential schedule's delay
        # close to 10.0 -- proving the actual sleep came from retry_after,
        # not from ignoring jitter by coincidence.
        random_source=lambda: 0.99,
    )
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_id = _job_id_for_question(service, "sub-1", "qa")
        await _wait_until(lambda: _state(service, job_id) is JobState.SUCCEEDED)
    finally:
        await service.shutdown()
    assert clock.sleep_calls == [17.0]


async def test_rate_limited_gives_up_immediately_when_retry_after_exceeds_the_budget(
    session_factory: sessionmaker[Session], clock: FakeClock
) -> None:
    """Issue #153 decision: a Retry-After bigger than the whole wait-time
    budget is not worth waiting out -- fail now, without sleeping at all,
    rather than blocking this job's worth of retries on one huge wait."""
    _seed(session_factory, question_ids=["qa"])
    processor = FakeJobProcessor(
        default=ProcessingResult(
            outcome=ProcessingOutcome.FAILED,
            error_category=ErrorCategory.RATE_LIMITED,
            retry_after_seconds=999.0,
        ),
    )
    settings = QueueSettings(rate_limited_budget_seconds=120.0)
    service = JobQueueService(session_factory, processor, settings=settings, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_id = _job_id_for_question(service, "sub-1", "qa")
        await _wait_until(lambda: _state(service, job_id) is JobState.FAILED)
    finally:
        await service.shutdown()
    job = service.get_job(job_id)
    assert job is not None
    assert job.attempts == 1
    assert clock.sleep_calls == []


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


async def test_a_job_that_did_nothing_says_so_on_its_own_row(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """Issue #164. A processor that finds nothing to do keeps SUCCEEDED --
    nothing is wrong and nothing is retryable -- but `last_error` is the one
    field the queue, the API and the screen already read for "why is this job
    like this". Left NULL, doing nothing looked exactly like doing the work:
    23 of one real run's 37 grading jobs were succeeded / usable=0 /
    last_error NULL / 0.013 seconds.

    ``error_code`` stays NULL, which is what keeps this out of the retry
    path.
    """
    _seed(session_factory, question_ids=["qa"])
    processor = FakeJobProcessor()
    processor.script(
        "sub-1",
        "qa",
        [
            ProcessingResult(
                outcome=ProcessingOutcome.SUCCEEDED,
                usable=False,
                skipped_reason="no_answer_area_defined",
            )
        ],
    )
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_id = _job_id_for_question(service, "sub-1", "qa")
        await _wait_until(lambda: _state(service, job_id) is JobState.SUCCEEDED)
        job = service.get_job(job_id)
        assert job is not None
        assert job.last_error == "no_answer_area_defined"
        assert job.error_code is None
    finally:
        await service.shutdown()


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
        self: SqlAlchemyJobRepository,
        job: Job,
        *,
        expected_state: JobState,
        expected_attempts: int | None = None,
        require_usable_unset: bool = False,
    ) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise JobSaveConflict(job.id, expected_state)
        real_save(
            self,
            job,
            expected_state=expected_state,
            expected_attempts=expected_attempts,
            require_usable_unset=require_usable_unset,
        )

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

    The CAS loses here, so this attempt retries from a fresh read; that read
    now sees the active version's own row as QUEUED (not terminal), which
    review round 4's fix (see the round 4 test below) raises
    JobResumeConflictError for directly, rather than falling back to a
    stale terminal job from an older version.
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
        self: SqlAlchemyJobRepository,
        job_id: str,
        *,
        usable: bool,
        expected_state: JobState,
        expected_attempts: int,
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
        return real_mark_usable(
            self,
            job_id,
            usable=usable,
            expected_state=expected_state,
            expected_attempts=expected_attempts,
        )

    monkeypatch.setattr(
        SqlAlchemyJobRepository, "mark_usable", _mark_usable_racing_a_concurrent_retry
    )

    service = JobQueueService(session_factory, FakeJobProcessor(), clock=clock)
    with pytest.raises(JobResumeConflictError):
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
    kept in `pending` -- lets a test release one specific backoff wait.

    The single retry-scheduler task (review round 7, P2) only ever awaits
    one `sleep` call at a time, so `pending` grows one entry at a time, in
    sequence, rather than accumulating several concurrently-sleeping calls
    the way the old one-task-per-retry design did.
    """

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

        # Release the first, now-stale timer -- the single scheduler task
        # was still sleeping it out (attempt 2's own entry just sits in the
        # heap until this one is serviced). It must recognize the mismatch
        # (attempts=2 now, but this timer was scheduled for attempt 1) and
        # skip requeuing, then move on to service attempt 2's own entry --
        # which starts a *second* sleep call only now, in sequence.
        clock.pending[0].set()
        await _wait_until(lambda: len(clock.pending) == 2)

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
        self: SqlAlchemyJobRepository,
        job: Job,
        *,
        expected_state: JobState,
        expected_attempts: int | None = None,
        require_usable_unset: bool = False,
    ) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise JobSaveConflict(job.id, expected_state)
        real_save(
            self,
            job,
            expected_state=expected_state,
            expected_attempts=expected_attempts,
            require_usable_unset=require_usable_unset,
        )

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


# --------------------------------------------------------------------------- #
# Review round 4 regressions
# --------------------------------------------------------------------------- #
async def test_mark_question_usable_rejects_when_the_active_version_job_is_not_terminal(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P2: the "active version has no row at all" fallback must only fire
    when that is actually true -- not merely when the active version's row
    isn't terminal yet. If it is still QUEUED/RUNNING/BLOCKED (e.g. a
    concurrent retry_job just requeued it, or confirm just created a fresh
    replacement), falling back to a stale terminal job from an older
    version would approve a superseded result while the real, active
    attempt is still pending, and its dependent would proceed on an
    outcome nobody has actually confirmed yet.
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

        # v1's qa job: terminal, but stale -- superseded by v2's own row.
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
        # v2's qa job: the active version's own row, still QUEUED (e.g. a
        # concurrent retry_job just requeued it).
        uow.jobs.add(
            Job(
                id="job-qa-v2",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qa",
                state=JobState.QUEUED,
                dependency_graph_version=2,
                created_at=at(seconds=10),
                updated_at=at(seconds=10),
            )
        )
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
    with pytest.raises(JobResumeConflictError):
        service.mark_question_usable(submission_id="sub-1", question_id="qa")

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        qa_v1 = uow.jobs.get("job-qa-v1")
        qa_v2 = uow.jobs.get("job-qa-v2")
        qb_v2 = uow.jobs.get("job-qb-v2")
    assert qa_v1 is not None and qa_v1.usable is False  # untouched: stale, never approved
    assert qa_v2 is not None and qa_v2.state is JobState.QUEUED  # untouched
    assert qb_v2 is not None and qb_v2.state is JobState.BLOCKED  # never spuriously released


async def test_retry_job_rejects_an_already_approved_failed_job(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P2: retry_job must refuse a FAILED job whose usable bit is already
    set -- a human approved its downstream effect via mark_question_usable,
    and its dependent may already be running or done on the strength of
    that approval. transitioned_to unconditionally clears usable on
    FAILED -> QUEUED, but nothing re-blocks the already-released dependent
    to match.
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
                usable=True,  # already approved by a human
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
                state=JobState.QUEUED,  # already released on the strength of the approval
                dependency_graph_version=version,
                created_at=at(),
                updated_at=at(),
            )
        )
        uow.commit()

    service = JobQueueService(session_factory, FakeJobProcessor(), clock=clock)
    with pytest.raises(JobRetryRejectedError):
        service.retry_job("job-qa")

    job = service.get_job("job-qa")
    assert job is not None
    assert job.state is JobState.FAILED  # untouched
    assert job.usable is True  # approval preserved


async def test_shutdown_leaves_the_queue_clean_for_a_later_start(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P2: shutdown must not leave unconsumed job ids or _STOP sentinels
    sitting in the in-memory queue -- a later start() on this same service
    (e.g. a second FastAPI app lifespan) would otherwise have its freshly-
    spawned worker dequeue a stale _STOP left over from the previous
    shutdown and exit immediately, permanently stranding whatever backlog
    that start()'s own DB sweep just re-enqueued.
    """
    question_ids = [f"q{i}" for i in range(3)]
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
    hold.set()  # let the one held job finish; shutdown abandons the rest
    await shutdown_task

    remaining_before_restart = [job.state for job in service.list_for_submission("sub-1")]
    assert remaining_before_restart.count(JobState.QUEUED) == 2  # abandoned, per the P2 above

    try:
        await service.start()  # a later lifespan, reusing this same service instance
        await _wait_until(
            lambda: all(
                _state(service, j.id) is JobState.SUCCEEDED
                for j in service.list_for_submission("sub-1")
            )
        )
    finally:
        await service.shutdown()


# --------------------------------------------------------------------------- #
# Review round 5 regressions
# --------------------------------------------------------------------------- #
async def test_retry_job_loses_to_a_concurrent_approval_that_lands_mid_write(
    session_factory: sessionmaker[Session], clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1: retry_job's own read seeing usable=None is not enough to be sure
    no approval is landing -- a concurrent mark_question_usable call can
    still commit usable=True in the window between that read and retry_job's
    own write, and a state-only compare-and-set would never notice
    (mark_usable never touches `state`). require_usable_unset=True closes
    that window: the approval landing first makes retry's own save lose
    instead of silently clearing it, and the retry then correctly rejects on
    a fresh read.
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
                state=JobState.QUEUED,
                dependency_graph_version=version,
                created_at=at(),
                updated_at=at(),
            )
        )
        uow.commit()

    real_save = SqlAlchemyJobRepository.save
    calls = {"count": 0}

    def _save_races_a_concurrent_approval(
        self: SqlAlchemyJobRepository,
        job: Job,
        *,
        expected_state: JobState,
        expected_attempts: int | None = None,
        require_usable_unset: bool = False,
    ) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            # Simulate mark_question_usable committing usable=True in the
            # window between retry_job's own read and this write. This must
            # be independently committed on its own unit of work -- retry_job's
            # own `with SqlAlchemyUnitOfWork(...)` rolls back on the
            # JobSaveConflict this call is about to raise, which would
            # silently undo a same-session write instead of leaving it
            # standing the way a genuinely concurrent commit would.
            with SqlAlchemyUnitOfWork(session_factory) as inner:
                assert (
                    inner.jobs.mark_usable(
                        job.id,
                        usable=True,
                        expected_state=JobState.FAILED,
                        expected_attempts=job.attempts,
                    )
                    is True
                )
                inner.commit()
        real_save(
            self,
            job,
            expected_state=expected_state,
            expected_attempts=expected_attempts,
            require_usable_unset=require_usable_unset,
        )

    monkeypatch.setattr(SqlAlchemyJobRepository, "save", _save_races_a_concurrent_approval)

    service = JobQueueService(session_factory, FakeJobProcessor(), clock=clock)
    with pytest.raises(JobRetryRejectedError):
        service.retry_job("job-qa")

    assert calls["count"] == 1  # the first save attempt lost to the approval; never retried
    job = service.get_job("job-qa")
    assert job is not None
    assert job.state is JobState.FAILED  # untouched
    assert job.usable is True  # the approval, not the retry, won


async def test_cancel_job_rejects_an_already_approved_failed_job(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P2: cancel_job must refuse a FAILED job whose usable bit is already
    set, mirroring retry_job's own guard -- a human approved its downstream
    effect via mark_question_usable, and its dependent may already be
    queued or running on the strength of that approval. transitioned_to
    would clear usable on this FAILED -> CANCELLED transition without ever
    re-blocking that already-released dependent, leaving it to keep
    processing against a prerequisite now recorded as cancelled.
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
                usable=True,  # already approved by a human
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
                state=JobState.QUEUED,  # already released on the strength of the approval
                dependency_graph_version=version,
                created_at=at(),
                updated_at=at(),
            )
        )
        uow.commit()

    service = JobQueueService(session_factory, FakeJobProcessor(), clock=clock)
    with pytest.raises(JobCancelRejectedError):
        service.cancel_job("job-qa")

    job = service.get_job("job-qa")
    assert job is not None
    assert job.state is JobState.FAILED  # untouched
    assert job.usable is True  # approval preserved


async def test_start_preserves_remaining_backoff_instead_of_requeuing_immediately(
    session_factory: sessionmaker[Session],
) -> None:
    """P2: a retryable FAILED job recovered at startup must wait out only
    what's left of its backoff, not be requeued immediately -- otherwise a
    quick restart during a long rate-limit delay would hit the provider
    again right away, defeating the exponential backoff this job was
    already sleeping out before the process died.
    """
    version = _seed(session_factory, question_ids=["qa"])
    settings = QueueSettings(
        max_attempts=3,
        initial_backoff_seconds=100.0,
        backoff_multiplier=2.0,
        max_backoff_seconds=200.0,
    )
    # The job failed (and its updated_at was bumped) at EPOCH; this
    # "restart" happens 40s later -- 40s of the full 100s backoff for
    # attempt 1 has already elapsed.
    clock = FakeClock(EPOCH + timedelta(seconds=40))
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

    processor = FakeJobProcessor()
    service = JobQueueService(session_factory, processor, settings=settings, clock=clock)
    await service.start()
    try:
        await _wait_until(lambda: _state(service, "job-1") is JobState.SUCCEEDED)
    finally:
        await service.shutdown()
    job = service.get_job("job-1")
    assert job is not None
    assert job.attempts == 2
    # Full backoff for attempt 1 is 100s; 40s had already elapsed by the
    # time this "restart" happened -- only the remaining 60s should ever be
    # slept, never the full 100s (defeats the point) and never 0 (an
    # immediate requeue).
    assert clock.sleep_calls == [60.0]


# --------------------------------------------------------------------------- #
# Review round 6 regressions
# --------------------------------------------------------------------------- #
async def test_mark_usable_does_not_apply_a_stale_approval_across_a_full_aba_retry_cycle(
    session_factory: sessionmaker[Session], clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1: mark_question_usable's compare-and-set on `state` alone cannot
    tell a FAILED row it read apart from a *different*, later FAILED row --
    FAILED is not a dead end, so a concurrent retry can complete a whole
    FAILED -> QUEUED -> RUNNING -> FAILED cycle (a fresh, unreviewed
    attempt) in the window between this call's read and its write, and the
    state predicate alone would match again. Pinning the CAS to `attempts`
    too must make that first attempt lose instead of silently applying an
    approval read for the earlier attempt to the later, unreviewed one --
    the retry that follows then correctly re-evaluates against the fresh
    (current) attempt.
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
                max_attempts=5,
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

    def _mark_usable_after_a_full_aba_retry_cycle(
        self: SqlAlchemyJobRepository,
        job_id: str,
        *,
        usable: bool,
        expected_state: JobState,
        expected_attempts: int,
    ) -> bool:
        calls["count"] += 1
        if calls["count"] == 1:
            # Simulate a concurrent retry_job completing a full cycle back
            # to FAILED -- a brand new, unreviewed attempt -- in the window
            # between this call's own read (attempts=1) and its write.
            # Independently committed so it survives this call's own uow
            # rolling back on a lost CAS.
            with SqlAlchemyUnitOfWork(session_factory) as inner:
                job = inner.jobs.get(job_id)
                assert job is not None
                requeued = job.transitioned_to(JobState.QUEUED, updated_at=at(seconds=1))
                inner.jobs.save(requeued, expected_state=JobState.FAILED)
                running = requeued.transitioned_to(JobState.RUNNING, updated_at=at(seconds=2))
                inner.jobs.save(running, expected_state=JobState.QUEUED)
                failed_again = running.transitioned_to(
                    JobState.FAILED,
                    updated_at=at(seconds=3),
                    error_code=ErrorCategory.TIMEOUT,
                )
                inner.jobs.save(failed_again, expected_state=JobState.RUNNING)
                inner.commit()
        return real_mark_usable(
            self,
            job_id,
            usable=usable,
            expected_state=expected_state,
            expected_attempts=expected_attempts,
        )

    monkeypatch.setattr(
        SqlAlchemyJobRepository, "mark_usable", _mark_usable_after_a_full_aba_retry_cycle
    )

    service = JobQueueService(session_factory, FakeJobProcessor(), clock=clock)
    service.mark_question_usable(submission_id="sub-1", question_id="qa")

    assert calls["count"] == 2  # the first attempt lost to the ABA cycle and had to be retried
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        qa_final = uow.jobs.get("job-qa")
        qb_final = uow.jobs.get("job-qb")
    assert qa_final is not None
    assert qa_final.attempts == 2  # approved against the current attempt, not the stale one
    assert qa_final.usable is True
    assert qb_final is not None
    assert qb_final.state is JobState.QUEUED  # released on the strength of the fresh approval


# --------------------------------------------------------------------------- #
# Review round 7 regressions
# --------------------------------------------------------------------------- #
async def test_an_unexpected_run_one_error_does_not_kill_the_worker(
    session_factory: sessionmaker[Session], clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1: an unexpected exception from _run_one itself (e.g. a transient
    SQLAlchemy OperationalError from a SQLite busy-timeout while claiming or
    finalizing a job) must not kill the long-lived worker task processing
    it -- nothing else in the fixed pool ever replaces a dead worker, so at
    max_concurrency=1 the whole queue would stop until a restart. The
    affected job itself must not be stranded either: the worker restores
    its dispatch signal (review round 8, P1) instead of only logging and
    moving on to other work, so it still completes once the transient
    condition clears, rather than sitting QUEUED until a full restart.
    """
    _seed(session_factory, test_id="test-a", submission_id="sub-a", question_ids=["qa"])
    _seed(session_factory, test_id="test-b", submission_id="sub-b", question_ids=["qb"])

    real_get = SqlAlchemyJobRepository.get
    calls = {"count": 0}

    def _get_raises_once(self: SqlAlchemyJobRepository, job_id: str) -> Job | None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("simulated transient infra error")
        return real_get(self, job_id)

    monkeypatch.setattr(SqlAlchemyJobRepository, "get", _get_raises_once)

    processor = FakeJobProcessor()
    service = JobQueueService(
        session_factory, processor, settings=QueueSettings(max_concurrency=1), clock=clock
    )
    await service.start()
    try:
        service.submit_submission(submission_id="sub-a")
        job_a = _job_id_for_question(service, "sub-a", "qa")
        # Wait for the *worker's own* first claim-read to hit the injected
        # error -- checking calls["count"] directly, rather than polling
        # via _state() (which itself calls the patched get() and could race
        # to be the one that hits it instead of the worker).
        await _wait_until(lambda: calls["count"] >= 1)

        # The worker must restore job_a's dispatch signal and let it
        # succeed normally instead of leaving it stuck QUEUED.
        await _wait_until(lambda: _state(service, job_a) is JobState.SUCCEEDED)
        assert calls["count"] > 1  # the retried attempt really did happen

        # The worker must also still be alive to pick up an unrelated
        # submission's job -- it must not have died with the error.
        service.submit_submission(submission_id="sub-b")
        job_b = _job_id_for_question(service, "sub-b", "qb")
        await _wait_until(lambda: _state(service, job_b) is JobState.SUCCEEDED)
    finally:
        await service.shutdown()


async def test_retry_backoff_scheduling_uses_a_single_task_regardless_of_backlog_size(
    session_factory: sessionmaker[Session],
) -> None:
    """P2: a large backlog of not-yet-due retryable FAILED jobs recovered
    at startup must not spawn one sleeping task per entry -- a single
    `_retry_scheduler_task` services a heap of pending retries instead,
    the same way a fixed worker pool (not one task per queued job) bounds
    ordinary processing regardless of backlog size.
    """
    question_ids = [f"q{i}" for i in range(20)]
    version = _seed(session_factory, question_ids=question_ids)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        for i, question_id in enumerate(question_ids):
            uow.jobs.add(
                Job(
                    id=f"job-{i}",
                    kind=JobKind.GRADING,
                    submission_id="sub-1",
                    question_id=question_id,
                    state=JobState.FAILED,
                    attempts=1,
                    max_attempts=3,
                    error_code=ErrorCategory.TIMEOUT,
                    dependency_graph_version=version,
                    created_at=at(),
                    updated_at=at(),  # "just failed" -- essentially the full delay remains
                )
            )
        uow.commit()

    clock = FakeClock(EPOCH)
    settings = QueueSettings(
        max_attempts=3,
        initial_backoff_seconds=1000.0,
        backoff_multiplier=1.0,
        max_backoff_seconds=1000.0,
    )
    processor = FakeJobProcessor()
    service = JobQueueService(session_factory, processor, settings=settings, clock=clock)
    await service.start()
    try:
        # All 20 recovered jobs are not-yet-due (~1000s remains on each) --
        # every one must have landed as heap *data*, not as its own task.
        assert len(service._retry_heap) == 20
        assert service._workers  # the fixed worker pool, unaffected
        assert service._retry_scheduler_task is not None
        assert not service._retry_scheduler_task.done()
    finally:
        await service.shutdown()


# --------------------------------------------------------------------------- #
# Review round 8 regressions
# --------------------------------------------------------------------------- #
async def test_requeue_after_backoff_loses_to_a_concurrent_approval_that_lands_mid_write(
    session_factory: sessionmaker[Session], clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1: _requeue_after_backoff's own read seeing usable=None is not
    enough -- a concurrent mark_question_usable approval can still commit
    usable=True in the window between that read and this write, and a
    state-only compare-and-set would never notice (mark_usable never
    touches state). require_usable_unset=True closes that window the same
    way retry_job/cancel_job's own writes already do (review rounds 5/6):
    the approval landing first makes this save lose instead, leaving the
    approval (and whatever it already released) untouched.
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
                state=JobState.QUEUED,
                dependency_graph_version=version,
                created_at=at(),
                updated_at=at(),
            )
        )
        uow.commit()

    real_save = SqlAlchemyJobRepository.save
    calls = {"count": 0}

    def _save_races_a_concurrent_approval(
        self: SqlAlchemyJobRepository,
        job: Job,
        *,
        expected_state: JobState,
        expected_attempts: int | None = None,
        require_usable_unset: bool = False,
    ) -> None:
        if expected_state is JobState.FAILED and require_usable_unset:
            calls["count"] += 1
            if calls["count"] == 1:
                # Simulate mark_question_usable committing usable=True in
                # the window between this call's own read and its write --
                # independently committed so it survives this call's own
                # uow rolling back on the resulting lost CAS.
                with SqlAlchemyUnitOfWork(session_factory) as inner:
                    assert (
                        inner.jobs.mark_usable(
                            job.id,
                            usable=True,
                            expected_state=JobState.FAILED,
                            expected_attempts=1,
                        )
                        is True
                    )
                    inner.commit()
        real_save(
            self,
            job,
            expected_state=expected_state,
            expected_attempts=expected_attempts,
            require_usable_unset=require_usable_unset,
        )

    monkeypatch.setattr(SqlAlchemyJobRepository, "save", _save_races_a_concurrent_approval)

    service = JobQueueService(session_factory, FakeJobProcessor(), clock=clock)
    service._requeue_after_backoff("job-qa", expected_attempts=1)

    assert calls["count"] == 1  # the CAS lost to the approval; never retried
    job = service.get_job("job-qa")
    assert job is not None
    assert job.state is JobState.FAILED  # untouched
    assert job.usable is True  # the approval, not the requeue, won
    qb = service.get_job("job-qb")
    assert qb is not None
    assert qb.state is JobState.QUEUED  # unaffected, sanity check


async def test_start_recovery_loses_to_a_concurrent_approval_that_lands_mid_write(
    session_factory: sessionmaker[Session], clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1: start()'s retryable-FAILED sweep has the exact same race as
    _requeue_after_backoff -- its own read of a FAILED job with
    usable=None is not enough, since a concurrent mark_question_usable
    approval can still land before this specific write commits (this
    startup transaction may not yet have escalated to a write lock at this
    point, if nothing earlier in the same sweep had to write anything).
    The same require_usable_unset=True guard must apply here too.
    """
    version = _seed(session_factory, question_ids=["qa"])
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
                updated_at=at(),  # backoff has long since fully elapsed
            )
        )
        uow.commit()

    real_save = SqlAlchemyJobRepository.save
    calls = {"count": 0}

    def _save_races_a_concurrent_approval(
        self: SqlAlchemyJobRepository,
        job: Job,
        *,
        expected_state: JobState,
        expected_attempts: int | None = None,
        require_usable_unset: bool = False,
    ) -> None:
        if expected_state is JobState.FAILED and require_usable_unset:
            calls["count"] += 1
            if calls["count"] == 1:
                with SqlAlchemyUnitOfWork(session_factory) as inner:
                    assert (
                        inner.jobs.mark_usable(
                            job.id,
                            usable=True,
                            expected_state=JobState.FAILED,
                            expected_attempts=1,
                        )
                        is True
                    )
                    inner.commit()
        real_save(
            self,
            job,
            expected_state=expected_state,
            expected_attempts=expected_attempts,
            require_usable_unset=require_usable_unset,
        )

    monkeypatch.setattr(SqlAlchemyJobRepository, "save", _save_races_a_concurrent_approval)

    processor = FakeJobProcessor()
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    try:
        await asyncio.sleep(0.05)
    finally:
        await service.shutdown()

    assert calls["count"] == 1
    job = service.get_job("job-qa")
    assert job is not None
    assert job.state is JobState.FAILED  # untouched -- the approval won
    assert job.usable is True
    assert processor.calls == []  # never actually reprocessed


async def test_retry_scheduler_survives_a_requeue_after_backoff_error(
    session_factory: sessionmaker[Session], clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1: an exception from _requeue_after_backoff itself (e.g. a
    transient SQLite busy-timeout) must not kill the single retry
    scheduler task -- nothing else services _retry_heap, so letting it die
    would silently strand every other pending retry until a restart. The
    scheduler must absorb the failure per entry, keep running, and
    reschedule the affected entry instead of losing it outright.

    Both jobs' *entire* attempt history is scripted up front (one FAILED,
    then SUCCEEDED) instead of relying on this test calling
    `processor.set_default(...)` at just the right moment: every delay the
    service awaits here goes through `FakeClock`, which advances virtual
    time instantly rather than actually waiting, so nothing stops both
    jobs from racing through every one of their `max_attempts` attempts
    (all still FAILED/TIMEOUT) before this coroutine ever gets scheduled
    again to flip the processor's default to SUCCEEDED -- on a fast enough
    event loop that race is lost close to every time, permanently
    exhausting both jobs' retries and hanging the test on its final
    `_wait_until` no matter how generous its timeout is (Issue #50: this
    reproduced deterministically on Linux, confirmed by tracing the actual
    attempt counts -- see docs/job-queue.md). Scripting the exact outcome
    of every attempt removes the race entirely: the fate of both jobs is
    fixed before `service.start()` ever runs, independent of how fast or
    slow the host schedules the retry storm.
    """
    _seed(session_factory, test_id="test-a", submission_id="sub-a", question_ids=["qa"])
    _seed(session_factory, test_id="test-b", submission_id="sub-b", question_ids=["qb"])
    processor = FakeJobProcessor(
        default=ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=True)
    )
    failed_once = [
        ProcessingResult(outcome=ProcessingOutcome.FAILED, error_category=ErrorCategory.TIMEOUT)
    ]
    processor.script("sub-a", "qa", failed_once)
    processor.script("sub-b", "qb", failed_once)
    service = JobQueueService(
        session_factory, processor, settings=QueueSettings(max_attempts=5), clock=clock
    )
    await service.start()
    try:
        service.submit_submission(submission_id="sub-a")
        service.submit_submission(submission_id="sub-b")
        job_a = _job_id_for_question(service, "sub-a", "qa")
        job_b = _job_id_for_question(service, "sub-b", "qb")

        real_requeue = JobQueueService._requeue_after_backoff
        calls = {"count": 0}

        def _requeue_raises_once_for_job_a(
            self: JobQueueService, job_id: str, *, expected_attempts: int
        ) -> None:
            if job_id == job_a and calls["count"] == 0:
                calls["count"] += 1
                raise RuntimeError("simulated transient infra error")
            real_requeue(self, job_id, expected_attempts=expected_attempts)

        # Patched before either job has even failed once, so there is no
        # window where the real (unpatched) method could service job_a's
        # entry before this takes effect.
        monkeypatch.setattr(
            JobQueueService, "_requeue_after_backoff", _requeue_raises_once_for_job_a
        )

        # Both jobs must still eventually succeed: job_b's own backoff
        # timer was never affected, and job_a's failed requeue attempt gets
        # rescheduled rather than lost once the scheduler absorbs the error.
        await _wait_until(lambda: _state(service, job_a) is JobState.SUCCEEDED)
        await _wait_until(lambda: _state(service, job_b) is JobState.SUCCEEDED)
        assert calls["count"] == 1
    finally:
        await service.shutdown()


async def test_shutdown_replaces_the_retry_added_event_not_just_clears_it(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P2: `_retry_added` is an `asyncio.Event` that binds to whichever
    loop first awaits it; `clear()` alone does not undo that binding, so a
    later `start()` on an entirely different event loop (the same
    reasoning `_loop`/`_queue` are already reset for -- see `shutdown`'s
    own docstring) would have its `_retry_scheduler_loop` raise "... is
    bound to a different event loop" the moment it tries to idle on this
    same object while the heap is empty. shutdown() must replace it with a
    fresh Event instead of just clearing the existing one.
    """
    _seed(session_factory, question_ids=["qa"])
    processor = FakeJobProcessor()
    processor.script(
        "sub-1",
        "qa",
        [ProcessingResult(outcome=ProcessingOutcome.FAILED, error_category=ErrorCategory.TIMEOUT)],
    )
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    original_event = service._retry_added
    await service.shutdown()
    assert service._retry_added is not original_event  # replaced, not just cleared

    # A later start() on this same instance must still work correctly with
    # the replaced Event: the scheduler idles on it while the heap is
    # empty, a subsequent failure schedules a retry (which sets it), and
    # the scheduler actually wakes up and requeues -- if the replacement
    # were broken, this would simply hang.
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_id = _job_id_for_question(service, "sub-1", "qa")
        await _wait_until(lambda: _state(service, job_id) is JobState.SUCCEEDED)
    finally:
        await service.shutdown()


# --------------------------------------------------------------------------- #
# Review round 9 regressions
# --------------------------------------------------------------------------- #
async def test_retry_job_save_loses_to_a_concurrent_aba_cycle(
    session_factory: sessionmaker[Session], clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1: retry_job reads a FAILED job at attempt N and later writes with
    expected_state=FAILED; state alone cannot rule out a concurrent
    FAILED -> QUEUED -> RUNNING -> FAILED cycle completing before that
    write -- a fresh, unreviewed attempt N+1 with its own new
    error_code/last_error -- which would still match the same state-only
    CAS and silently overwrite the newer attempt's real state with this
    call's stale one instead of losing the race. Passing
    expected_attempts=job.attempts to save() closes that hole the same way
    mark_usable's own expected_attempts already does (review round 6, P1).
    """
    version = _seed(session_factory, question_ids=["qa"])
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.jobs.add(
            Job(
                id="job-qa",
                kind=JobKind.GRADING,
                submission_id="sub-1",
                question_id="qa",
                state=JobState.FAILED,
                attempts=1,
                max_attempts=5,
                error_code=ErrorCategory.TIMEOUT,
                last_error="timed out",
                dependency_graph_version=version,
                created_at=at(),
                updated_at=at(),
            )
        )
        uow.commit()

    real_save = SqlAlchemyJobRepository.save
    calls = {"count": 0}

    def _save_races_a_concurrent_aba_cycle(
        self: SqlAlchemyJobRepository,
        job: Job,
        *,
        expected_state: JobState,
        expected_attempts: int | None = None,
        require_usable_unset: bool = False,
    ) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            # A full cycle back to FAILED, independently committed so it
            # survives this call's own uow rolling back on the resulting
            # lost CAS -- simulating another process/worker completing an
            # entire retry attempt for this same job in the window between
            # retry_job's own read and this write.
            # real_save (the unpatched method, captured before this
            # monkeypatch) is called directly here, not via inner.jobs.save
            # -- the latter would recurse back into this same patched
            # dispatcher (it is patched on the class, not this one
            # instance) and inflate `calls` with these simulated writes
            # too.
            with SqlAlchemyUnitOfWork(session_factory) as inner:
                current = inner.jobs.get("job-qa")
                assert current is not None
                requeued = current.transitioned_to(JobState.QUEUED, updated_at=at(seconds=1))
                real_save(inner.jobs, requeued, expected_state=JobState.FAILED)
                running = requeued.transitioned_to(JobState.RUNNING, updated_at=at(seconds=2))
                real_save(inner.jobs, running, expected_state=JobState.QUEUED)
                failed_again = running.transitioned_to(
                    JobState.FAILED,
                    updated_at=at(seconds=3),
                    error_code=ErrorCategory.SERVER_ERROR,
                    error="a completely different failure",
                )
                real_save(inner.jobs, failed_again, expected_state=JobState.RUNNING)
                inner.commit()
        real_save(
            self,
            job,
            expected_state=expected_state,
            expected_attempts=expected_attempts,
            require_usable_unset=require_usable_unset,
        )

    monkeypatch.setattr(SqlAlchemyJobRepository, "save", _save_races_a_concurrent_aba_cycle)

    service = JobQueueService(session_factory, FakeJobProcessor(), clock=clock)
    retried = service.retry_job("job-qa")

    assert calls["count"] == 2  # the first attempt lost to the ABA cycle and had to be retried
    assert retried.state is JobState.QUEUED
    assert retried.attempts == 2  # requeued against the *current* attempt, not the stale one
    job = service.get_job("job-qa")
    assert job is not None
    assert job.state is JobState.QUEUED
    assert job.attempts == 2


async def test_submit_submission_does_not_re_enqueue_an_existing_queued_job(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """P2: a repeat, idempotent submit_submission call for a submission
    whose job already exists and is still QUEUED must not push its id onto
    the in-memory dispatch queue again -- otherwise a client's repeated
    retries (or just polling) would grow that queue with an ever-larger
    pile of redundant, eventually-no-op signals, delaying unrelated
    submissions' genuinely new work sitting behind them in the same FIFO
    queue.

    The service is deliberately never `start()`-ed: no worker ever exists
    to claim the job, so it stays QUEUED (not RUNNING) for the whole test
    -- exactly the state a repeat call must not re-signal.
    """
    _seed(session_factory, question_ids=["qa"])
    service = JobQueueService(session_factory, FakeJobProcessor(), clock=clock)

    service.submit_submission(submission_id="sub-1")
    assert service._queue.qsize() == 1
    assert [j.state for j in service.list_for_submission("sub-1")] == [JobState.QUEUED]

    # Repeat, idempotent calls for the same submission -- the job already
    # exists (still QUEUED, never claimed) and there is nothing new to
    # create, so nothing should ever be pushed onto the queue again.
    for _ in range(5):
        service.submit_submission(submission_id="sub-1")
    assert service._queue.qsize() == 1


# --------------------------------------------------------------------------- #
# Review round 10 regressions
# --------------------------------------------------------------------------- #
async def test_a_post_claim_failure_recovers_the_stuck_running_job(
    session_factory: sessionmaker[Session], clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1: an unexpected exception *after* _run_one's own claim (QUEUED ->
    RUNNING) has already committed -- e.g. a transient SQLAlchemy
    OperationalError while persisting the outcome -- must not be treated
    the same way a pre-claim failure is (just re-enqueue the job id).
    `_run_one`'s own early-return guard immediately no-ops a non-QUEUED
    row, so a plain re-enqueue signal for a job stuck RUNNING would do
    nothing at all, stranding it until the next process restart's
    recovery sweep. The worker must instead recover it in-process, the
    same way `start()` would on restart: QUEUED again here (a fresh job,
    retries remain), then actually re-processed to completion -- not left
    RUNNING forever.
    """
    _seed(session_factory, question_ids=["qa"])

    real_save = SqlAlchemyJobRepository.save
    calls = {"finalize_attempts": 0}

    def _save_raises_once_on_finalize(
        self: SqlAlchemyJobRepository,
        job: Job,
        *,
        expected_state: JobState,
        expected_attempts: int | None = None,
        require_usable_unset: bool = False,
    ) -> None:
        if expected_state is JobState.RUNNING and calls["finalize_attempts"] == 0:
            calls["finalize_attempts"] += 1
            raise RuntimeError("simulated transient infra error while finalizing")
        real_save(
            self,
            job,
            expected_state=expected_state,
            expected_attempts=expected_attempts,
            require_usable_unset=require_usable_unset,
        )

    monkeypatch.setattr(SqlAlchemyJobRepository, "save", _save_raises_once_on_finalize)

    processor = FakeJobProcessor()
    service = JobQueueService(
        session_factory, processor, settings=QueueSettings(max_concurrency=1), clock=clock
    )
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        job_id = _job_id_for_question(service, "sub-1", "qa")
        # In-process recovery must flip the stuck RUNNING row back to
        # QUEUED and re-enqueue it, letting it go on to actually succeed --
        # not sit stuck RUNNING forever.
        await _wait_until(lambda: _state(service, job_id) is JobState.SUCCEEDED)
        assert calls["finalize_attempts"] == 1  # the injected failure really fired once
        job = service.get_job(job_id)
        assert job is not None
        assert job.attempts == 2  # the recovered attempt, then the one that actually succeeded
    finally:
        await service.shutdown()


async def test_submit_submission_does_not_queue_jobs_for_extra_pages(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """Issue #215: A submission with extra pages relative to registered questions
    (e.g. page_count=3, expected pages=(1, 2)) must NOT have grading jobs queued.
    It must stay in needs_review waiting for human intervention rather than failing
    with 'no answer image recorded'."""
    _seed(
        session_factory,
        question_ids=["qa", "qb"],
        question_pages={"qa": 1, "qb": 2},
        page_count=3,
    )
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.submissions.mark_intake_outcome("sub-1", SubmissionState.AI_PROCESSING, None)
        uow.submissions.mark_intake_outcome("sub-1", SubmissionState.AI_PROCESSED, None)
        uow.submissions.mark_intake_outcome(
            "sub-1", SubmissionState.NEEDS_REVIEW, "extra_pages:3>2"
        )
        uow.commit()

    processor = FakeJobProcessor()
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    try:
        created = service.submit_submission(submission_id="sub-1")
        assert created == []
        assert service.list_for_submission("sub-1") == []
        assert processor.calls == []
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            assert uow.jobs.list_for_submission("sub-1") == []
            sub = uow.submissions.get("sub-1")
            assert sub is not None
            assert sub.state is SubmissionState.NEEDS_REVIEW
            assert sub.review_reason == "extra_pages:3>2"
    finally:
        await service.shutdown()


async def test_submit_submission_does_not_queue_jobs_for_missing_pages(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """Issue #215: A submission with missing pages relative to registered questions
    (e.g. page_count=1, expected pages=(1, 2)) must NOT have grading jobs queued."""
    _seed(
        session_factory,
        question_ids=["qa", "qb"],
        question_pages={"qa": 1, "qb": 2},
        page_count=1,
    )
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.submissions.mark_intake_outcome("sub-1", SubmissionState.AI_PROCESSING, None)
        uow.submissions.mark_intake_outcome("sub-1", SubmissionState.AI_PROCESSED, None)
        uow.submissions.mark_intake_outcome(
            "sub-1", SubmissionState.NEEDS_REVIEW, "missing_pages:2"
        )
        uow.commit()

    processor = FakeJobProcessor()
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    try:
        created = service.submit_submission(submission_id="sub-1")
        assert created == []
        assert service.list_for_submission("sub-1") == []
        assert processor.calls == []
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            assert uow.jobs.list_for_submission("sub-1") == []
            sub = uow.submissions.get("sub-1")
            assert sub is not None
            assert sub.state is SubmissionState.NEEDS_REVIEW
            assert sub.review_reason == "missing_pages:2"
    finally:
        await service.shutdown()


async def test_submit_submission_queues_jobs_normally_when_page_coverage_is_complete(
    session_factory: sessionmaker[Session], clock: Clock
) -> None:
    """Issue #215 (regression prevention): A submission with complete page coverage
    (e.g. page_count=2, expected pages=(1, 2)) queues jobs and processes them normally."""
    _seed(
        session_factory,
        question_ids=["qa", "qb"],
        question_pages={"qa": 1, "qb": 2},
        page_count=2,
    )
    processor = FakeJobProcessor()
    service = JobQueueService(session_factory, processor, clock=clock)
    await service.start()
    try:
        created = service.submit_submission(submission_id="sub-1")
        assert len(created) == 2
        assert len(service.list_for_submission("sub-1")) == 2
        await _wait_until(lambda: len(processor.calls) == 2)
        await _wait_until(
            lambda: all(
                _state(service, j.id) is JobState.SUCCEEDED
                for j in service.list_for_submission("sub-1")
            )
        )
    finally:
        await service.shutdown()
