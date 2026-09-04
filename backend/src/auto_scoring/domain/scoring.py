"""Pure scoring rules."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreResult:
    """Outcome of scoring a single answer."""

    awarded: int
    maximum: int

    @property
    def ratio(self) -> float:
        """Fraction of the available points that were awarded (0.0 to 1.0)."""
        if self.maximum == 0:
            return 0.0
        return self.awarded / self.maximum


def clamp_score(raw: int, maximum: int) -> ScoreResult:
    """Clamp a raw point value into the valid ``0..maximum`` range."""
    if maximum < 0:
        raise ValueError("maximum must be non-negative")
    awarded = max(0, min(raw, maximum))
    return ScoreResult(awarded=awarded, maximum=maximum)
