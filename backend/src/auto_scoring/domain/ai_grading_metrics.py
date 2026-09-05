"""PoC 2 metrics -- computed from human ground-truth labels.

Pure functions and plain dataclasses, mirroring the shape of
``domain/ocr_metrics.py`` for PoC 1. The harness
(``backend/poc/issue_14_ai_grading/report.py``) feeds a recorded
:class:`~auto_scoring.domain.ai_provider.GradingResponse` and a human
:class:`GradingGroundTruth` in; nothing here reaches a provider or the
network. Aggregates are secret-free by construction: only counts and
averaged scores leave this module (Issue #14 verification: "secretと答案
本文を出力せず、同じデータから集計結果を再生成できることを確認する").

Recognition Confidence and Grading Confidence are kept in separate fields and
separate summary columns throughout -- never averaged together (section 10;
Issue #14: "Recognition ConfidenceとGrading Confidenceを混同しない").
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean
from typing import Any

from auto_scoring.domain.ai_provider import GradingResponse
from auto_scoring.domain.models import CriterionOutcome

_COLUMNS = (
    "教科",
    "provider",
    "入力",
    "件数",
    "完全一致率",
    "許容点差内率",
    "criterion一致率",
    "平均Recognition Conf",
    "平均Grading Conf",
    "schema違反率",
    "p50 latency(s)",
    "概算cost(USD)",
)


@dataclass(frozen=True, kw_only=True)
class CriterionGroundTruth:
    """Human label for one rubric criterion (business rules section 6.3)."""

    criterion_id: str
    outcome: CriterionOutcome

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> CriterionGroundTruth:
        return cls(
            criterion_id=str(data["criterion_id"]),
            outcome=CriterionOutcome(str(data["outcome"])),
        )


@dataclass(frozen=True, kw_only=True)
class GradingGroundTruth:
    """Human label for one graded question (business rules section 6.3).

    Holds no student-identifying data: ``question_id`` and ``test_id`` are
    opaque ids. ``criteria`` may be a subset of the rubric's criteria when a
    single reader could not confidently confirm every item from a scanned
    correction sheet -- see the PoC 2 doc's real-data pilot caveat; an
    incomplete ``criteria`` list does not affect ``score`` /
    ``max_score`` accuracy.
    """

    question_id: str
    subject: str
    test_id: str
    score: int
    max_score: int
    criteria: tuple[CriterionGroundTruth, ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> GradingGroundTruth:
        return cls(
            question_id=str(data["question_id"]),
            subject=str(data["subject"]),
            test_id=str(data["test_id"]),
            score=int(data["score"]),
            max_score=int(data["max_score"]),
            criteria=tuple(CriterionGroundTruth.from_mapping(c) for c in data.get("criteria", ())),
        )


@dataclass(frozen=True, kw_only=True)
class SampleOutcome:
    """One recorded provider response scored against its human label.

    ``schema_violation`` samples carry no ``response`` -- the provider's raw
    output failed :func:`auto_scoring.domain.ai_grading.parse_ai_grading_result`
    and must not be scored as if it were a real grade (Issue #14 acceptance).
    """

    provider: str
    input_variant: str  # "ocr_clean" | "ocr_noisy"
    subject: str
    schema_violation: bool
    exact_match: bool | None
    within_tolerance: bool | None
    criterion_matches: int
    criterion_total: int
    recognition_confidence: float | None
    grading_confidence: float | None
    latency_seconds: float | None
    cost_usd: float | None


@dataclass(frozen=True, kw_only=True)
class BucketSummary:
    """Averaged metrics for every sample in one (subject, provider, input_variant) bucket."""

    subject: str
    provider: str
    input_variant: str
    samples: int
    exact_match_rate: float
    within_tolerance_rate: float
    criterion_agreement_rate: float | None
    mean_recognition_confidence: float | None
    mean_grading_confidence: float | None
    schema_violation_rate: float
    latency_p50: float | None
    latency_p95: float | None
    mean_cost_usd: float | None


def evaluate_sample(
    truth: GradingGroundTruth,
    response: GradingResponse | None,
    *,
    provider: str,
    input_variant: str,
    tolerance: int = 1,
    cost_usd: float | None = None,
) -> SampleOutcome:
    """Score one recorded ``response`` against its human ``truth`` label.

    ``response`` is ``None`` when the provider's raw output was rejected by
    schema validation (:class:`~auto_scoring.domain.ai_provider.SchemaViolation`)
    -- that sample counts toward ``schema_violation_rate`` and contributes no
    exact-match / within-tolerance / criterion data (Issue #14 acceptance: a
    schema violation is never scored as if it were a valid grade).
    """
    if response is None:
        return SampleOutcome(
            provider=provider,
            input_variant=input_variant,
            subject=truth.subject,
            schema_violation=True,
            exact_match=None,
            within_tolerance=None,
            criterion_matches=0,
            criterion_total=0,
            recognition_confidence=None,
            grading_confidence=None,
            latency_seconds=None,
            cost_usd=cost_usd,
        )

    truth_by_id = {c.criterion_id: c.outcome for c in truth.criteria}
    matches = sum(
        1
        for c in response.criteria
        if c.criterion_id in truth_by_id and truth_by_id[c.criterion_id] == c.outcome
    )
    total = sum(1 for c in response.criteria if c.criterion_id in truth_by_id)

    return SampleOutcome(
        provider=provider,
        input_variant=input_variant,
        subject=truth.subject,
        schema_violation=False,
        exact_match=response.score == truth.score,
        within_tolerance=abs(response.score - truth.score) <= tolerance,
        criterion_matches=matches,
        criterion_total=total,
        recognition_confidence=response.recognition_confidence,
        grading_confidence=response.grading_confidence,
        latency_seconds=response.latency_seconds,
        cost_usd=cost_usd,
    )


def _percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def _mean_or_none(values: Sequence[float]) -> float | None:
    return fmean(values) if values else None


def summarize_by_provider(samples: Iterable[SampleOutcome]) -> list[BucketSummary]:
    """Group per-sample outcomes by (subject, provider, input_variant) and average each."""
    by_bucket: dict[tuple[str, str, str], list[SampleOutcome]] = {}
    for sample in samples:
        key = (sample.subject, sample.provider, sample.input_variant)
        by_bucket.setdefault(key, []).append(sample)

    summaries: list[BucketSummary] = []
    for key in sorted(by_bucket):
        subject, provider, input_variant = key
        group = by_bucket[key]
        scored = [s for s in group if not s.schema_violation]
        recognition = [
            s.recognition_confidence for s in scored if s.recognition_confidence is not None
        ]
        grading = [s.grading_confidence for s in scored if s.grading_confidence is not None]
        latencies = [s.latency_seconds for s in scored if s.latency_seconds is not None]
        costs = [s.cost_usd for s in group if s.cost_usd is not None]
        criterion_total = sum(s.criterion_total for s in scored)
        criterion_matches = sum(s.criterion_matches for s in scored)

        summaries.append(
            BucketSummary(
                subject=subject,
                provider=provider,
                input_variant=input_variant,
                samples=len(group),
                exact_match_rate=fmean(float(bool(s.exact_match)) for s in scored)
                if scored
                else 0.0,
                within_tolerance_rate=fmean(float(bool(s.within_tolerance)) for s in scored)
                if scored
                else 0.0,
                criterion_agreement_rate=(
                    criterion_matches / criterion_total if criterion_total else None
                ),
                mean_recognition_confidence=_mean_or_none(recognition),
                mean_grading_confidence=_mean_or_none(grading),
                schema_violation_rate=fmean(float(s.schema_violation) for s in group),
                latency_p50=_percentile(latencies, 0.50),
                latency_p95=_percentile(latencies, 0.95),
                mean_cost_usd=_mean_or_none(costs),
            )
        )
    return summaries


def _fmt(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def to_markdown_table(summaries: Sequence[BucketSummary]) -> str:
    """Render bucket summaries as a Markdown table (the docs "結果表")."""
    rows = [
        "| " + " | ".join(_COLUMNS) + " |",
        "| " + " | ".join(["---"] * len(_COLUMNS)) + " |",
    ]
    for summary in summaries:
        rows.append(
            "| "
            + " | ".join(
                (
                    summary.subject,
                    summary.provider,
                    summary.input_variant,
                    str(summary.samples),
                    _fmt(summary.exact_match_rate),
                    _fmt(summary.within_tolerance_rate),
                    _fmt(summary.criterion_agreement_rate),
                    _fmt(summary.mean_recognition_confidence),
                    _fmt(summary.mean_grading_confidence),
                    _fmt(summary.schema_violation_rate),
                    _fmt(summary.latency_p50),
                    _fmt(summary.mean_cost_usd, digits=5),
                )
            )
            + " |"
        )
    return "\n".join(rows)
