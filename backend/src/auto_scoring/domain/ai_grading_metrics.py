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

A recorded response is only ever scored against the ground-truth label it
actually answers: ``evaluate_sample`` rejects (as ``mismatched``, distinct
from a schema violation) a response whose ``question_id`` or ``max_score``
does not match the label it is being compared against, so an answer to a
different question can never register as an accidental exact match
(code review finding: comparing raw scores alone let a 4/100 answer to the
wrong question count as matching a 4/5 truth label).

Every outcome also carries a ``config_key`` (see
:func:`auto_scoring.domain.ai_provider.descriptor_key`): two recordings under
the same ``provider`` name but a different model / version / prompt version /
temperature / structured-output mode are aggregated into separate buckets,
never pooled (code review finding: pooling could let a passing and a failing
configuration average out to something that looks like it cleared the
adoption gate).

``criterion_agreement_rate`` is computed against every *labeled*
ground-truth criterion, not just the ones a response happens to return: a
response that omits a hard criterion counts as disagreeing on it, rather
than shrinking the denominator and inflating the rate towards 100%
(code review finding).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from auto_scoring.domain.ai_provider import GradingResponse
from auto_scoring.domain.models import CriterionOutcome

#: Grading Confidence at/above this counts as "high confidence" for the
#: calibration gate (docs/poc-2-ai-grading.md section 8.1).
_HIGH_CONFIDENCE_THRESHOLD = 0.8

#: Grading Confidence below this counts as "low confidence" for the same gate.
_LOW_CONFIDENCE_THRESHOLD = 0.5

_COLUMNS = (
    "教科",
    "provider",
    "config",
    "入力",
    "件数",
    "完全一致率",
    "許容点差内率",
    "criterion一致率",
    "平均Recognition Conf",
    "平均Grading Conf",
    "schema違反率",
    "対応不一致率",
    "p50 latency(s)",
    "p95 latency(s)",
    "latency計測件数",
    "概算cost(USD/1000問)",
    "cost計測件数",
    "高Conf誤り率(>=0.8)",
    "低Conf誤り率(<0.5)",
)

#: A required string that must contain more than just whitespace. Plain
#: ``min_length=1`` accepts ``" "``; this also strips before checking length.
_NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CriterionGroundTruth(BaseModel):
    """Human label for one rubric criterion (business rules section 6.3).

    Strict + non-blank-checked: an external ``--dataset`` file is untrusted
    input, same as a provider response (code review finding: silent coercion
    of a malformed label -- e.g. a blank id -- would produce metrics that
    look valid but are not).
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    criterion_id: _NonBlankStr
    outcome: CriterionOutcome


class GradingGroundTruth(BaseModel):
    """Human label for one graded question (business rules section 6.3).

    Holds no student-identifying data: ``question_id`` and ``test_id`` are
    opaque ids. ``criteria`` may be a subset of the rubric's criteria when a
    single reader could not confidently confirm every item from a scanned
    correction sheet -- see the PoC 2 doc's real-data pilot caveat; an
    incomplete ``criteria`` list does not affect ``score`` /
    ``max_score`` accuracy.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    question_id: _NonBlankStr
    subject: _NonBlankStr
    test_id: _NonBlankStr
    score: int = Field(ge=0)
    max_score: int = Field(ge=0)
    criteria: tuple[CriterionGroundTruth, ...] = ()

    @model_validator(mode="after")
    def _validate_invariants(self) -> GradingGroundTruth:
        if self.score > self.max_score:
            raise ValueError(f"score {self.score} exceeds max_score {self.max_score}")
        ids = [c.criterion_id for c in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("criteria contains duplicate criterion_id")
        return self

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> GradingGroundTruth:
        """Parse and validate a ground-truth mapping loaded from ``--dataset`` JSON.

        Goes through the JSON-validation code path (``model_validate_json``,
        not ``model_validate`` on the raw ``dict``) so ``strict=True`` still
        accepts a JSON array for ``criteria`` -- JSON has no tuple literal,
        so pydantic treats a list as valid input for a tuple field even in
        strict mode; only scalar coercion (e.g. the string ``"4"`` for an
        ``int`` field) is rejected.
        """
        return cls.model_validate_json(json.dumps(data, ensure_ascii=False))


@dataclass(frozen=True, kw_only=True)
class SampleOutcome:
    """One recorded provider response scored against its human label.

    ``schema_violation`` samples carry no ``response`` -- the provider's raw
    output failed :func:`auto_scoring.domain.ai_grading.parse_ai_grading_result`
    and must not be scored as if it were a real grade (Issue #14 acceptance).

    ``mismatched`` samples carry a schema-*valid* response that does not
    correspond to the ground-truth label it was evaluated against (different
    ``question_id`` and/or ``max_score``) -- also never scored as a real
    grade, and reported separately from a schema violation so the two
    failure modes are not conflated.

    ``config_key`` (see
    :func:`auto_scoring.domain.ai_provider.descriptor_key`) is required: a
    sample is only ever produced from a cell whose reproducibility metadata
    was read (or, for a pending cell, never produced at all -- pending cells
    are counted separately by the harness, not represented here).
    """

    provider: str
    config_key: str
    input_variant: str  # "ocr_clean" | "ocr_noisy"
    subject: str
    schema_violation: bool
    mismatched: bool
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
    """Averaged metrics for every sample in one (subject, provider, config, input_variant) bucket.

    ``exact_match_rate`` / ``within_tolerance_rate`` are ``None`` (rendered
    ``-``, never ``0.0``) when the bucket has no scorable sample -- every
    response was a schema violation or a mismatch. A ``0.0`` there would read
    as "0% correct", not "nothing to score" (code review finding).

    ``latency_measured`` / ``cost_measured`` count how many of ``samples``
    actually carried that measurement, so a percentile or mean computed from
    a partial subset is never mistaken for one computed over the full bucket
    (code review finding: a latency p95 from 2 of 20 calls looked identical
    to one from all 20).
    """

    subject: str
    provider: str
    config_key: str
    input_variant: str
    samples: int
    exact_match_rate: float | None
    within_tolerance_rate: float | None
    criterion_agreement_rate: float | None
    mean_recognition_confidence: float | None
    mean_grading_confidence: float | None
    schema_violation_rate: float
    mismatch_rate: float
    latency_p50: float | None
    latency_p95: float | None
    latency_measured: int
    mean_cost_usd: float | None
    cost_measured: int
    high_confidence_wrong_rate: float | None
    low_confidence_wrong_rate: float | None


def evaluate_sample(
    truth: GradingGroundTruth,
    response: GradingResponse | None,
    *,
    provider: str,
    config_key: str,
    input_variant: str,
    tolerance: int = 1,
    cost_usd: float | None = None,
    latency_seconds: float | None = None,
) -> SampleOutcome:
    """Score one recorded ``response`` against its human ``truth`` label.

    ``config_key`` (see
    :func:`auto_scoring.domain.ai_provider.descriptor_key`) is required and
    keyed on downstream, alongside ``provider``: two recordings under the
    same provider name but different model/version/temperature/output-mode
    settings must end up in different buckets, not pooled together.

    ``response`` is ``None`` when the provider's raw output was rejected by
    schema validation (:class:`~auto_scoring.domain.ai_provider.SchemaViolation`)
    -- that sample counts toward ``schema_violation_rate`` and contributes no
    exact-match / within-tolerance / criterion data (Issue #14 acceptance: a
    schema violation is never scored as if it were a valid grade).

    A schema-*valid* ``response`` whose ``question_id`` or ``max_score``
    does not match ``truth`` is rejected the same way, as ``mismatched``:
    comparing only the raw ``score`` values would let an answer to a
    different question register as an accidental exact match.

    ``latency_seconds`` is taken as given, independent of whether ``response``
    parsed -- a failed or mismatched call still took real time, and a cell
    with no recorded measurement is genuinely unknown, not a fabricated 0s
    (code review finding).
    """
    if response is None:
        return SampleOutcome(
            provider=provider,
            config_key=config_key,
            input_variant=input_variant,
            subject=truth.subject,
            schema_violation=True,
            mismatched=False,
            exact_match=None,
            within_tolerance=None,
            criterion_matches=0,
            criterion_total=0,
            recognition_confidence=None,
            grading_confidence=None,
            latency_seconds=latency_seconds,
            cost_usd=cost_usd,
        )

    if response.question_id != truth.question_id or response.max_score != truth.max_score:
        return SampleOutcome(
            provider=provider,
            config_key=config_key,
            input_variant=input_variant,
            subject=truth.subject,
            schema_violation=False,
            mismatched=True,
            exact_match=None,
            within_tolerance=None,
            criterion_matches=0,
            criterion_total=0,
            recognition_confidence=None,
            grading_confidence=None,
            latency_seconds=latency_seconds,
            cost_usd=cost_usd,
        )

    # Denominator is every *labeled* ground-truth criterion, not whatever the
    # response happened to return: a response that silently omits a hard
    # criterion must not shrink the denominator and inflate its agreement
    # rate to 100% (code review finding). A criterion the human labeler did
    # not record at all (not in ``truth.criteria``) is still ignored, same
    # as before -- only labeled criteria enter the denominator.
    response_by_id = {c.criterion_id: c.outcome for c in response.criteria}
    total = len(truth.criteria)
    matches = sum(1 for c in truth.criteria if response_by_id.get(c.criterion_id) == c.outcome)

    return SampleOutcome(
        provider=provider,
        config_key=config_key,
        input_variant=input_variant,
        subject=truth.subject,
        schema_violation=False,
        mismatched=False,
        exact_match=response.score == truth.score,
        within_tolerance=abs(response.score - truth.score) <= tolerance,
        criterion_matches=matches,
        criterion_total=total,
        recognition_confidence=response.recognition_confidence,
        grading_confidence=response.grading_confidence,
        latency_seconds=latency_seconds,
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


def _wrong_rate(samples: Sequence[SampleOutcome]) -> float | None:
    """Fraction of ``samples`` that did not exact-match (``None`` if empty)."""
    return fmean(float(not bool(s.exact_match)) for s in samples) if samples else None


def summarize_by_provider(samples: Iterable[SampleOutcome]) -> list[BucketSummary]:
    """Group per-sample outcomes by (subject, provider, config, input_variant) and average each."""
    by_bucket: dict[tuple[str, str, str, str], list[SampleOutcome]] = {}
    for sample in samples:
        key = (sample.subject, sample.provider, sample.config_key, sample.input_variant)
        by_bucket.setdefault(key, []).append(sample)

    summaries: list[BucketSummary] = []
    for key in sorted(by_bucket):
        subject, provider, config_key, input_variant = key
        group = by_bucket[key]
        # Correctness / criterion / confidence stats only make sense for a
        # response that both parsed and answers the right question.
        scored = [s for s in group if not s.schema_violation and not s.mismatched]
        recognition = [
            s.recognition_confidence for s in scored if s.recognition_confidence is not None
        ]
        grading = [s.grading_confidence for s in scored if s.grading_confidence is not None]
        # Latency and cost reflect the call itself, independent of whether
        # the response was structurally valid -- computed over the full
        # group, not just ``scored`` (code review finding). The measured
        # count is reported alongside so a partial subset is never mistaken
        # for a complete one.
        latencies = [s.latency_seconds for s in group if s.latency_seconds is not None]
        costs = [s.cost_usd for s in group if s.cost_usd is not None]
        criterion_total = sum(s.criterion_total for s in scored)
        criterion_matches = sum(s.criterion_matches for s in scored)
        high_confidence = [
            s
            for s in scored
            if s.grading_confidence is not None
            and s.grading_confidence >= _HIGH_CONFIDENCE_THRESHOLD
        ]
        low_confidence = [
            s
            for s in scored
            if s.grading_confidence is not None and s.grading_confidence < _LOW_CONFIDENCE_THRESHOLD
        ]

        summaries.append(
            BucketSummary(
                subject=subject,
                provider=provider,
                config_key=config_key,
                input_variant=input_variant,
                samples=len(group),
                exact_match_rate=(
                    fmean(float(bool(s.exact_match)) for s in scored) if scored else None
                ),
                within_tolerance_rate=(
                    fmean(float(bool(s.within_tolerance)) for s in scored) if scored else None
                ),
                criterion_agreement_rate=(
                    criterion_matches / criterion_total if criterion_total else None
                ),
                mean_recognition_confidence=_mean_or_none(recognition),
                mean_grading_confidence=_mean_or_none(grading),
                schema_violation_rate=fmean(float(s.schema_violation) for s in group),
                mismatch_rate=fmean(float(s.mismatched) for s in group),
                latency_p50=_percentile(latencies, 0.50),
                latency_p95=_percentile(latencies, 0.95),
                latency_measured=len(latencies),
                mean_cost_usd=_mean_or_none(costs),
                cost_measured=len(costs),
                high_confidence_wrong_rate=_wrong_rate(high_confidence),
                low_confidence_wrong_rate=_wrong_rate(low_confidence),
            )
        )
    return summaries


def _fmt(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _escape_markdown_cell(value: str) -> str:
    """Escape a literal ``|`` so it cannot be mistaken for a column separator.

    ``config_key`` (see ``auto_scoring.domain.ai_provider.descriptor_key``)
    always contains ``|`` characters; inserted verbatim into a Markdown
    table row, each one opens extra cells and shifts every following column
    (code review finding).
    """
    return value.replace("|", "\\|")


def _fmt_count(measured: int, total: int) -> str:
    """Render "measured/total", flagging partial coverage the reader must not
    mistake for a complete measurement (code review finding)."""
    return f"{measured}/{total}"


def to_markdown_table(summaries: Sequence[BucketSummary]) -> str:
    """Render bucket summaries as a Markdown table (the docs "結果表").

    Cost is rendered per 1,000 questions (``mean_cost_usd * 1000``) to match
    the unit the adoption gate is written in
    (docs/poc-2-ai-grading.md section 8.1: "概算 cost: <= 3 USD / 1,000
    設問"); the internal ``mean_cost_usd`` stays per-question.
    """
    rows = [
        "| " + " | ".join(_COLUMNS) + " |",
        "| " + " | ".join(["---"] * len(_COLUMNS)) + " |",
    ]
    for summary in summaries:
        cost_per_1k = None if summary.mean_cost_usd is None else summary.mean_cost_usd * 1000
        rows.append(
            "| "
            + " | ".join(
                (
                    summary.subject,
                    summary.provider,
                    _escape_markdown_cell(summary.config_key),
                    summary.input_variant,
                    str(summary.samples),
                    _fmt(summary.exact_match_rate),
                    _fmt(summary.within_tolerance_rate),
                    _fmt(summary.criterion_agreement_rate),
                    _fmt(summary.mean_recognition_confidence),
                    _fmt(summary.mean_grading_confidence),
                    _fmt(summary.schema_violation_rate),
                    _fmt(summary.mismatch_rate),
                    _fmt(summary.latency_p50),
                    _fmt(summary.latency_p95),
                    _fmt_count(summary.latency_measured, summary.samples),
                    _fmt(cost_per_1k, digits=2),
                    _fmt_count(summary.cost_measured, summary.samples),
                    _fmt(summary.high_confidence_wrong_rate),
                    _fmt(summary.low_confidence_wrong_rate),
                )
            )
            + " |"
        )
    return "\n".join(rows)
