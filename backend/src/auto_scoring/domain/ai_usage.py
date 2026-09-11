"""Aggregate provider-reported token usage and optional cost (Issue #187)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from auto_scoring.domain.models import GradeResult, GradingSource


class UsageAvailability(StrEnum):
    """Whether token totals are complete for the rows being summarized."""

    KNOWN = "known"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass(frozen=True, kw_only=True)
class TokenTotals:
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, kw_only=True)
class AiUsageSummary:
    totals: TokenTotals | None
    availability: UsageAvailability
    token_unit_cost: float | None
    estimated_cost: float | None


def summarize_ai_grade_tokens(grades: Sequence[GradeResult]) -> AiUsageSummary:
    """Sum token usage from AI grade rows.

    Every AI row with both token fields set contributes. Rows with neither
    field set are ignored for the sum but mark the availability partial when
    other rows did carry usage, or unknown when no row carried any.
    """
    ai_grades = [grade for grade in grades if grade.source is GradingSource.AI]
    if not ai_grades:
        return AiUsageSummary(
            totals=None,
            availability=UsageAvailability.UNKNOWN,
            token_unit_cost=None,
            estimated_cost=None,
        )

    known = [grade for grade in ai_grades if grade.input_tokens is not None]
    unknown_count = len(ai_grades) - len(known)
    if not known:
        return AiUsageSummary(
            totals=None,
            availability=UsageAvailability.UNKNOWN,
            token_unit_cost=None,
            estimated_cost=None,
        )

    totals = TokenTotals(
        input_tokens=sum(grade.input_tokens or 0 for grade in known),
        output_tokens=sum(grade.output_tokens or 0 for grade in known),
    )
    availability = (
        UsageAvailability.KNOWN if unknown_count == 0 else UsageAvailability.PARTIAL
    )
    return AiUsageSummary(
        totals=totals,
        availability=availability,
        token_unit_cost=None,
        estimated_cost=None,
    )


def apply_token_unit_cost(summary: AiUsageSummary, token_unit_cost: float | None) -> AiUsageSummary:
    """Attach optional cost from a per-1000-token unit price."""
    if summary.totals is None or summary.availability is not UsageAvailability.KNOWN:
        return AiUsageSummary(
            totals=summary.totals,
            availability=summary.availability,
            token_unit_cost=token_unit_cost,
            estimated_cost=None,
        )
    if token_unit_cost is None:
        return AiUsageSummary(
            totals=summary.totals,
            availability=summary.availability,
            token_unit_cost=None,
            estimated_cost=None,
        )
    estimated = (summary.totals.total_tokens / 1000.0) * token_unit_cost
    return AiUsageSummary(
        totals=summary.totals,
        availability=summary.availability,
        token_unit_cost=token_unit_cost,
        estimated_cost=estimated,
    )
