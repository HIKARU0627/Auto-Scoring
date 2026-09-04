"""Aggregation for PoC 2: agreement with human scoring and output stability.

All functions are pure and order-independent so the report is reproducible from
the same inputs. No answer text, student identifier, or secret is ever read or
emitted here — discrepancy rows carry only ids, results, and score deltas.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from auto_scoring.domain.ai_grading import AIGradingResult, CriterionResult
from auto_scoring.domain.ai_provider import TokenUsage
from poc.pricing import PRICES, estimate_cost_usd


@dataclass(frozen=True)
class HumanLabel:
    """The confirmed human score for one question (業務ルール §6.3, ``source: human``)."""

    question_id: str
    score: float
    max_score: float
    criteria: dict[str, CriterionResult]


@dataclass(frozen=True)
class CaseOutcome:
    """One evaluated ``(case, ocr_variant)`` cell."""

    case_id: str
    variant: str
    human: HumanLabel
    ai: AIGradingResult | None
    schema_violation: bool = False
    error: str | None = None
    latency_s: float | None = None
    usage: TokenUsage | None = None


@dataclass(frozen=True)
class CriterionDiff:
    id: str
    human: CriterionResult
    ai: CriterionResult


@dataclass(frozen=True)
class Discrepancy:
    """A human/AI mismatch worth eyeballing. Ids and numbers only."""

    case_id: str
    variant: str
    human_score: float
    ai_score: float | None
    score_delta: float | None
    criterion_diffs: list[CriterionDiff] = field(default_factory=list)
    note: str | None = None


@dataclass(frozen=True)
class Metrics:
    candidate: str
    tolerance_points: float
    n_cells: int
    n_answered: int
    exact_match_rate: float
    within_tolerance_rate: float
    criterion_agreement_rate: float
    schema_violation_rate: float
    latency_p50_s: float | None
    latency_p95_s: float | None
    est_cost_per_100_usd: float | None
    discrepancies: list[Discrepancy]


def _percentile(values: Sequence[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1))))
    return ordered[rank]


def _criterion_diffs(outcome: CaseOutcome) -> list[CriterionDiff]:
    if outcome.ai is None:
        return []
    ai_by_id = {c.id: c.result for c in outcome.ai.criteria}
    diffs: list[CriterionDiff] = []
    for cid in sorted(outcome.human.criteria):
        human_result = outcome.human.criteria[cid]
        ai_result = ai_by_id.get(cid)
        if ai_result is not None and ai_result != human_result:
            diffs.append(CriterionDiff(id=cid, human=human_result, ai=ai_result))
    return diffs


def aggregate(candidate: str, outcomes: Sequence[CaseOutcome], tolerance_points: float) -> Metrics:
    """Compute the comparison-table row for one candidate.

    ``exact_match`` / ``within_tolerance`` rates are over *all* cells: a schema
    violation or missing answer counts as a non-match (conservative), and is also
    reported via ``schema_violation_rate``. ``criterion_agreement`` is over the
    criteria that were actually answered.
    """
    cells = sorted(outcomes, key=lambda o: (o.case_id, o.variant))
    n_cells = len(cells)
    answered = [o for o in cells if o.ai is not None]

    exact = sum(1 for o in answered if o.ai is not None and o.ai.grading.score == o.human.score)
    within = sum(
        1
        for o in answered
        if o.ai is not None and abs(o.ai.grading.score - o.human.score) <= tolerance_points
    )

    criterion_total = 0
    criterion_agree = 0
    for outcome in answered:
        assert outcome.ai is not None
        ai_by_id = {c.id: c.result for c in outcome.ai.criteria}
        criterion_total += len(outcome.human.criteria)
        for cid, human_result in outcome.human.criteria.items():
            if ai_by_id.get(cid) == human_result:
                criterion_agree += 1

    violations = sum(1 for o in cells if o.schema_violation)

    latencies = [o.latency_s for o in cells if o.latency_s is not None]
    usages = [o.usage for o in cells if o.usage is not None]
    price = PRICES.get(candidate)
    cost_per_100: float | None = None
    if price is not None and usages:
        cost_per_100 = estimate_cost_usd(usages, price) / len(usages) * 100

    discrepancies: list[Discrepancy] = []
    for outcome in cells:
        if outcome.ai is None:
            discrepancies.append(
                Discrepancy(
                    case_id=outcome.case_id,
                    variant=outcome.variant,
                    human_score=outcome.human.score,
                    ai_score=None,
                    score_delta=None,
                    note=outcome.error
                    or ("schema_violation" if outcome.schema_violation else None),
                )
            )
            continue
        delta = outcome.ai.grading.score - outcome.human.score
        diffs = _criterion_diffs(outcome)
        if abs(delta) > tolerance_points or diffs:
            discrepancies.append(
                Discrepancy(
                    case_id=outcome.case_id,
                    variant=outcome.variant,
                    human_score=outcome.human.score,
                    ai_score=outcome.ai.grading.score,
                    score_delta=round(delta, 4),
                    criterion_diffs=diffs,
                )
            )

    return Metrics(
        candidate=candidate,
        tolerance_points=tolerance_points,
        n_cells=n_cells,
        n_answered=len(answered),
        exact_match_rate=_rate(exact, n_cells),
        within_tolerance_rate=_rate(within, n_cells),
        criterion_agreement_rate=_rate(criterion_agree, criterion_total),
        schema_violation_rate=_rate(violations, n_cells),
        latency_p50_s=_percentile(latencies, 50),
        latency_p95_s=_percentile(latencies, 95),
        est_cost_per_100_usd=cost_per_100,
        discrepancies=discrepancies,
    )


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
