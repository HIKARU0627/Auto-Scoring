"""PoC 2 entry point: run candidates over the fixture set and emit the report.

    uv run python -m poc.evaluate --format md
    uv run python -m poc.evaluate --format json

Deterministic: inputs are static fixtures, so repeated runs produce identical
output (受入条件, Issue #14). With no API keys configured this runs the
``ReplayAIProvider`` over recorded synthetic responses; see ``docs/ai-grading-poc.md``
for how to record real provider responses once credentials are set.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from auto_scoring.domain.ai_grading import CriterionResult
from auto_scoring.domain.ai_provider import (
    AIProvider,
    GradingRequest,
    ProviderUnavailable,
    RubricCriterion,
    SchemaViolation,
)
from poc.metrics import CaseOutcome, HumanLabel, Metrics, aggregate
from poc.replay_provider import load_replay_provider

_DEFAULT_FIXTURES = Path(__file__).resolve().parent / "fixtures"


class _HumanLabelModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: float
    criteria: dict[str, CriterionResult]


class _CaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    question_id: str
    question_text: str
    max_score: float
    reference_answer: str
    rubric: list[RubricCriterion]
    ocr_text: dict[str, str]
    answer_image_ref: str | None = None
    human_label: _HumanLabelModel


class _CaseFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tolerance_points: float = Field(gt=0.0)
    variants: list[str] = Field(min_length=1)
    cases: list[_CaseModel] = Field(min_length=1)


def _load_cases(fixtures_dir: Path) -> _CaseFile:
    return _CaseFile.model_validate_json((fixtures_dir / "cases.json").read_text(encoding="utf-8"))


def _grade_one(
    provider: AIProvider,
    request: GradingRequest,
    case_id: str,
    variant: str,
    human: HumanLabel,
) -> CaseOutcome:
    try:
        response = provider.grade(request)
    except SchemaViolation as exc:
        return CaseOutcome(
            case_id=case_id,
            variant=variant,
            human=human,
            ai=None,
            schema_violation=True,
            error=exc.reason,
        )
    except ProviderUnavailable as exc:
        return CaseOutcome(case_id=case_id, variant=variant, human=human, ai=None, error=str(exc))
    return CaseOutcome(
        case_id=case_id,
        variant=variant,
        human=human,
        ai=response.result,
        latency_s=response.latency_s,
        usage=response.usage,
    )


def _evaluate_candidate(
    candidate: str, fixtures_dir: Path, case_file: _CaseFile
) -> list[CaseOutcome]:
    outcomes: list[CaseOutcome] = []
    for variant in case_file.variants:
        provider = load_replay_provider(fixtures_dir, candidate, variant)
        for case in case_file.cases:
            human = HumanLabel(
                question_id=case.question_id,
                score=case.human_label.score,
                max_score=case.max_score,
                criteria=dict(case.human_label.criteria),
            )
            request = GradingRequest(
                question_id=case.question_id,
                question_text=case.question_text,
                max_score=case.max_score,
                rubric=case.rubric,
                reference_answer=case.reference_answer,
                ocr_text=case.ocr_text[variant],
                answer_image_ref=case.answer_image_ref,
            )
            outcomes.append(_grade_one(provider, request, case.case_id, variant, human))
    return outcomes


def run(candidates: Sequence[str], fixtures_dir: Path = _DEFAULT_FIXTURES) -> dict[str, Metrics]:
    """Evaluate each candidate; return ``{candidate: Metrics}`` ordered by key."""
    case_file = _load_cases(fixtures_dir)
    report: dict[str, Metrics] = {}
    for candidate in sorted(candidates):
        outcomes = _evaluate_candidate(candidate, fixtures_dir, case_file)
        report[candidate] = aggregate(candidate, outcomes, case_file.tolerance_points)
    return report


def _fmt(value: float | None, spec: str) -> str:
    return "n/a" if value is None else format(value, spec)


def render_markdown(report: Mapping[str, Metrics]) -> str:
    lines = [
        "| candidate | cells | answered | exact match | within ±tol | criterion agree "
        "| schema violation | latency p50 (s) | latency p95 (s) | est. USD / 100 answers |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for candidate, m in report.items():
        lines.append(
            f"| {candidate} | {m.n_cells} | {m.n_answered} "
            f"| {m.exact_match_rate:.1%} | {m.within_tolerance_rate:.1%} "
            f"| {m.criterion_agreement_rate:.1%} | {m.schema_violation_rate:.1%} "
            f"| {_fmt(m.latency_p50_s, '.2f')} | {_fmt(m.latency_p95_s, '.2f')} "
            f"| {_fmt(m.est_cost_per_100_usd, '.2f')} |"
        )
    for candidate, m in report.items():
        lines.append(
            f"\n### {candidate} — 人間採点との不一致例 (tolerance ±{m.tolerance_points:g})"
        )
        if not m.discrepancies:
            lines.append("\n(none)")
            continue
        lines.append("\n| case | variant | human | AI | Δ | criterion diffs | note |")
        lines.append("| --- | --- | ---: | ---: | ---: | --- | --- |")
        for d in m.discrepancies:
            diffs = ", ".join(f"{cd.id}: {cd.human}->{cd.ai}" for cd in d.criterion_diffs) or "-"
            lines.append(
                f"| {d.case_id} | {d.variant} | {d.human_score:g} "
                f"| {'n/a' if d.ai_score is None else format(d.ai_score, 'g')} "
                f"| {'n/a' if d.score_delta is None else format(d.score_delta, 'g')} "
                f"| {diffs} | {d.note or '-'} |"
            )
    return "\n".join(lines) + "\n"


def render_json(report: Mapping[str, Metrics]) -> str:
    payload = {candidate: asdict(m) for candidate, m in report.items()}
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PoC 2 — AI grading comparison")
    parser.add_argument(
        "--candidates",
        nargs="+",
        default=["synthetic-a", "synthetic-b"],
        help="candidate ids under fixtures/recorded/ (default: the two synthetic candidates)",
    )
    parser.add_argument("--fixtures", type=Path, default=_DEFAULT_FIXTURES)
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args(argv)

    report = run(args.candidates, args.fixtures)
    rendered = render_markdown(report) if args.format == "md" else render_json(report)
    # Force UTF-8: the report contains Japanese and the report must be identical
    # regardless of the host console code page.
    sys.stdout.buffer.write(rendered.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
