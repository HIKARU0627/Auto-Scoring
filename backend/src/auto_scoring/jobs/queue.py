"""The asyncio job queue engine (Issue #18).

A fixed pool of ``max_concurrency`` long-lived worker coroutines consumes an
``asyncio.Queue`` of job ids, as decided in docs/technology-stack.md §3.4.
One `JobQueueService` instance lives for the lifetime of the FastAPI app
(`auto_scoring.api.app.create_app`) and is shared by every submission/
question -- the fixed worker count is what keeps "different submissions run
in parallel" and "one submission's DAG runs in parallel where the graph
allows" under the same concurrency cap (Issue #18 acceptance), and, unlike a
semaphore shared by an unbounded number of per-job tasks, it also bounds how
many tasks this service ever has alive at once regardless of how large a
recovered/submitted backlog is (review round 2, P2). Pending retry backoffs
are likewise a single scheduler task servicing a heap, not one sleeping task
per pending retry -- a large backlog of not-yet-due FAILED jobs recovered at
startup, or a fast, sustained run of failures, must not grow the task count
past that fixed total either (review round 7, P2).

Every operation opens its own short-lived `SqlAlchemyUnitOfWork`; nothing here
ever holds a transaction open across an ``await`` into
`auto_scoring.domain.job_execution.JobProcessor.process` (that call may be a
slow network round trip in a real, future implementation).

Thread-safety: FastAPI runs a synchronous ``def`` route handler in a worker
thread, not on the event loop that owns this service's ``asyncio.Queue``/
``asyncio.Task`` objects (`auto_scoring.api.jobs_router`'s handlers are
exactly that). Every place a route handler can reach an asyncio primitive --
`enqueue` and cancelling a `RUNNING` job's task -- goes through
``loop.call_soon_threadsafe`` instead of calling it directly, since
``asyncio.Queue.put_nowait``/``Task.cancel`` are not themselves safe to call
from a different thread (review round 1, P1). Cancellation specifically
schedules the *entire* lookup-and-cancel operation onto the loop (not just
the final ``.cancel()`` call), so a worker thread never reads `_running`
directly while the loop thread is concurrently mutating it (review round 2,
P2).
"""

from __future__ import annotations

import asyncio
import heapq
import logging
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta
from typing import cast
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.dependency_graph import DependencyGraph, can_start_submission_processing
from auto_scoring.domain.job_execution import JobProcessor, ProcessingOutcome, ProcessingResult
from auto_scoring.domain.job_scheduling import (
    direct_dependents,
    evaluate_readiness,
    plan_submission_jobs,
    question_statuses,
    recover_running_job,
)
from auto_scoring.domain.models import ErrorCategory, Job, JobKind, JobSaveConflict, JobState
from auto_scoring.domain.retry_policy import RetryPolicy, is_retryable
from auto_scoring.jobs.clock import Clock, SystemClock
from auto_scoring.jobs.settings import QueueSettings

logger = logging.getLogger(__name__)

_STOP = object()  # sentinel pushed to the queue, one per worker, to stop it

#: Bound on retries when two concurrent `submit_submission` calls race to
#: create a job for the same (submission, question, graph version) -- see
#: `submit_submission`.
_MAX_SUBMIT_ATTEMPTS = 5

#: Bound on retries when `cancel_job`'s compare-and-set loses a race against
#: a worker or a backoff-driven requeue changing the same row -- see
#: `cancel_job`.
_MAX_CANCEL_ATTEMPTS = 5

#: Bound on retries when `retry_job`'s compare-and-set loses a race against
#: another `retry_job` call or a backoff-driven requeue -- see `retry_job`.
_MAX_RETRY_ATTEMPTS = 5

#: Bound on retries when `mark_question_usable`'s compare-and-set loses a
#: race against a concurrent `retry_job`/worker changing the target job's
#: state -- see `mark_question_usable`.
_MAX_RESUME_ATTEMPTS = 5

#: Delay before `_retry_scheduler_loop` re-schedules an entry whose own
#: `_requeue_after_backoff` call raised (e.g. a transient SQLite busy-
#: timeout) -- always > 0 so the loop's next attempt goes through the
#: sleep-then-requeue branch (a real ``await``) instead of looping back to
#: `_requeue_after_backoff` with no yield point at all, which an
#: immediately-recurring error would turn into an event-loop-starving spin
#: (review round 8, P1).
_SCHEDULER_ERROR_RETRY_DELAY_SECONDS = 1.0


class SubmissionNotReadyError(Exception):
    """The submission's test has no confirmed, up-to-date dependency graph."""


class SubmissionJobCreationConflictError(Exception):
    """Concurrent `submit_submission` calls kept losing the idempotency race."""


class JobNotFoundError(Exception):
    def __init__(self, reference: str) -> None:
        super().__init__(f"job {reference!r} not found")
        self.reference = reference


class JobNotCancellableError(Exception):
    def __init__(self, job_id: str, state: JobState) -> None:
        super().__init__(f"job {job_id!r} is {state!s} and cannot be cancelled")
        self.job_id = job_id
        self.state = state


class JobCancelConflictError(Exception):
    """`cancel_job` kept losing the compare-and-set race against another writer."""

    def __init__(self, job_id: str) -> None:
        super().__init__(
            f"job {job_id!r} could not be cancelled -- its state kept changing "
            "concurrently; please re-fetch and retry"
        )
        self.job_id = job_id


class JobCancelRejectedError(Exception):
    """`cancel_job` refused a FAILED job whose downstream effect a human
    already approved via `mark_question_usable` -- see `cancel_job`."""

    def __init__(self, job_id: str) -> None:
        super().__init__(
            f"job {job_id!r} has already been approved via /resume; cancelling it would clear "
            "that approval while its already-released dependents keep running against an "
            "outcome that no longer has any record -- cancel the dependents first if this "
            "attempt really needs to be invalidated"
        )
        self.job_id = job_id


class JobNotRetryableError(Exception):
    def __init__(self, job_id: str, state: JobState) -> None:
        super().__init__(f"job {job_id!r} is {state!s}; only a FAILED job can be retried")
        self.job_id = job_id
        self.state = state


class JobRetryConflictError(Exception):
    """`retry_job` kept losing the compare-and-set race against another writer."""

    def __init__(self, job_id: str) -> None:
        super().__init__(
            f"job {job_id!r} could not be retried -- its state kept changing concurrently; "
            "please re-fetch and retry"
        )
        self.job_id = job_id


class JobRetryRejectedError(Exception):
    """`retry_job` refused a FAILED job whose downstream effect a human
    already approved via `mark_question_usable` -- see `retry_job`."""

    def __init__(self, job_id: str) -> None:
        super().__init__(
            f"job {job_id!r} has already been approved via /resume; retrying it would clear "
            "that approval while its already-released dependents keep running against an "
            "outcome that is about to change -- cancel the dependents first if this attempt "
            "really needs to be redone"
        )
        self.job_id = job_id


class JobResumeConflictError(Exception):
    """`mark_question_usable` kept losing the compare-and-set race against another writer."""

    def __init__(self, submission_id: str, question_id: str) -> None:
        super().__init__(
            f"could not mark {submission_id!r}:{question_id!r} usable -- its job kept "
            "changing state concurrently (e.g. a retry); please re-fetch and retry"
        )
        self.submission_id = submission_id
        self.question_id = question_id


class JobQueueService:
    """Owns the in-memory queue and worker pool and drives every Job through it."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        processor: JobProcessor,
        *,
        settings: QueueSettings | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._processor = processor
        self._settings = settings or QueueSettings()
        self._clock = clock or SystemClock()
        self._queue: asyncio.Queue[object] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        #: job_id -> the single worker task currently processing it. Only
        #: the worker whose compare-and-set (QUEUED -> RUNNING) actually
        #: wins ever registers here (in `_run_one`, after the CAS
        #: succeeds) -- so unlike a naive "register on dispatch" scheme, a
        #: duplicate dispatch signal for the same id (start()'s recovered-
        #: then-swept lists, or two idempotent `submit_submission` calls)
        #: can never overwrite tracking for a real, still-running worker,
        #: because the loser's CAS fails and it never registers anything
        #: (review round 1, P2).
        self._running: dict[str, asyncio.Task[None]] = {}
        #: Min-heap of ``(due_at, seq, job_id, expected_attempts)`` for every
        #: retryable FAILED job currently sleeping out its backoff, serviced
        #: by the single `_retry_scheduler_task` rather than one task per
        #: pending retry -- decoupled from the worker pool so a job sleeping
        #: out its backoff does not occupy a worker slot another, independent
        #: submission's job could use (review round 1, P2), but *without*
        #: growing this service's task count with backlog size or failure
        #: rate the way one task per pending retry used to (review round 7,
        #: P2; a large not-yet-due-FAILED-job backlog recovered at startup,
        #: or a fast, sustained run of failures, could otherwise spawn
        #: unboundedly many sleeping tasks -- exactly what the fixed worker
        #: pool above was designed to avoid in the first place). ``seq`` is a
        #: tie-breaker so two equal ``due_at`` values never fall back to
        #: comparing ``job_id`` strings against each other pointlessly.
        self._retry_heap: list[tuple[datetime, int, str, int]] = []
        self._retry_heap_seq = 0
        #: Set whenever `_schedule_retry` pushes onto `_retry_heap` while
        #: `_retry_scheduler_loop` is idling on an empty heap, so it wakes up
        #: to notice the new entry instead of waiting forever.
        self._retry_added = asyncio.Event()
        self._retry_scheduler_task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        #: Set for the duration of `shutdown`. Checked by `_worker_loop`
        #: right after dequeuing so a worker stops after its *current* job
        #: instead of draining whatever backlog is still queued behind the
        #: `_STOP` sentinels `shutdown` pushes -- those sentinels sit at the
        #: back of the FIFO queue, so without this flag a large persisted
        #: backlog would delay shutdown by however long it took to process
        #: all of it first (review round 3, P2). A job abandoned this way is
        #: simply left QUEUED in the DB; `start`'s sweep re-enqueues it next
        #: time regardless.
        self._closing = False

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        """Recover from a killed process, then start the worker pool (Issue
        #18 acceptance: "強制終了後の再起動でjobが失われず…").

        The in-memory queue is empty on a fresh process no matter how the
        previous one ended, so every still-``QUEUED`` job (never picked up
        yet) needs re-enqueuing here, not just the ones ``RUNNING`` when the
        process died -- and so does every ``FAILED`` job that still had
        retry attempts left: if the process was killed while a job was
        sleeping out its backoff (`_retry_heap`), that in-process timer died
        with it, and nothing else would ever wake the job up again (review
        round 2, P1). A restart during a *long* backoff (a large rate-limit
        delay, say) must not skip the rest of it, though -- the remaining
        wait is derived from ``updated_at`` (bumped exactly when the FAILED
        transition was persisted) and a fresh `_retry_heap` entry picks up
        only what is left, same as an in-process backoff would have (review
        round 5, P2). However large this backlog of not-yet-due FAILED jobs
        is, scheduling all of it only ever grows `_retry_heap`'s data, never
        the single `_retry_scheduler_task` that services it (review round 7,
        P2).
        """
        self._loop = asyncio.get_running_loop()
        to_enqueue: list[str] = []
        to_schedule_backoff: list[tuple[str, float, int]] = []
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            for job in uow.jobs.list_by_state(JobState.RUNNING):
                recovered = recover_running_job(job, at=self._clock.now())
                try:
                    uow.jobs.save(recovered, expected_state=JobState.RUNNING)
                except JobSaveConflict:
                    continue
                logger.info(
                    "job recovered at startup",
                    extra={"job_id": recovered.id, "state": recovered.state.value},
                )
                if recovered.state is JobState.QUEUED:
                    to_enqueue.append(recovered.id)

            for job in uow.jobs.list_by_state(JobState.FAILED):
                if (
                    job.error_code is None
                    or not is_retryable(job.error_code)
                    or job.attempts >= job.max_attempts
                    # A human already approved this failure's downstream
                    # effect via `mark_question_usable` (Issue #18 §4.4) --
                    # requeuing it for an automatic retry would silently
                    # discard that approval the next time this job
                    # finalizes (`transitioned_to` always resets `usable`
                    # on a fresh transition), even though dependents may
                    # already have been released on the strength of it
                    # (review round 3, P1).
                    or job.usable is not None
                ):
                    continue
                retry_policy = self._retry_policy_for(job)
                full_delay = retry_policy.delay_seconds(job.attempts)
                elapsed = (self._clock.now() - job.updated_at).total_seconds()
                remaining = max(0.0, full_delay - elapsed)
                if remaining > 0:
                    # Requeuing immediately would let a quick restart during
                    # a long backoff (e.g. a 429's rate-limit delay) hit the
                    # provider again right away, defeating the exponential
                    # delay this job was already sleeping out. Leave the row
                    # FAILED for now; a timer for only what's left is
                    # scheduled below, once this transaction has committed.
                    to_schedule_backoff.append((job.id, remaining, job.attempts))
                    continue
                requeued = job.transitioned_to(JobState.QUEUED, updated_at=self._clock.now())
                try:
                    # require_usable_unset=True: a concurrent `/resume` call
                    # (its own short transaction) can still commit `usable`
                    # between the read above and this write, before this
                    # startup transaction's own writes escalate its lock --
                    # see `_requeue_after_backoff`'s identical guard (review
                    # round 8, P1). expected_attempts=job.attempts closes
                    # the ABA hole `state` alone cannot: another process (or
                    # this one, elsewhere) could complete a whole
                    # FAILED -> QUEUED -> RUNNING -> FAILED cycle for this
                    # same job in that same window, and a state-only CAS
                    # would still match a newer, unrelated attempt (review
                    # round 9, P1).
                    uow.jobs.save(
                        requeued,
                        expected_state=JobState.FAILED,
                        expected_attempts=job.attempts,
                        require_usable_unset=True,
                    )
                except JobSaveConflict:
                    continue
                logger.info(
                    "retryable failed job recovered at startup",
                    extra={"job_id": requeued.id, "state": requeued.state.value},
                )
                to_enqueue.append(requeued.id)

            to_enqueue.extend(job.id for job in uow.jobs.list_by_state(JobState.QUEUED))
            uow.commit()

        self._workers = [
            asyncio.create_task(self._worker_loop()) for _ in range(self._settings.max_concurrency)
        ]
        self._retry_scheduler_task = asyncio.create_task(self._retry_scheduler_loop())
        for job_id in to_enqueue:
            self.enqueue(job_id)
        for job_id, remaining, attempts in to_schedule_backoff:
            self._schedule_retry(job_id, remaining, expected_attempts=attempts)

    async def shutdown(self) -> None:
        """Stop the worker pool and wait for in-flight jobs to reach a
        resting state. Does not cancel a RUNNING job's processing -- a
        graceful shutdown lets it finish; only an actual process kill
        leaves a job RUNNING for `start` to recover next time.

        The retry scheduler task is cancelled rather than awaited to actual
        completion of whatever it was sleeping out: every job still sitting
        in `_retry_heap` is already durably persisted as FAILED with its
        real ``attempts``/``error_code``, so `start`'s retryable-FAILED
        sweep recovers each of them next time regardless of whether this
        process exited gracefully or was killed -- waiting out the full
        backoff here first would only make routine shutdowns slower for no
        benefit. `_retry_heap` is cleared for the same reason `_queue` is
        replaced below: harmless either way (`_requeue_after_backoff`'s own
        state/attempts check makes a stale entry a no-op), but leaving it
        populated across a later `start()` on this same instance serves no
        purpose either.

        Sets `_closing` before pushing the `_STOP` sentinels: those sit at
        the *back* of the FIFO queue, so if a large backlog of already-
        QUEUED job ids is still sitting ahead of them, a worker would
        otherwise keep dequeuing and processing real jobs (including a
        possibly slow provider call each) until it finally reaches its own
        sentinel -- delaying shutdown by however long draining the whole
        backlog takes. `_closing` lets a worker stop as soon as it dequeues
        *anything* once shutdown has begun, abandoning the rest of the
        backlog in the DB as still-QUEUED for `start`'s next sweep to pick
        up (review round 3, P2).

        Leaves this instance ready for a later `start()` call (the same
        service, or a second FastAPI app lifespan reusing it): any job ids
        abandoned above, plus every worker's now-unconsumed `_STOP`
        sentinel, are still sitting in `_queue` once the workers exit, so it
        is replaced with a fresh, empty one rather than reused -- otherwise
        the next `start()`'s workers would immediately dequeue a stale
        `_STOP` (or reprocess an abandoned id out from under that start's
        own DB-driven sweep) and exit before doing any work. `_loop` is
        cleared too, since the next `start()` may run on an entirely
        different event loop (review round 4, P2). Neither loses anything:
        every job id this drops is still durably QUEUED in the DB, and
        `start`'s own sweep re-enqueues it regardless.
        """
        if not self._workers:
            return
        self._closing = True
        for _ in self._workers:
            self._queue.put_nowait(_STOP)
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        self._closing = False
        self._queue = asyncio.Queue()
        self._loop = None
        if self._retry_scheduler_task is not None:
            self._retry_scheduler_task.cancel()
            await asyncio.gather(self._retry_scheduler_task, return_exceptions=True)
            self._retry_scheduler_task = None
        self._retry_heap = []
        # Replaced, not just `.clear()`-ed: an `asyncio.Event` binds to
        # whichever loop is running the first time something awaits it, and
        # `clear()` does not undo that binding. A later `start()` may run on
        # an entirely different event loop (same reasoning as `_loop`
        # above), and the next `_retry_scheduler_loop` awaiting this same
        # Event object while the heap is empty would otherwise raise
        # "... is bound to a different event loop" (review round 8, P2).
        self._retry_added = asyncio.Event()

    async def _worker_loop(self) -> None:
        while True:
            item = await self._queue.get()
            if item is _STOP or self._closing:
                return
            job_id = cast(str, item)
            try:
                await self._run_one(job_id)
            except Exception:
                # _run_one already absorbs a processor bug and a lost
                # compare-and-set (JobSaveConflict); this is the backstop
                # for anything else it doesn't specifically expect -- most
                # plausibly a transient SQLAlchemy OperationalError (e.g. a
                # SQLite busy-timeout) while claiming or finalizing this job.
                # Nothing else in the pool ever replaces a dead worker task,
                # so letting this propagate out of the loop would shrink the
                # pool by one permanently; at max_concurrency=1 that stops
                # every future job until the next process restart (review
                # round 7, P1). Log and move on to the next queued item
                # instead of dying.
                logger.exception(
                    "worker failed to process a job; continuing",
                    extra={"job_id": job_id},
                )
                # This worker already dequeued job_id -- that in-memory
                # dispatch signal is gone regardless of whether the failure
                # happened before or after _run_one's own claim (QUEUED ->
                # RUNNING) CAS committed. If it was *before* the row is
                # still QUEUED with nothing left to ever re-signal it short
                # of a full process restart's `start()` sweep (review round
                # 8, P1). Restoring the signal unconditionally costs nothing
                # if the claim actually did succeed before the failure --
                # the next `_run_one(job_id)` simply finds it no longer
                # QUEUED and no-ops immediately.
                self.enqueue(job_id)

    def enqueue(self, job_id: str) -> None:
        """Push an already-QUEUED job's id onto the in-memory queue.

        Public so callers outside this module that create a QUEUED job
        directly (e.g. Issue #26's dependency-graph confirm reissue path)
        can hand it to this same worker pool instead of waiting for the next
        process restart's `start()` sweep to pick it up.

        Safe to call from any thread: goes through
        ``loop.call_soon_threadsafe`` since ``asyncio.Queue.put_nowait`` is
        not itself safe to call from a thread other than the one running the
        loop (review round 1, P1) -- FastAPI runs a synchronous route
        handler (`auto_scoring.api.jobs_router`) in a worker thread, not on
        this service's event loop.
        """
        if self._loop is None:
            # Not started yet (or already shut down) -- nothing is consuming
            # the queue anyway; queue directly so a caller that starts the
            # service afterwards still sees it via `start`'s QUEUED sweep.
            self._queue.put_nowait(job_id)
            return
        self._loop.call_soon_threadsafe(self._queue.put_nowait, job_id)

    # ------------------------------------------------------------------ #
    # Submission-DAG job creation
    # ------------------------------------------------------------------ #
    def submit_submission(self, *, submission_id: str) -> list[Job]:
        """Create one `Job` (kind GRADING) per question in the submission's
        test's active confirmed dependency graph, queueing every question
        with no prerequisite and leaving the rest BLOCKED (Issue #18
        additional requirement: Submission内DAGスケジューリング).

        Idempotent: if jobs already exist for this submission under the
        active graph version, this creates nothing new and only re-enqueues
        whichever of them are still QUEUED (see
        ``uq_jobs_submission_question_graph_version``). Two concurrent calls
        for the same submission can both observe "no existing job" for the
        same question and both try to insert one; the loser's `add()` raises
        `IntegrityError` on that same unique constraint (review round 1,
        P2), so the whole attempt is retried from a fresh read rather than
        surfacing a raw 500.
        """
        for _attempt in range(_MAX_SUBMIT_ATTEMPTS):
            try:
                created, newly_queued = self._plan_and_create_jobs(submission_id)
            except IntegrityError:
                continue
            for job_id in newly_queued:
                self.enqueue(job_id)
            return created
        raise SubmissionJobCreationConflictError(
            f"could not create jobs for submission {submission_id!r} after several concurrent "
            "attempts; please retry"
        )

    def _plan_and_create_jobs(self, submission_id: str) -> tuple[list[Job], list[str]]:
        newly_queued: list[str] = []
        created: list[Job] = []
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            submission = uow.submissions.get(submission_id)
            if submission is None:
                raise JobNotFoundError(submission_id)
            test_id = submission.test_id
            questions = uow.questions.list_for_test(test_id)
            graph = uow.dependency_graphs.get_latest_confirmed(test_id)
            if not can_start_submission_processing(
                graph,
                current_question_ids=[q.id for q in questions],
                active_confirmed_version=graph.version if graph is not None else None,
            ):
                raise SubmissionNotReadyError(
                    f"test {test_id!r} has no confirmed, up-to-date dependency graph"
                )
            assert graph is not None  # can_start_submission_processing already checked this

            existing = {
                job.question_id: job
                for job in uow.jobs.list_for_submission(submission_id)
                if job.dependency_graph_version == graph.version
            }
            now = self._clock.now()
            for plan in plan_submission_jobs(graph):
                existing_job = existing.get(plan.question_id)
                if existing_job is not None:
                    if existing_job.state is JobState.QUEUED:
                        newly_queued.append(existing_job.id)
                    continue
                job = Job(
                    id=str(uuid4()),
                    kind=JobKind.GRADING,
                    submission_id=submission_id,
                    question_id=plan.question_id,
                    created_at=now,
                    updated_at=now,
                    state=JobState.QUEUED if plan.ready else JobState.BLOCKED,
                    max_attempts=self._settings.max_attempts,
                    blocked_on_question_id=(None if plan.ready else plan.blocking_question_id),
                    dependency_graph_version=graph.version,
                )
                uow.jobs.add(job)  # flushes immediately; may raise IntegrityError
                created.append(job)
                if plan.ready:
                    newly_queued.append(job.id)
            uow.commit()
        return created, newly_queued

    # ------------------------------------------------------------------ #
    # Human-triggered resume (Issue #18 §4.4)
    # ------------------------------------------------------------------ #
    def mark_question_usable(self, *, submission_id: str, question_id: str) -> None:
        """Flip the submission's terminal (last known) job for
        ``question_id`` to usable and release any dependent whose other
        prerequisites are also usable now (business-rules-and-evaluation-
        data.md §4.4 resume condition: "人間が…前提を承認して続行…選んだ時点
        で、依存先を自動でキュー再投入する"). A future review API calls this
        once a human approves or corrects a low-confidence/failed result.

        Resolves the submission's test's *currently active* confirmed graph
        version first. The target job is, in order of preference:

        1. A SUCCEEDED or FAILED job for ``question_id`` at the active
           version -- the normal case.
        2. If none exists at the active version at all: the most recent
           SUCCEEDED or FAILED job for ``question_id`` at *any* version.
           `dependency_graph_router.confirm` only reissues jobs that were
           still *incomplete* when the graph advanced (Issue #26); a
           question whose last job had already reached a terminal state
           under an older version is never reissued, so the active version
           can have no row for it at all even though it is very much still
           part of the active graph. Without this fallback, resuming such a
           question would 404 forever and its dependents would stay BLOCKED
           permanently (review round 2, P1).

        The fallback only fires when the active version has *no row at all*
        for ``question_id`` -- if it has one that simply isn't terminal yet
        (QUEUED/RUNNING/BLOCKED, e.g. a concurrent `retry_job` just
        requeued it, or `confirm` just created a fresh replacement), this
        raises `JobResumeConflictError` instead of silently falling back to
        a stale terminal job from an older version. Approving that stale
        job while the real, active attempt is still pending would let a
        dependent proceed on a prerequisite result nobody has actually
        confirmed yet (review round 4, P2).

        Both SUCCEEDED and FAILED are eligible (review round 2, P1): a human
        may approve a low-confidence *success* or correct a *failure*'s
        downstream effect -- `list_for_submission` returning jobs oldest-
        first is also why this only ever considers the active version (or,
        for the fallback, the most recently updated row): picking any
        SUCCEEDED/FAILED match regardless of recency could revive a stale,
        superseded result instead of the real last one (review round 1, P2).

        The actual write is a compare-and-set on the *exact* state (and, to
        rule out an ABA cycle -- see below -- ``attempts``) read here
        (`JobRepository.mark_usable`'s ``expected_state``/
        ``expected_attempts``), retried (bounded) from a fresh read if it
        loses a race -- e.g. against a concurrent `retry_job` moving the
        same row FAILED -> QUEUED. Without this, both writes could commit
        (this call's `mark_usable`, keyed only on "SUCCEEDED or FAILED",
        and the racing `save`, keyed only on `state`) with this call going
        on to release dependents on the strength of a prerequisite that, in
        reality, is already being reprocessed and may yet fail differently
        (review round 3, P1; AGENTS.md "invariants は…実制約で" applies to
        the whole read-decide-write transaction here, not just the
        column). Raises `JobResumeConflictError` if the race keeps losing.

        ``expected_attempts`` matters because FAILED is not a dead end: a
        concurrent retry can complete a full FAILED -> QUEUED -> RUNNING ->
        FAILED cycle in the window between this call's read and its write,
        landing back on the *same* state this call is keyed on but for a
        completely different, unreviewed attempt. `state` alone cannot
        tell that apart; `attempts`, which only ever changes on a
        transition through RUNNING, can (review round 6, P1).
        """
        for _attempt in range(_MAX_RESUME_ATTEMPTS):
            newly_queued = self._try_mark_question_usable(
                submission_id=submission_id, question_id=question_id
            )
            if newly_queued is None:
                continue
            for job_id in newly_queued:
                self.enqueue(job_id)
            return
        raise JobResumeConflictError(submission_id, question_id)

    def _try_mark_question_usable(
        self, *, submission_id: str, question_id: str
    ) -> list[str] | None:
        """One attempt. Returns the newly-queued dependent job ids on
        success, or ``None`` if the compare-and-set lost a race and the
        caller should retry from a fresh read."""
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            submission = uow.submissions.get(submission_id)
            if submission is None:
                raise JobNotFoundError(submission_id)
            graph = uow.dependency_graphs.get_latest_confirmed(submission.test_id)
            if graph is None:
                raise JobNotFoundError(f"{submission_id}:{question_id}")

            jobs = uow.jobs.list_for_submission(submission_id)
            terminal_states = (JobState.SUCCEEDED, JobState.FAILED)
            active_version_jobs = [
                j
                for j in jobs
                if j.question_id == question_id and j.dependency_graph_version == graph.version
            ]
            at_active_version = [j for j in active_version_jobs if j.state in terminal_states]
            if active_version_jobs and not at_active_version:
                # The active version does have a row for this question --
                # it just isn't terminal yet, so falling back to an older
                # version's stale terminal job would approve a superseded
                # result while the real, active attempt is still pending.
                raise JobResumeConflictError(submission_id, question_id)
            candidates = at_active_version or [
                j for j in jobs if j.question_id == question_id and j.state in terminal_states
            ]
            target = max(candidates, key=lambda j: j.updated_at, default=None)
            if target is None:
                raise JobNotFoundError(f"{submission_id}:{question_id}")

            if not uow.jobs.mark_usable(
                target.id,
                usable=True,
                expected_state=target.state,
                expected_attempts=target.attempts,
            ):
                return None

            jobs = [replace(target, usable=True) if j.id == target.id else j for j in jobs]
            newly_queued = self._release_ready_dependents(
                uow, graph=graph, jobs=jobs, completed_question_id=question_id
            )
            uow.commit()
        return newly_queued

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def get_job(self, job_id: str) -> Job | None:
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            return uow.jobs.get(job_id)

    def list_for_submission(self, submission_id: str) -> list[Job]:
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            return uow.jobs.list_for_submission(submission_id)

    # ------------------------------------------------------------------ #
    # Manual controls
    # ------------------------------------------------------------------ #
    def retry_job(self, job_id: str) -> Job:
        """Requeue a FAILED job, retrying the compare-and-set if another
        writer (a second concurrent `retry_job` call, or a backoff-driven
        requeue) changes its state first, instead of letting
        `JobSaveConflict` surface as an unhandled 500 (review round 3, P2).
        Raises `JobRetryConflictError` if the race keeps losing.

        Refuses (`JobRetryRejectedError`) a FAILED job whose ``usable`` is
        already set: a human approved this failure's downstream effect via
        `mark_question_usable` and any dependent that was BLOCKED on it has
        already been released and may already be running or done.
        `transitioned_to` unconditionally clears `usable` on this
        FAILED -> QUEUED transition, but nothing re-blocks that already-
        released dependent to match -- letting the retry through would leave
        it processing (or having processed) an outcome this job is about to
        replace with an unknown one (review round 4, P2).

        That check alone only covers ``usable`` as read *before* this call's
        own write -- a concurrent `mark_question_usable` call can still read
        FAILED, decide to approve, and commit ``usable=True`` in the window
        between this call's own read above and its `save` below; `save`'s
        ``WHERE`` only looked at `state`, which `mark_usable` never touches,
        so it would still match and silently clear the just-granted
        approval (review round 5, P1). Passing ``require_usable_unset=True``
        adds ``usable IS NULL`` to that same compare-and-set, so a
        `mark_usable` that wins the race in that window makes this `save`
        lose instead -- the retry then re-reads fresh (below) and correctly
        rejects via the check above.

        ``expected_attempts=job.attempts`` closes the ABA hole `state`
        alone cannot: another process (or worker, elsewhere in this one)
        could complete a whole FAILED -> QUEUED -> RUNNING -> FAILED cycle
        for this same job in that same window -- a fresh, unreviewed
        attempt this call never saw -- and a state-only CAS would still
        match it, overwriting its newer `attempts`/`error_code` with this
        call's stale ones instead of losing the race (review round 9, P1).
        """
        for _attempt in range(_MAX_RETRY_ATTEMPTS):
            with SqlAlchemyUnitOfWork(self._session_factory) as uow:
                job = uow.jobs.get(job_id)
                if job is None:
                    raise JobNotFoundError(job_id)
                if job.state is not JobState.FAILED:
                    raise JobNotRetryableError(job_id, job.state)
                if job.usable is not None:
                    raise JobRetryRejectedError(job_id)
                requeued = job.transitioned_to(JobState.QUEUED, updated_at=self._clock.now())
                try:
                    uow.jobs.save(
                        requeued,
                        expected_state=JobState.FAILED,
                        expected_attempts=job.attempts,
                        require_usable_unset=True,
                    )
                except JobSaveConflict:
                    continue  # re-read the fresh state and retry the decision
                uow.commit()
            self.enqueue(job_id)
            return requeued
        raise JobRetryConflictError(job_id)

    def cancel_job(self, job_id: str) -> Job:
        """Cancel ``job_id``, retrying the compare-and-set if another writer
        (a worker finishing it, or a backoff-driven requeue) changes its
        state concurrently, instead of letting `JobSaveConflict` surface as
        an unhandled 500 (review round 2, P2). Raises `JobCancelConflictError`
        if the race keeps losing after several attempts.

        Refuses (`JobCancelRejectedError`) a FAILED job whose ``usable`` is
        already set, mirroring `retry_job`'s own guard: a human approved
        this failure's downstream effect via `mark_question_usable`, and
        any dependent released on its strength may already be queued or
        running. `transitioned_to` would clear `usable` on this
        FAILED -> CANCELLED transition without ever re-blocking that
        already-released dependent, leaving it to keep processing against a
        prerequisite now recorded as cancelled (review round 5, P2). The
        write itself also passes ``require_usable_unset=True`` to close the
        same race `retry_job` closes: a concurrent `mark_usable` committing
        between this call's own read and its write would otherwise still
        let a state-only compare-and-set through, since `mark_usable` never
        touches `state` (review round 5, P1 applied here by the same
        reasoning).

        For a RUNNING job, the returned `Job` is a pre-cancellation
        snapshot (still ``state: RUNNING``): the actual RUNNING ->
        CANCELLED write is owned by whichever worker task is processing it
        (`_finalize_cancelled`, once it notices the `CancelledError`
        `cancel_running_task` triggers), not this call, and happens
        moments later. Callers that need to know cancellation is only
        *requested*, not yet applied, must check ``result.state`` --
        `auto_scoring.api.jobs_router.cancel_job` answers 202 rather than
        200 in exactly this case (review round 6, P2).
        """
        for _attempt in range(_MAX_CANCEL_ATTEMPTS):
            with SqlAlchemyUnitOfWork(self._session_factory) as uow:
                job = uow.jobs.get(job_id)
                if job is None:
                    raise JobNotFoundError(job_id)
                if job.state in (JobState.SUCCEEDED, JobState.CANCELLED):
                    raise JobNotCancellableError(job_id, job.state)
                if job.state is JobState.FAILED and job.usable is not None:
                    raise JobCancelRejectedError(job_id)
                if job.state is JobState.RUNNING:
                    self.cancel_running_task(job_id)
                    # The running worker's own CancelledError handler
                    # (_finalize_cancelled) owns the RUNNING -> CANCELLED
                    # write, so this call must not also write it -- that
                    # would race the same UPDATE from two places.
                    uow.rollback()
                    return job
                cancelled = job.transitioned_to(
                    JobState.CANCELLED, updated_at=self._clock.now(), error="cancelled by user"
                )
                try:
                    # expected_attempts=job.attempts: when job.state is
                    # FAILED, state alone cannot rule out an ABA cycle
                    # (another process/worker completing a whole
                    # FAILED -> QUEUED -> RUNNING -> FAILED cycle for this
                    # job in this same window) making this cancel silently
                    # overwrite a newer, unrelated attempt instead of losing
                    # the race (review round 9, P1). Harmless for the other
                    # possible states here (QUEUED/BLOCKED never carry a
                    # stale `attempts` collision the same way).
                    uow.jobs.save(
                        cancelled,
                        expected_state=job.state,
                        expected_attempts=job.attempts,
                        require_usable_unset=True,
                    )
                except JobSaveConflict:
                    continue  # re-read the fresh state and retry the decision
                uow.commit()
                return cancelled
        raise JobCancelConflictError(job_id)

    def cancel_running_task(self, job_id: str) -> None:
        """Best-effort: ask whatever worker task is currently processing
        ``job_id`` (in *this* process) to stop, without touching its
        persisted state.

        Used both by `cancel_job` (RUNNING branch) and by the dependency-
        graph confirm reissue path (Issue #26) when a stale job being
        cancelled there was RUNNING -- that DB write happens in confirm's
        own transaction, so this call must not also try to persist
        anything, only signal the in-process task (review round 2, P1: a
        stale RUNNING job's actual provider call used to keep going
        indefinitely after only its DB row was flipped to CANCELLED).

        The lookup and the cancellation are scheduled together as one unit
        onto the owning event loop (never performed here directly if a
        different thread calls this), so a worker thread never reads
        `_running` while the loop thread is concurrently mutating it
        (review round 2, P2).
        """
        if self._loop is None:
            self._cancel_running_task_on_loop(job_id)
            return
        self._loop.call_soon_threadsafe(self._cancel_running_task_on_loop, job_id)

    def _cancel_running_task_on_loop(self, job_id: str) -> None:
        task = self._running.get(job_id)
        if task is not None:
            task.cancel()

    # ------------------------------------------------------------------ #
    # Worker
    # ------------------------------------------------------------------ #
    async def _run_one(self, job_id: str) -> None:
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            job = uow.jobs.get(job_id)
            if job is None or job.state is not JobState.QUEUED:
                # Already handled, cancelled while queued, or a stale
                # enqueue signal -- nothing to do.
                return
            running = job.transitioned_to(JobState.RUNNING, updated_at=self._clock.now())
            try:
                uow.jobs.save(running, expected_state=JobState.QUEUED)
            except JobSaveConflict:
                return
            uow.commit()

        # Only the CAS winner above ever reaches here, so at most one entry
        # per job_id ever exists in `_running` (review round 1, P2).
        current_task = cast(asyncio.Task[None], asyncio.current_task())
        self._running[job_id] = current_task
        try:
            started_at = self._clock.now()
            try:
                result = await self._processor.process(running)
            except asyncio.CancelledError:
                # Deliberately swallowed, not re-raised: this cancels only
                # this job's processing, not the worker's own long-lived
                # task -- `cancel_running_task` targets a specific job_id,
                # never the worker pool itself, and re-raising here would
                # permanently kill one of the pool's fixed workers.
                self._finalize_cancelled(job_id)
                return
            except Exception as exc:  # a processor bug must not crash the worker loop
                result = ProcessingResult(
                    outcome=ProcessingOutcome.FAILED,
                    error_category=ErrorCategory.PERMANENT,
                    error_message=f"processor raised {type(exc).__name__}",
                )
            latency = (self._clock.now() - started_at).total_seconds()
            retry = self._finalize_result(job_id, result, latency=latency)
        finally:
            if self._running.get(job_id) is current_task:
                self._running.pop(job_id, None)

        if retry is not None:
            delay, attempts_at_failure = retry
            self._schedule_retry(job_id, delay, expected_attempts=attempts_at_failure)

    def _schedule_retry(self, job_id: str, delay: float, *, expected_attempts: int) -> None:
        """Push a heap entry due ``delay`` seconds from now, serviced by the
        single `_retry_scheduler_task` -- decoupled from the worker pool so
        this worker is immediately free for other jobs instead of occupying
        a pool slot for the whole backoff window (review round 1, P2), and
        without spawning a new task per call the way this used to (review
        round 7, P2; see `_retry_heap`).

        ``expected_attempts`` pins this entry to the specific failed attempt
        that spawned it (`current.attempts` at the moment `_finalize_result`
        decided to retry) -- see `_requeue_after_backoff`.
        """
        due_at = self._clock.now() + timedelta(seconds=delay)
        self._retry_heap_seq += 1
        heapq.heappush(self._retry_heap, (due_at, self._retry_heap_seq, job_id, expected_attempts))
        self._retry_added.set()

    async def _retry_scheduler_loop(self) -> None:
        """Service `_retry_heap` one entry at a time, in due-time order,
        for as long as this service runs -- the single task that replaces
        one-task-per-pending-retry (review round 7, P2).

        Idles on `_retry_added` while the heap is empty. While non-empty,
        always sleeps out (via `self._clock`, so `FakeClock`-based tests
        never actually wait) exactly the *earliest* entry's own remaining
        delay before requeuing it; a new entry added mid-sleep that turns
        out to be due sooner simply waits until this sleep completes and is
        serviced on the next loop iteration, rather than interrupting it --
        a bounded, small amount of extra imprecision in exchange for never
        needing more than this one task no matter how many retries are
        pending at once. Cancelled (by `shutdown`), not run to completion:
        see `shutdown`'s own docstring for why that loses nothing.

        A `_requeue_after_backoff` call that itself raises (e.g. a
        transient SQLite busy-timeout) is caught per entry rather than left
        to escape this loop: this is the *only* task servicing
        `_retry_heap`, so letting it die would silently strand every other
        still-pending retry until the next process restart -- a worse
        outcome than losing track of just the one entry that failed
        (review round 8, P1). The failed entry is rescheduled after
        `_SCHEDULER_ERROR_RETRY_DELAY_SECONDS` instead of being dropped.
        """
        while True:
            if not self._retry_heap:
                await self._retry_added.wait()
                self._retry_added.clear()
                continue
            due_at, _, job_id, expected_attempts = heapq.heappop(self._retry_heap)
            remaining = (due_at - self._clock.now()).total_seconds()
            if remaining > 0:
                await self._clock.sleep(remaining)
            try:
                self._requeue_after_backoff(job_id, expected_attempts=expected_attempts)
            except Exception:
                logger.exception(
                    "retry scheduler failed to requeue a job; rescheduling",
                    extra={"job_id": job_id},
                )
                self._schedule_retry(
                    job_id,
                    _SCHEDULER_ERROR_RETRY_DELAY_SECONDS,
                    expected_attempts=expected_attempts,
                )

    def _finalize_cancelled(self, job_id: str) -> None:
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            current = uow.jobs.get(job_id)
            if current is None or current.state is not JobState.RUNNING:
                return
            cancelled = current.transitioned_to(
                JobState.CANCELLED, updated_at=self._clock.now(), error="cancelled by user"
            )
            try:
                uow.jobs.save(cancelled, expected_state=JobState.RUNNING)
                uow.commit()
            except JobSaveConflict:
                pass
        logger.info("job cancelled", extra={"job_id": job_id, "state": "cancelled"})

    def _retry_policy_for(self, job: Job) -> RetryPolicy:
        """A `RetryPolicy` using *this job's own* persisted `max_attempts`,
        not the service's current `QueueSettings.max_attempts` -- those can
        differ (settings changed since this job was created, a reissued or
        legacy job carrying a different value), and the decision of whether
        another attempt is allowed must honour what was actually persisted
        for this job, not whatever the service happens to be configured with
        right now (review round 1, P2). Cannot fail validation:
        `Job.max_attempts` is already required to be ``>= 1`` at
        construction, and `QueueSettings.__post_init__` already validates
        the backoff fields.
        """
        return RetryPolicy(
            max_attempts=job.max_attempts,
            initial_backoff_seconds=self._settings.initial_backoff_seconds,
            backoff_multiplier=self._settings.backoff_multiplier,
            max_backoff_seconds=self._settings.max_backoff_seconds,
        )

    def _finalize_result(
        self, job_id: str, result: ProcessingResult, *, latency: float
    ) -> tuple[float, int] | None:
        """Persist ``result`` and return ``(delay, attempts_at_failure)``
        before a retry, or ``None`` if none is needed. Purely synchronous --
        the caller (`_run_one`) hands the pair to `_schedule_retry`, which
        only pushes a heap entry; `_retry_scheduler_loop` is the one that
        actually awaits the delay, decoupled from the worker pool.
        ``attempts_at_failure`` is ``current.attempts`` at the
        moment of this decision, so `_requeue_after_backoff` can tell this
        specific attempt's timer apart from a later one (review round 3,
        P1 -- see that method).

        Both compare-and-set writes below are guarded against
        `JobSaveConflict`: a stale-job cancellation from a confirmed
        dependency-graph version advance (`dependency_graph_router.confirm`)
        can flip this same RUNNING row to CANCELLED between `_run_one`'s own
        read and this write. Left unguarded, that exception would propagate
        out of `_finalize_result` and `_run_one` into `_worker_loop`,
        permanently killing this worker's task -- at ``max_concurrency=1``,
        stopping the whole queue until a restart (review round 3, P1).
        Treated as a no-op instead: whichever writer actually won already
        owns this job's fate.
        """
        now = self._clock.now()
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            current = uow.jobs.get(job_id)
            if current is None or current.state is not JobState.RUNNING:
                # Cancelled concurrently; that handler owns the transition.
                return None

            if result.outcome is ProcessingOutcome.SUCCEEDED:
                done = current.transitioned_to(
                    JobState.SUCCEEDED, updated_at=now, usable=result.usable
                )
                try:
                    uow.jobs.save(done, expected_state=JobState.RUNNING)
                except JobSaveConflict:
                    return None
                logger.info(
                    "job succeeded",
                    extra={
                        "job_id": job_id,
                        "state": "succeeded",
                        "latency_seconds": latency,
                        "usable": result.usable,
                    },
                )
                newly_queued: list[str] = []
                if current.question_id is not None:
                    submission = uow.submissions.get(current.submission_id)
                    graph = (
                        uow.dependency_graphs.get_latest_confirmed(submission.test_id)
                        if submission is not None
                        else None
                    )
                    if graph is not None:
                        jobs = uow.jobs.list_for_submission(current.submission_id)
                        newly_queued = self._release_ready_dependents(
                            uow,
                            graph=graph,
                            jobs=jobs,
                            completed_question_id=current.question_id,
                        )
                uow.commit()
                for ready_job_id in newly_queued:
                    self.enqueue(ready_job_id)
                return None

            category = result.error_category or ErrorCategory.PERMANENT
            retry_policy = self._retry_policy_for(current)
            should_retry = retry_policy.should_retry(category=category, attempts=current.attempts)
            failed = current.transitioned_to(
                JobState.FAILED, updated_at=now, error=result.error_message, error_code=category
            )
            try:
                uow.jobs.save(failed, expected_state=JobState.RUNNING)
            except JobSaveConflict:
                return None
            logger.info(
                "job failed",
                extra={
                    "job_id": job_id,
                    "state": "failed",
                    "latency_seconds": latency,
                    "error_code": category.value,
                    "will_retry": should_retry,
                },
            )
            uow.commit()
            if not should_retry:
                return None
            return retry_policy.delay_seconds(current.attempts), current.attempts

    def _requeue_after_backoff(self, job_id: str, *, expected_attempts: int) -> None:
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            current = uow.jobs.get(job_id)
            if (
                current is None
                or current.state is not JobState.FAILED
                # Cancelled, or already retried by a manual `retry_job` call
                # while this backoff was sleeping.
                or current.attempts != expected_attempts
                # A *newer* attempt (from that manual retry) has already
                # failed again in the meantime -- this timer belongs to the
                # earlier attempt, not this one, and must not requeue an
                # attempt it was never scheduled for. That newer failure
                # either exhausted retries (must stay FAILED) or already
                # has its own, correctly-timed pending timer (review round
                # 3, P1).
                or current.usable is not None
                # A human already approved this failure's downstream effect
                # via `mark_question_usable` since this timer was scheduled
                # -- requeuing now would silently discard that approval
                # (review round 3, P1).
            ):
                return
            requeued = current.transitioned_to(JobState.QUEUED, updated_at=self._clock.now())
            try:
                # require_usable_unset=True closes the same race the check
                # above cannot: `usable` could still land between that read
                # and this write (`mark_usable` never touches `state`, so a
                # state-only CAS would otherwise still match) -- without it,
                # this save could commit right after a `/resume` call whose
                # own transaction has already released a dependent on the
                # strength of the approval this write is about to silently
                # clear (review round 8, P1; same reasoning as `retry_job`
                # and `cancel_job`, review round 5). expected_attempts=
                # current.attempts closes the ABA hole the check above
                # cannot either: another process/worker could still
                # complete a whole FAILED -> QUEUED -> RUNNING -> FAILED
                # cycle for this job between that check and this write,
                # landing back on FAILED with a newer, unreviewed attempt a
                # state-only CAS would not distinguish from this one
                # (review round 9, P1).
                uow.jobs.save(
                    requeued,
                    expected_state=JobState.FAILED,
                    expected_attempts=current.attempts,
                    require_usable_unset=True,
                )
            except JobSaveConflict:
                return
            uow.commit()
        self.enqueue(job_id)

    def _release_ready_dependents(
        self,
        uow: SqlAlchemyUnitOfWork,
        *,
        graph: DependencyGraph,
        jobs: Sequence[Job],
        completed_question_id: str,
    ) -> list[str]:
        """Re-check every direct dependent of ``completed_question_id`` and
        release (BLOCKED -> QUEUED) whichever now has every prerequisite
        usable. Must be called within ``uow``'s still-open transaction so the
        release commits atomically with the completion that triggered it.
        """
        jobs_by_question = {j.question_id: j for j in jobs if j.question_id is not None}
        statuses = question_statuses(jobs)
        newly_queued: list[str] = []
        for dependent_id in direct_dependents(graph, completed_question_id):
            dependent_job = jobs_by_question.get(dependent_id)
            if dependent_job is None or dependent_job.state is not JobState.BLOCKED:
                continue
            readiness = evaluate_readiness(graph, dependent_id, statuses)
            if readiness.ready:
                released = dependent_job.transitioned_to(
                    JobState.QUEUED, updated_at=self._clock.now()
                )
                try:
                    uow.jobs.save(released, expected_state=JobState.BLOCKED)
                except JobSaveConflict:
                    continue
                newly_queued.append(dependent_job.id)
            elif readiness.blocking_question_id != dependent_job.blocked_on_question_id:
                updated = replace(
                    dependent_job, blocked_on_question_id=readiness.blocking_question_id
                )
                try:
                    uow.jobs.save(updated, expected_state=JobState.BLOCKED)
                except JobSaveConflict:
                    continue
        return newly_queued
