"""Tests for the PoC 2 aggregation and the reproducibility guarantee (Issue #14)."""

from __future__ import annotations

from pathlib import Path

from auto_scoring.domain.ai_grading import AIGradingResult
from auto_scoring.domain.ai_provider import TokenUsage
from poc.evaluate import render_json, render_markdown, run
from poc.metrics import CaseOutcome, HumanLabel, aggregate

_FIXTURES = Path(__file__).resolve().parents[1] / "poc" / "fixtures"


def _ai(score: float, criteria: list[tuple[str, str]]) -> AIGradingResult:
    return AIGradingResult.model_validate(
        {
            "questionId": "q",
            "recognition": {"text": "x", "confidence": 0.9},
            "grading": {"score": score, "maxScore": 5, "confidence": 0.8, "rationale": "r"},
            "criteria": [
                {"id": cid, "result": res, "confidence": 0.8, "rationale": "r"}
                for cid, res in criteria
            ],
            "comment": "c",
        }
    )


def _human(score: float, criteria: dict[str, str]) -> HumanLabel:
    return HumanLabel(question_id="q", score=score, max_score=5, criteria=criteria)  # type: ignore[arg-type]


def test_exact_and_tolerance_and_criterion_rates() -> None:
    outcomes = [
        CaseOutcome(
            "a", "clean", _human(4, {"c1": "pass"}), _ai(4, [("c1", "pass")]), latency_s=1.0
        ),
        CaseOutcome(
            "b", "clean", _human(4, {"c1": "pass"}), _ai(3, [("c1", "fail")]), latency_s=3.0
        ),
    ]
    m = aggregate("synthetic-a", outcomes, tolerance_points=1.0)
    assert m.exact_match_rate == 0.5
    assert m.within_tolerance_rate == 1.0
    assert m.criterion_agreement_rate == 0.5
    assert m.schema_violation_rate == 0.0
    assert m.latency_p50_s == 1.0
    assert len(m.discrepancies) == 1
    assert m.discrepancies[0].case_id == "b"


def test_schema_violation_counts_as_non_match_and_is_reported() -> None:
    outcomes = [
        CaseOutcome(
            "a", "noisy", _human(4, {"c1": "pass"}), None, schema_violation=True, error="bad"
        ),
    ]
    m = aggregate("synthetic-a", outcomes, tolerance_points=1.0)
    assert m.schema_violation_rate == 1.0
    assert m.exact_match_rate == 0.0
    assert m.n_answered == 0
    assert m.discrepancies[0].note == "bad"


def test_missing_criterion_counts_as_disagreement() -> None:
    outcomes = [
        CaseOutcome(
            "a",
            "clean",
            _human(4, {"c1": "pass", "c2": "partial"}),
            _ai(4, [("c1", "pass")]),
        ),
    ]
    assert aggregate("synthetic-a", outcomes, tolerance_points=1.0).criterion_agreement_rate == 0.5


def test_cost_estimate_uses_pricing_table() -> None:
    outcomes = [
        CaseOutcome(
            "a",
            "clean",
            _human(4, {"c1": "pass"}),
            _ai(4, [("c1", "pass")]),
            usage=TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000),
        ),
    ]
    m = aggregate("synthetic-a", outcomes, tolerance_points=1.0)
    # synthetic-a: 1.25 + 5.00 per MTok pair, one answer -> * 100.
    assert m.est_cost_per_100_usd == (1.25 + 5.00) * 100


def test_run_is_reproducible_from_the_same_fixtures() -> None:
    first = run(["synthetic-a", "synthetic-b"], _FIXTURES)
    second = run(["synthetic-a", "synthetic-b"], _FIXTURES)
    assert render_json(first) == render_json(second)
    assert render_markdown(first) == render_markdown(second)


def test_candidate_order_is_stable_regardless_of_argument_order() -> None:
    assert list(run(["synthetic-b", "synthetic-a"], _FIXTURES)) == ["synthetic-a", "synthetic-b"]


def test_real_candidates_are_reproducible_from_recorded_fixtures() -> None:
    """gemini / openai replay real, previously-recorded responses (docs/ai-grading-poc.md
    §4/§5) — no network call happens in this test, and the report must still be
    byte-identical across runs."""
    first = run(["gemini", "openai"], _FIXTURES)
    second = run(["gemini", "openai"], _FIXTURES)
    assert render_json(first) == render_json(second)
    for candidate in ("gemini", "openai"):
        assert first[candidate].n_cells == 6
        assert first[candidate].schema_violation_rate == 0.0


def test_report_contains_no_answer_text() -> None:
    rendered = render_json(run(["synthetic-a", "synthetic-b"], _FIXTURES))
    # OCR / answer bodies from cases.json must never reach the report.
    assert "光エネルギー" not in rendered
    assert "蒸散" not in rendered
