"""Issue #25 additional acceptance: a multi-page answer's Question DAG really
is executed in dependency order *and* in parallel where the DAG allows it.

Existing coverage stops short of this. `test_job_scheduling.py` proves
`evaluate_readiness` alone; `test_job_queue.py` proves the queue never
*exceeds* the concurrency cap and that a dependent is never handed to the
processor before its prerequisite -- but "never exceeds 2" is equally true of
a queue that ran everything one at a time, and a call-order assertion cannot
tell a genuinely overlapping pair of jobs from two sequential ones. Issue #25
asks for the three properties that distinguish those cases:

* no schedule that ignores the DAG and runs everything at once,
* no schedule that needlessly serializes independent work,
* no schedule that exceeds the external-provider concurrency cap,

decided from when each job actually started and finished
(`tests.fakes.ProcessingSpan`), and holding both within one submission and
across several submitted at the same time.

**Determinism.** Nothing here waits on elapsed real time. Overlap is proved
by `FakeJobProcessor(release_at_concurrency=...)`, a latch that only opens
once that many jobs are genuinely in flight -- so a serializing queue hangs
the latch and fails, rather than quietly satisfying a weaker assertion.
Every job's outcome is scripted before `start()`, which is the correction
Issue #50 (docs/job-queue.md) landed on after a test whose result depended on
how many rounds the workers got through before the test coroutine ran again
failed deterministically on Linux and not at all on Windows.

`max_concurrency=2` throughout is deliberately *not* `QueueSettings`' own
default (4 since Issue #81, business-rules-and-evaluation-data.md section
3 (E)). One submission of this DAG starts with exactly two runnable questions
(q1, q2), and the latch blocks the very jobs whose completion would unblock
q3/q4 -- so at `release_at_concurrency=4` the jobs could never open it
themselves. Nothing hangs: `FakeJobProcessor` gives up on an unopened latch
after `latch_timeout_seconds` and records `latch_timed_out` (tests/fakes.py --
deliberately a failing test rather than a hung one), and `_wait_until` gives
up on its own 5s bound first, so the run fails there. Verified by temporarily
setting this constant to 4: the first test below fails in ~5s. At 2 the latch
is reachable, which is what makes "and still in parallel" a real assertion
rather than one a fully serial queue would also satisfy.

**Saturation at the shipped default of 4 is therefore not covered here.**
These tests prove the queue honours whatever cap it is given and that it
really overlaps work up to 2; they say nothing about four workers in flight.
Covering that needs a scenario with four simultaneously-runnable jobs -- the
two-submission test below is the one that already has them (two roots each),
and it does open a 4-latch -- so it is a separate change, not a constant to
bump here.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.dependency_graph import DependencyEdge, DependencyProvision
from auto_scoring.domain.job_execution import ProcessingOutcome, ProcessingResult
from auto_scoring.domain.models import JobState
from auto_scoring.jobs.queue import JobQueueService
from auto_scoring.jobs.settings import QueueSettings
from tests.fakes import FakeClock, FakeJobProcessor, ProcessingSpan, peak_overlap
from tests.support import EPOCH, make_submission
from tests.support import seed_confirmed_dependency_graph as _seed

#: The concurrency cap under test -- the module docstring explains why it is
#: 2 rather than the configured default of 4 (section 3 (E)).
_MAX_CONCURRENCY = 2

#: A 3-page answer whose questions cover every shape the acceptance names:
#: two independent roots (q1, q2) on page 1, a fan-out from q1 to q3 and q4 on
#: page 2, and a merge of q2/q3/q4 into q5 on page 3.
#:
#:     q1 --> q3 --.
#:       \--> q4 --+--> q5
#:     q2 ---------'
_QUESTION_IDS = ["q1", "q2", "q3", "q4", "q5"]
_QUESTION_PAGES = {"q1": 1, "q2": 1, "q3": 2, "q4": 2, "q5": 3}
_EDGE_PAIRS = [("q1", "q3"), ("q1", "q4"), ("q2", "q5"), ("q3", "q5"), ("q4", "q5")]


def _edge(a: str, b: str) -> DependencyEdge:
    return DependencyEdge(
        from_question_id=a,
        to_question_id=b,
        provides=(DependencyProvision.SCORE,),
        rationale=f"{a}の結果を{b}が使用",
    )


def _seed_three_page_dag(
    session_factory: sessionmaker[Session], *, submission_id: str = "sub-1"
) -> None:
    _seed(
        session_factory,
        submission_id=submission_id,
        question_ids=_QUESTION_IDS,
        question_pages=_QUESTION_PAGES,
        page_count=3,
        edges=[_edge(a, b) for a, b in _EDGE_PAIRS],
    )


def _add_submission(session_factory: sessionmaker[Session], submission_id: str) -> None:
    """A second answer for the *same* test, so both share one confirmed DAG."""
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.submissions.add(
            make_submission(
                id=submission_id,
                page_count=3,
                # The submissions table rejects a duplicate source hash (an
                # identical PDF is the same answer, Issue #17).
                source_pdf_sha256=f"{submission_id:x<64}"[:64],
            )
        )
        uow.commit()


async def _wait_until(
    predicate: Callable[[], bool], *, timeout: float = 5.0, interval: float = 0.01
) -> None:
    """Copied from `test_job_queue.py` deliberately.

    Real time appears in this module only here, as the bound on how long a
    *failing* test takes to give up -- never as the thing an assertion is
    decided by. See the module docstring.
    """
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting for condition")
        await asyncio.sleep(interval)


def _all_terminal(service: JobQueueService, submission_id: str) -> bool:
    return all(
        job.state is JobState.SUCCEEDED for job in service.list_for_submission(submission_id)
    )


def _assert_dependency_order(processor: FakeJobProcessor, submission_id: str) -> None:
    """Every confirmed edge's prerequisite finished before its dependent started.

    This is what rules out the "ignored the DAG and ran everything in
    parallel" schedule: under that schedule a dependent's start would sit
    inside -- or before -- its prerequisite's span.
    """
    for prerequisite, dependent in _EDGE_PAIRS:
        before = processor.span_for(submission_id, prerequisite)
        after = processor.span_for(submission_id, dependent)
        assert before.finished < after.started, (
            f"{submission_id}: {dependent} started at {after.started} but its prerequisite "
            f"{prerequisite} only finished at {before.finished}"
        )


def _spans_for(processor: FakeJobProcessor, submission_id: str) -> list[ProcessingSpan]:
    return [span for span in processor.spans if span.submission_id == submission_id]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(EPOCH)


@pytest.fixture
def settings() -> QueueSettings:
    return QueueSettings(max_concurrency=_MAX_CONCURRENCY)


async def test_a_three_page_dag_runs_in_dependency_order_and_still_in_parallel(
    session_factory: sessionmaker[Session], clock: FakeClock, settings: QueueSettings
) -> None:
    """The whole additional-acceptance list, on one submission.

    The latch (`release_at_concurrency=2`) is what makes "and still in
    parallel" a real assertion: q1 and q2 are the only two questions runnable
    at the start, so the run can only get past the latch at all if the queue
    really ran them at the same time.
    """
    _seed_three_page_dag(session_factory)
    processor = FakeJobProcessor(release_at_concurrency=_MAX_CONCURRENCY)
    service = JobQueueService(session_factory, processor, settings=settings, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        await _wait_until(lambda: _all_terminal(service, "sub-1"))
    finally:
        await service.shutdown()

    assert {span.question_id for span in processor.spans} == set(_QUESTION_IDS)
    _assert_dependency_order(processor, "sub-1")

    # Not needlessly serial: the two independent roots really overlapped.
    q1, q2 = processor.span_for("sub-1", "q1"), processor.span_for("sub-1", "q2")
    assert q1.overlaps(q2), f"independent roots did not run concurrently: {q1}, {q2}"

    # Not over the external-provider cap, measured from the spans themselves.
    assert peak_overlap(processor.spans) <= _MAX_CONCURRENCY
    assert processor.max_concurrency_seen <= _MAX_CONCURRENCY


async def test_a_low_confidence_prerequisite_blocks_only_its_own_downstream(
    session_factory: sessionmaker[Session], clock: FakeClock, settings: QueueSettings
) -> None:
    """q1 succeeds but is not usable (business-rules-and-evaluation-data.md
    section 4.4's low-Confidence case, decided by the processor at whatever
    threshold section 3 (C) is currently configured with -- scripted here so
    the test does not depend on that operationally-tuned value).

    Its dependents q3/q4 -- and q5 behind them -- must stay BLOCKED and must
    never be handed to the provider at all. q2, which does not depend on q1,
    must still run: a stalled prerequisite blocks its own subtree, not the
    queue.
    """
    _seed_three_page_dag(session_factory)
    processor = FakeJobProcessor()
    processor.script(
        "sub-1", "q1", [ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=False)]
    )
    service = JobQueueService(session_factory, processor, settings=settings, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        await _wait_until(lambda: {span.question_id for span in processor.spans} == {"q1", "q2"})
        # Nothing further can become runnable: q3/q4 wait on q1, q5 waits on
        # q3/q4. Any additional span would be the bug this test exists for,
        # so give the workers a few scheduler turns to produce one.
        for _ in range(10):
            await asyncio.sleep(0)
    finally:
        await service.shutdown()

    assert {span.question_id for span in processor.spans} == {"q1", "q2"}
    states = {job.question_id: job.state for job in service.list_for_submission("sub-1")}
    assert states["q3"] is JobState.BLOCKED
    assert states["q4"] is JobState.BLOCKED
    assert states["q5"] is JobState.BLOCKED
    assert states["q2"] is JobState.SUCCEEDED


async def test_approving_the_blocked_prerequisite_resumes_the_rest_of_the_dag(
    session_factory: sessionmaker[Session], clock: FakeClock, settings: QueueSettings
) -> None:
    """The human-correction resume path (section 4.4 "再開条件"): once the
    reviewer marks the stalled prerequisite usable, the subtree behind it
    runs -- still in dependency order, not all at once.
    """
    _seed_three_page_dag(session_factory)
    processor = FakeJobProcessor()
    processor.script(
        "sub-1", "q1", [ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=False)]
    )
    service = JobQueueService(session_factory, processor, settings=settings, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        await _wait_until(lambda: {span.question_id for span in processor.spans} == {"q1", "q2"})

        service.mark_question_usable(submission_id="sub-1", question_id="q1")

        await _wait_until(lambda: _all_terminal(service, "sub-1"))
    finally:
        await service.shutdown()

    assert {span.question_id for span in processor.spans} == set(_QUESTION_IDS)
    _assert_dependency_order(processor, "sub-1")
    assert peak_overlap(processor.spans) <= _MAX_CONCURRENCY


async def test_two_submissions_submitted_at_once_keep_both_guarantees(
    session_factory: sessionmaker[Session], clock: FakeClock, settings: QueueSettings
) -> None:
    """Both answers of the same test are submitted before either finishes.

    Each one's own dependency order must hold, and the one process-wide
    semaphore must still bound the two of them together -- the queue holds a
    single `asyncio.Semaphore` for exactly this (docs/job-queue.md "並列度の
    共有"), so the cap is over all 10 jobs, not per submission.
    """
    _seed_three_page_dag(session_factory)
    _add_submission(session_factory, "sub-2")
    processor = FakeJobProcessor(release_at_concurrency=_MAX_CONCURRENCY)
    service = JobQueueService(session_factory, processor, settings=settings, clock=clock)
    await service.start()
    try:
        service.submit_submission(submission_id="sub-1")
        service.submit_submission(submission_id="sub-2")
        await _wait_until(
            lambda: _all_terminal(service, "sub-1") and _all_terminal(service, "sub-2")
        )
    finally:
        await service.shutdown()

    for submission_id in ("sub-1", "sub-2"):
        assert {span.question_id for span in _spans_for(processor, submission_id)} == set(
            _QUESTION_IDS
        )
        _assert_dependency_order(processor, submission_id)

    # The cap is global: measured over every span from both submissions.
    assert peak_overlap(processor.spans) == _MAX_CONCURRENCY
