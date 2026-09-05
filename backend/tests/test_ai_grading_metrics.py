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
    descriptor_key,
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
_CONFIG = descriptor_key(_DESCRIPTOR)

_OTHER_DESCRIPTOR = ProviderDescriptor(
    provider="test",
    model="test",
    version=None,
    temperature=0.9,
    structured_output_mode="tool_use",
)
_OTHER_CONFIG = descriptor_key(_OTHER_DESCRIPTOR)


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


def _evaluate(
    truth: GradingGroundTruth, response: GradingResponse | None, **kwargs: object
) -> SampleOutcome:
    kwargs.setdefault("provider", "p")
    kwargs.setdefault("config_key", _CONFIG)
    kwargs.setdefault("input_variant", "ocr_clean")
    return evaluate_sample(truth, response, **kwargs)  # type: ignore[arg-type]


def test_exact_match_and_full_criterion_agreement() -> None:
    outcome = _evaluate(_truth(), _response())
    assert outcome.exact_match is True
    assert outcome.within_tolerance is True
    assert outcome.criterion_matches == 2
    assert outcome.criterion_total == 2
    assert outcome.schema_violation is False
    assert outcome.mismatched is False
    assert outcome.config_key == _CONFIG


def test_within_tolerance_but_not_exact() -> None:
    response = _response(grading={"score": 3, "maxScore": 5, "confidence": 0.7})
    outcome = _evaluate(_truth(), response)
    assert outcome.exact_match is False
    assert outcome.within_tolerance is True  # default tolerance = 1


def test_outside_tolerance() -> None:
    response = _response(grading={"score": 1, "maxScore": 5, "confidence": 0.7})
    outcome = _evaluate(_truth(), response)
    assert outcome.within_tolerance is False


def test_criterion_mismatch_is_counted_not_averaged_away() -> None:
    response = _response(
        criteria=[
            {"id": "c1", "result": "pass", "confidence": 0.9, "rationale": "根拠1"},
            {"id": "c2", "result": "pass", "confidence": 0.6, "rationale": "根拠2 (誤り)"},
        ]
    )
    outcome = _evaluate(_truth(), response)
    assert outcome.criterion_matches == 1
    assert outcome.criterion_total == 2


def test_schema_violation_sample_is_excluded_from_exact_match_not_scored_as_wrong() -> None:
    """A schema violation must not be silently coerced into "score 0" -- it is
    a distinct outcome (Issue #14 acceptance)."""
    with pytest.raises(ValidationError):
        parse_ai_grading_result(json.dumps({"questionId": "q1"}))

    outcome = _evaluate(_truth(), None)
    assert outcome.schema_violation is True
    assert outcome.mismatched is False
    assert outcome.exact_match is None
    assert outcome.within_tolerance is None


def test_response_to_a_different_question_is_mismatched_not_an_accidental_match() -> None:
    """Code review finding: a response answering a different question (a
    4/100 grade) must never register as matching a 4/5 truth label just
    because the raw ``score`` happens to line up on its own."""
    response = _response(
        questionId="some-other-question",
        grading={"score": 4, "maxScore": 100, "confidence": 0.8},
    )
    outcome = _evaluate(_truth(), response)
    assert outcome.mismatched is True
    assert outcome.schema_violation is False
    assert outcome.exact_match is None
    assert outcome.within_tolerance is None
    assert outcome.criterion_matches == 0
    assert outcome.criterion_total == 0


def test_response_with_wrong_max_score_is_mismatched_even_with_matching_question_id() -> None:
    """Same question id, different point scale (e.g. the provider graded
    against a stale rubric) must not be compared as if the scales agreed."""
    response = _response(grading={"score": 4, "maxScore": 10, "confidence": 0.8})
    outcome = _evaluate(_truth(), response)
    assert outcome.mismatched is True
    assert outcome.exact_match is None


def test_mismatched_sample_still_preserves_latency_and_cost() -> None:
    response = _response(questionId="other")
    outcome = _evaluate(_truth(), response, latency_seconds=2.5, cost_usd=0.001)
    assert outcome.mismatched is True
    assert outcome.latency_seconds == pytest.approx(2.5)
    assert outcome.cost_usd == pytest.approx(0.001)


def test_recognition_and_grading_confidence_stay_in_separate_columns() -> None:
    response = _response(
        recognition={"text": "答案", "confidence": 0.98},
        grading={"score": 4, "maxScore": 5, "confidence": 0.63},
    )
    outcome = _evaluate(_truth(), response, input_variant="ocr_noisy")
    assert outcome.recognition_confidence == pytest.approx(0.98)
    assert outcome.grading_confidence == pytest.approx(0.63)
    assert outcome.recognition_confidence != outcome.grading_confidence


def test_latency_defaults_to_none_not_a_fabricated_zero() -> None:
    outcome = _evaluate(_truth(), _response())
    assert outcome.latency_seconds is None


def test_latency_is_preserved_for_a_schema_violation_not_lost() -> None:
    """Code review finding: a call that took real time but returned invalid
    structured output must not have that measurement discarded."""
    outcome = _evaluate(_truth(), None, latency_seconds=3.4)
    assert outcome.schema_violation is True
    assert outcome.latency_seconds == pytest.approx(3.4)


def test_latency_and_cost_are_included_in_aggregate_even_for_schema_violations() -> None:
    """latency/cost measure the call, not the grade -- they must not be
    dropped from the aggregate just because the response was invalid."""
    outcomes = [
        _evaluate(_truth(), None, latency_seconds=9.0),
        _evaluate(_truth(), _response(), latency_seconds=1.0),
    ]
    summary = summarize_by_provider(outcomes)[0]
    assert summary.latency_p95 == pytest.approx(9.0)
    assert summary.latency_measured == 2


def test_partial_latency_measurement_is_reported_not_hidden() -> None:
    """Code review finding: a percentile computed from only some of the
    bucket's calls must not look identical to one computed from all of
    them -- the measured count must say so."""
    outcomes = [
        _evaluate(_truth(), _response(), latency_seconds=1.0),
        _evaluate(_truth(), _response(), latency_seconds=None),
        _evaluate(_truth(), _response(), cost_usd=None),
    ]
    summary = summarize_by_provider(outcomes)[0]
    assert summary.samples == 3
    assert summary.latency_measured == 1
    assert summary.cost_measured == 0


def test_bucket_with_no_scorable_sample_reports_undefined_not_zero_accuracy() -> None:
    """Code review finding: a bucket where every sample is a schema
    violation or a mismatch has no scorable response at all -- reporting
    0.0 would misleadingly read as "0% correct" rather than "nothing to
    score"."""
    outcomes = [
        _evaluate(_truth(), None),  # schema violation
        _evaluate(_truth(), _response(questionId="other")),  # mismatched
    ]
    summary = summarize_by_provider(outcomes)[0]
    assert summary.exact_match_rate is None
    assert summary.within_tolerance_rate is None


def test_same_provider_different_config_are_separate_buckets() -> None:
    """Code review finding: two recordings under the same provider name but
    different model/version/temperature/structured-output-mode settings
    must never be pooled -- averaging a passing and a failing configuration
    together could look like an overall pass."""
    passing = _evaluate(_truth(), _response(), config_key=_CONFIG)
    failing_response = _response(grading={"score": 0, "maxScore": 5, "confidence": 0.9})
    failing = _evaluate(_truth(), failing_response, config_key=_OTHER_CONFIG)
    summaries = {s.config_key: s for s in summarize_by_provider([passing, failing])}
    assert len(summaries) == 2
    assert summaries[_CONFIG].exact_match_rate == pytest.approx(1.0)
    assert summaries[_OTHER_CONFIG].exact_match_rate == pytest.approx(0.0)


def test_calibration_rates_flag_overconfident_wrong_answers() -> None:
    """docs/poc-2-ai-grading.md section 8.1: a high-confidence wrong answer
    must be distinguishable from a low-confidence wrong answer."""
    overconfident_wrong = _response(grading={"score": 0, "maxScore": 5, "confidence": 0.95})
    underconfident_right = _response(grading={"score": 4, "maxScore": 5, "confidence": 0.3})
    outcomes = [_evaluate(_truth(), overconfident_wrong), _evaluate(_truth(), underconfident_right)]
    summary = summarize_by_provider(outcomes)[0]
    assert summary.high_confidence_wrong_rate == pytest.approx(1.0)
    assert summary.low_confidence_wrong_rate == pytest.approx(0.0)


def test_calibration_rate_is_none_when_no_sample_falls_in_the_band() -> None:
    outcome = _evaluate(_truth(), _response())
    summary = summarize_by_provider([outcome])[0]
    # grading confidence 0.8 falls in neither the high (>= 0.8 -> included)
    # nor low (< 0.5) band boundary check: 0.8 is high-confidence exactly.
    assert summary.high_confidence_wrong_rate == pytest.approx(0.0)
    assert summary.low_confidence_wrong_rate is None


def test_ground_truth_rejects_score_exceeding_max_score() -> None:
    with pytest.raises(ValidationError):
        GradingGroundTruth(question_id="q", subject="s", test_id="t", score=6, max_score=5)


def test_ground_truth_rejects_negative_score() -> None:
    with pytest.raises(ValidationError):
        GradingGroundTruth(question_id="q", subject="s", test_id="t", score=-1, max_score=5)


def test_ground_truth_rejects_blank_question_id() -> None:
    with pytest.raises(ValidationError):
        GradingGroundTruth(question_id="   ", subject="s", test_id="t", score=1, max_score=5)


def test_ground_truth_rejects_duplicate_criterion_ids() -> None:
    with pytest.raises(ValidationError):
        GradingGroundTruth(
            question_id="q",
            subject="s",
            test_id="t",
            score=1,
            max_score=5,
            criteria=(
                CriterionGroundTruth(criterion_id="c1", outcome=CriterionOutcome.PASS),
                CriterionGroundTruth(criterion_id="c1", outcome=CriterionOutcome.FAIL),
            ),
        )


def test_from_mapping_does_not_truncate_a_non_integer_score() -> None:
    """Code review finding: ``int(data["score"])`` used to silently truncate
    4.9 to 4. A non-integer score in the dataset is a malformed label, not a
    rounding problem."""
    with pytest.raises(ValidationError):
        GradingGroundTruth.from_mapping(
            {"question_id": "q", "subject": "s", "test_id": "t", "score": 4.9, "max_score": 5}
        )


def test_from_mapping_does_not_stringify_a_missing_field() -> None:
    """Code review finding: ``str(data[...])`` used to turn a missing/``None``
    value into the literal string ``"None"``."""
    with pytest.raises((ValidationError, KeyError)):
        GradingGroundTruth.from_mapping(
            {"question_id": None, "subject": "s", "test_id": "t", "score": 1, "max_score": 5}
        )


def test_from_mapping_rejects_score_as_string() -> None:
    with pytest.raises(ValidationError):
        GradingGroundTruth.from_mapping(
            {"question_id": "q", "subject": "s", "test_id": "t", "score": "4", "max_score": 5}
        )


def _load_fixture_outcomes() -> list[SampleOutcome]:
    outcomes: list[SampleOutcome] = []
    for path in sorted(_FIXTURES.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        truth = GradingGroundTruth.from_mapping(raw["ground_truth"])
        for provider, variants in raw.get("recorded", {}).items():
            for variant, cell in variants.items():
                latency_raw = cell.get("latency_seconds")
                latency_seconds = float(latency_raw) if latency_raw is not None else None
                descriptor_raw = cell["descriptor"]
                descriptor = ProviderDescriptor(
                    provider=provider,
                    model=str(descriptor_raw["model"]),
                    version=descriptor_raw.get("version"),
                    temperature=float(descriptor_raw["temperature"]),
                    structured_output_mode=str(descriptor_raw["structured_output_mode"]),
                )
                config_key = descriptor_key(descriptor)
                try:
                    parsed = parse_ai_grading_result(json.dumps(cell["response"]))
                except ValidationError:
                    response = None
                else:
                    response = grading_response_from_result(
                        parsed,
                        descriptor=descriptor,
                        latency_seconds=latency_seconds if latency_seconds is not None else 0.0,
                    )
                outcomes.append(
                    evaluate_sample(
                        truth,
                        response,
                        provider=provider,
                        config_key=config_key,
                        input_variant=variant,
                        cost_usd=cell.get("cost_usd"),
                        latency_seconds=latency_seconds,
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


def test_all_fixture_cells_carry_a_config_key() -> None:
    """Every recorded cell (including the deliberate schema-violation ones)
    must have descriptor metadata, since a schema violation still needs to
    be attributed to the configuration that produced it."""
    outcomes = _load_fixture_outcomes()
    assert all(o.config_key for o in outcomes)


def test_markdown_table_renders_header_and_rows() -> None:
    table = to_markdown_table(summarize_by_provider(_load_fixture_outcomes()))
    assert table.startswith("| 教科 |")
    assert "schema違反率" in table
    assert "p95 latency(s)" in table
    assert "概算cost(USD/1000問)" in table
    assert "config" in table
    assert "計測件数" in table
