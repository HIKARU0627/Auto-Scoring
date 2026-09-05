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
recovered/submitted backlog is (review round 2, P2).

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
import logging
from collections.abc import Sequence
from dataclasses import replace
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


class JobNotRetryableError(Exception):
    def __init__(self, job_id: str, state: JobState) -> None:
        super().__init__(f"job {job_id!r} is {state!s}; only a FAILED job can be retried")
        self.job_id = job_id
        self.state = state


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
        #: Backoff-wait tasks for a retryable FAILED job, decoupled from the
        #: worker pool so a job sleeping out its backoff does not occupy a
        #: worker slot another, independent submission's job could use
        #: (review round 1, P2). Bounded by recent failure rate, not by
        #: backlog size -- a fundamentally different, much smaller growth
        #: factor than the per-job dispatcher task this service no longer
        #: creates (review round 2, P2; see docs/job-queue.md).
        self._pending_retries: set[asyncio.Task[None]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

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
        sleeping out its backoff (`_pending_retries`), that in-process timer
        died with it, and nothing else would ever wake the job up again
        (review round 2, P1).
        """
        self._loop = asyncio.get_running_loop()
        to_enqueue: list[str] = []
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
                ):
                    continue
                requeued = job.transitioned_to(JobState.QUEUED, updated_at=self._clock.now())
                try:
                    uow.jobs.save(requeued, expected_state=JobState.FAILED)
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
        for job_id in to_enqueue:
            self.enqueue(job_id)

    async def shutdown(self) -> None:
        """Stop the worker pool and wait for in-flight jobs to reach a
        resting state. Does not cancel a RUNNING job's processing -- a
        graceful shutdown lets it finish; only an actual process kill
        leaves a job RUNNING for `start` to recover next time.

        Pending backoff-wait timers are cancelled rather than awaited to
        completion: the job behind each one is already durably persisted as
        FAILED with its real ``attempts``/``error_code``, so `start`'s
        retryable-FAILED sweep recovers it next time regardless of whether
        this process exited gracefully or was killed -- waiting out the
        full backoff here first would only make routine shutdowns slower
        for no benefit.
        """
        if not self._workers:
            return
        for _ in self._workers:
            self._queue.put_nowait(_STOP)
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        for task in list(self._pending_retries):
            task.cancel()
        if self._pending_retries:
            await asyncio.gather(*list(self._pending_retries), return_exceptions=True)

    async def _worker_loop(self) -> None:
        while True:
            item = await self._queue.get()
            if item is _STOP:
                return
            await self._run_one(cast(str, item))

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

        Both SUCCEEDED and FAILED are eligible (review round 2, P1): a human
        may approve a low-confidence *success* or correct a *failure*'s
        downstream effect -- `list_for_submission` returning jobs oldest-
        first is also why this only ever considers the active version (or,
        for the fallback, the most recently updated row): picking any
        SUCCEEDED/FAILED match regardless of recency could revive a stale,
        superseded result instead of the real last one (review round 1, P2).
        """
        newly_queued: list[str] = []
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            submission = uow.submissions.get(submission_id)
            if submission is None:
                raise JobNotFoundError(submission_id)
            graph = uow.dependency_graphs.get_latest_confirmed(submission.test_id)
            if graph is None:
                raise JobNotFoundError(f"{submission_id}:{question_id}")

            jobs = uow.jobs.list_for_submission(submission_id)
            terminal_states = (JobState.SUCCEEDED, JobState.FAILED)
            at_active_version = [
                j
                for j in jobs
                if j.question_id == question_id
                and j.state in terminal_states
                and j.dependency_graph_version == graph.version
            ]
            candidates = at_active_version or [
                j for j in jobs if j.question_id == question_id and j.state in terminal_states
            ]
            target = max(candidates, key=lambda j: j.updated_at, default=None)
            if target is None:
                raise JobNotFoundError(f"{submission_id}:{question_id}")

            uow.jobs.mark_usable(target.id, usable=True)
            jobs = [replace(target, usable=True) if j.id == target.id else j for j in jobs]

            newly_queued = self._release_ready_dependents(
                uow, graph=graph, jobs=jobs, completed_question_id=question_id
            )
            uow.commit()
        for job_id in newly_queued:
            self.enqueue(job_id)

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
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            job = uow.jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            if job.state is not JobState.FAILED:
                raise JobNotRetryableError(job_id, job.state)
            requeued = job.transitioned_to(JobState.QUEUED, updated_at=self._clock.now())
            uow.jobs.save(requeued, expected_state=JobState.FAILED)
            uow.commit()
        self.enqueue(job_id)
        return requeued

    def cancel_job(self, job_id: str) -> Job:
        """Cancel ``job_id``, retrying the compare-and-set if another writer
        (a worker finishing it, or a backoff-driven requeue) changes its
        state concurrently, instead of letting `JobSaveConflict` surface as
        an unhandled 500 (review round 2, P2). Raises `JobCancelConflictError`
        if the race keeps losing after several attempts.
        """
        for _attempt in range(_MAX_CANCEL_ATTEMPTS):
            with SqlAlchemyUnitOfWork(self._session_factory) as uow:
                job = uow.jobs.get(job_id)
                if job is None:
                    raise JobNotFoundError(job_id)
                if job.state in (JobState.SUCCEEDED, JobState.CANCELLED):
                    raise JobNotCancellableError(job_id, job.state)
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
                    uow.jobs.save(cancelled, expected_state=job.state)
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
            retry_delay = self._finalize_result(job_id, result, latency=latency)
        finally:
            if self._running.get(job_id) is current_task:
                self._running.pop(job_id, None)

        if retry_delay is not None:
            self._schedule_retry(job_id, retry_delay)

    def _schedule_retry(self, job_id: str, delay: float) -> None:
        """Wait out ``delay`` and requeue, on a task decoupled from the
        worker pool (see `_pending_retries`) so this worker is immediately
        free for other jobs instead of occupying a pool slot for the whole
        backoff window (review round 1, P2).
        """
        task = asyncio.create_task(self._sleep_then_requeue(job_id, delay))
        self._pending_retries.add(task)
        task.add_done_callback(self._pending_retries.discard)

    async def _sleep_then_requeue(self, job_id: str, delay: float) -> None:
        await self._clock.sleep(delay)
        self._requeue_after_backoff(job_id)

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
    ) -> float | None:
        """Persist ``result`` and return the backoff delay before a retry,
        or ``None`` if none is needed. Purely synchronous -- the caller
        (`_run_one`) hands the delay to `_schedule_retry`, which is the one
        that actually awaits it, decoupled from the worker pool.
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
                uow.jobs.save(done, expected_state=JobState.RUNNING)
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
            uow.jobs.save(failed, expected_state=JobState.RUNNING)
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
            return retry_policy.delay_seconds(current.attempts) if should_retry else None

    def _requeue_after_backoff(self, job_id: str) -> None:
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            current = uow.jobs.get(job_id)
            if current is None or current.state is not JobState.FAILED:
                # Cancelled, or already retried by a manual `retry_job` call
                # while this backoff was sleeping.
                return
            requeued = current.transitioned_to(JobState.QUEUED, updated_at=self._clock.now())
            try:
                uow.jobs.save(requeued, expected_state=JobState.FAILED)
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
