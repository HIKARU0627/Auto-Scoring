"""Unit tests for PoC 2 metrics, plus an end-to-end aggregation from fixtures.

The end-to-end test proves the acceptance criteria "human ground-truth labels
-> metrics", "schema violation is never scored as a real grade", and
"Recognition Confidence and Grading Confidence are never blended" (Issue #14).
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from auto_scoring.domain.ai_grading import parse_ai_grading_result
from auto_scoring.domain.ai_grading_metrics import (
    CriterionGroundTruth,
    GradingGroundTruth,
    SampleOutcome,
    evaluate_sample,
    summarize_by_provider,
    to_markdown_table,
)
from auto_scoring.domain.ai_provider import (
    GradingResponse,
    ProviderDescriptor,
    grading_response_from_result,
)
from auto_scoring.domain.models import CriterionOutcome

_FIXTURES = Path(__file__).parent / "fixtures" / "ai_grading"

_DESCRIPTOR = ProviderDescriptor(
    provider="test",
    model="test",
    version=None,
    temperature=0.0,
    structured_output_mode="json_schema",
)


def _response(**overrides: object) -> GradingResponse:
    payload: dict[str, object] = {
        "questionId": "q1",
        "recognition": {"text": "答案", "confidence": 0.9},
        "grading": {"score": 4, "maxScore": 5, "confidence": 0.8},
        "criteria": [
            {"id": "c1", "result": "pass", "confidence": 0.9, "rationale": "根拠1"},
            {"id": "c2", "result": "fail", "confidence": 0.6, "rationale": "根拠2"},
        ],
        "comment": "コメント",
        "rationale": "全体根拠",
        "annotations": [],
    }
    payload.update(overrides)
    parsed = parse_ai_grading_result(json.dumps(payload))
    return grading_response_from_result(parsed, descriptor=_DESCRIPTOR, latency_seconds=1.0)


def _truth(**overrides: object) -> GradingGroundTruth:
    defaults: dict[str, object] = dict(
        question_id="q1",
        subject="subj",
        test_id="t1",
        score=4,
        max_score=5,
        criteria=(
            CriterionGroundTruth(criterion_id="c1", outcome=CriterionOutcome.PASS),
            CriterionGroundTruth(criterion_id="c2", outcome=CriterionOutcome.FAIL),
        ),
    )
    defaults.update(overrides)
    return GradingGroundTruth(**defaults)  # type: ignore[arg-type]


def test_exact_match_and_full_criterion_agreement() -> None:
    outcome = evaluate_sample(_truth(), _response(), provider="p", input_variant="ocr_clean")
    assert outcome.exact_match is True
    assert outcome.within_tolerance is True
    assert outcome.criterion_matches == 2
    assert outcome.criterion_total == 2
    assert outcome.schema_violation is False


def test_within_tolerance_but_not_exact() -> None:
    response = _response(grading={"score": 3, "maxScore": 5, "confidence": 0.7})
    outcome = evaluate_sample(_truth(), response, provider="p", input_variant="ocr_clean")
    assert outcome.exact_match is False
    assert outcome.within_tolerance is True  # default tolerance = 1


def test_outside_tolerance() -> None:
    response = _response(grading={"score": 1, "maxScore": 5, "confidence": 0.7})
    outcome = evaluate_sample(_truth(), response, provider="p", input_variant="ocr_clean")
    assert outcome.within_tolerance is False


def test_criterion_mismatch_is_counted_not_averaged_away() -> None:
    response = _response(
        criteria=[
            {"id": "c1", "result": "pass", "confidence": 0.9, "rationale": "根拠1"},
            {"id": "c2", "result": "pass", "confidence": 0.6, "rationale": "根拠2 (誤り)"},
        ]
    )
    outcome = evaluate_sample(_truth(), response, provider="p", input_variant="ocr_clean")
    assert outcome.criterion_matches == 1
    assert outcome.criterion_total == 2


def test_schema_violation_sample_is_excluded_from_exact_match_not_scored_as_wrong() -> None:
    """A schema violation must not be silently coerced into "score 0" -- it is
    a distinct outcome (Issue #14 acceptance)."""
    with pytest.raises(ValidationError):
        parse_ai_grading_result(json.dumps({"questionId": "q1"}))

    outcome = evaluate_sample(_truth(), None, provider="p", input_variant="ocr_clean")
    assert outcome.schema_violation is True
    assert outcome.exact_match is None
    assert outcome.within_tolerance is None


def test_recognition_and_grading_confidence_stay_in_separate_columns() -> None:
    response = _response(
        recognition={"text": "答案", "confidence": 0.98},
        grading={"score": 4, "maxScore": 5, "confidence": 0.63},
    )
    outcome = evaluate_sample(_truth(), response, provider="p", input_variant="ocr_noisy")
    assert outcome.recognition_confidence == pytest.approx(0.98)
    assert outcome.grading_confidence == pytest.approx(0.63)
    assert outcome.recognition_confidence != outcome.grading_confidence


def _load_fixture_outcomes() -> list[SampleOutcome]:
    outcomes: list[SampleOutcome] = []
    for path in sorted(_FIXTURES.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        truth = GradingGroundTruth.from_mapping(raw["ground_truth"])
        for provider, variants in raw.get("recorded", {}).items():
            for variant, cell in variants.items():
                try:
                    parsed = parse_ai_grading_result(json.dumps(cell["response"]))
                except ValidationError:
                    response = None
                else:
                    response = grading_response_from_result(
                        parsed,
                        descriptor=_DESCRIPTOR,
                        latency_seconds=cell.get("latency_seconds", 0.0),
                    )
                outcomes.append(
                    evaluate_sample(
                        truth,
                        response,
                        provider=provider,
                        input_variant=variant,
                        cost_usd=cell.get("cost_usd"),
                    )
                )
    return outcomes


def test_end_to_end_aggregate_from_fixtures_is_deterministic() -> None:
    first = to_markdown_table(summarize_by_provider(_load_fixture_outcomes()))
    second = to_markdown_table(summarize_by_provider(_load_fixture_outcomes()))
    assert first == second
    assert "synthetic-a" in first
    assert "synthetic-b" in first


def test_fixtures_contain_at_least_one_schema_violation() -> None:
    """The fixture set must exercise the schema-violation path, not just the
    happy path (Issue #14: a violation must be catchable, not theoretical)."""
    outcomes = _load_fixture_outcomes()
    assert any(o.schema_violation for o in outcomes)
    assert any(not o.schema_violation for o in outcomes)


def test_markdown_table_renders_header_and_rows() -> None:
    table = to_markdown_table(summarize_by_provider(_load_fixture_outcomes()))
    assert table.startswith("| 教科 |")
    assert "schema違反率" in table
