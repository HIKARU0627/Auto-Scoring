"""The process-in-process asyncio job queue (Issue #18).

Layout follows docs/technology-stack.md §5's reserved location
(``backend/src/auto_scoring/jobs/``). This package sits between ``api`` and
``domain``/``adapters``: it drives `auto_scoring.domain.models.Job` rows
through `auto_scoring.domain.job_scheduling`'s pure decisions using a real
``asyncio.Queue`` + ``asyncio.Semaphore`` worker pool and a
`auto_scoring.adapters.unit_of_work.SqlAlchemyUnitOfWork` per transaction, but
is not itself framework-free domain code (see docs/job-queue.md).
"""

from __future__ import annotations
