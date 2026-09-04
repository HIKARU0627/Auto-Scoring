"""Ports the domain needs from the outside world.

Adapters implement these; the domain only ever sees the protocol.
"""

from typing import Protocol

from auto_scoring.domain.scoring import ScoreResult


class ScoreRepository(Protocol):
    """Persistence port for scoring results."""

    def save(self, key: str, result: ScoreResult) -> None: ...

    def get(self, key: str) -> ScoreResult | None: ...
