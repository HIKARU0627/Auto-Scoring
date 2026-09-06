"""Injectable clock so the queue's timing (timestamps and retry backoff) is
deterministic in tests (Issue #18: "時間依存…のテストを決定的にする").
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...

    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    """The real clock: wall time, real ``asyncio.sleep``."""

    def now(self) -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)

    async def sleep(self, seconds: float) -> None:
        if seconds > 0:
            await asyncio.sleep(seconds)
