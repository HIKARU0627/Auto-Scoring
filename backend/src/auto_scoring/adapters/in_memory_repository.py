"""In-memory implementation of :class:`ScoreRepository`.

Real persistence (SQLite via SQLAlchemy) arrives in a later issue; this keeps
the wiring honest without a database.
"""

from auto_scoring.domain.scoring import ScoreResult


class InMemoryScoreRepository:
    """Dict-backed :class:`~auto_scoring.domain.repository.ScoreRepository`."""

    def __init__(self) -> None:
        self._store: dict[str, ScoreResult] = {}

    def save(self, key: str, result: ScoreResult) -> None:
        self._store[key] = result

    def get(self, key: str) -> ScoreResult | None:
        return self._store.get(key)
