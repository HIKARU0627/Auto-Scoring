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
    GradingGroundTruth,
    GradingInputRecord,
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

_FIXTURES = Path(__file__).parent / "fixtures" / "ai_grading"

_DESCRIPTOR = ProviderDescriptor(
    provider="test",
    model="test",
    version=None,
    prompt_version="prompt-v1",
    temperature=0.0,
    structured_output_mode="json_schema",
)
_CONFIG = descriptor_key(_DESCRIPTOR)

_OTHER_DESCRIPTOR = ProviderDescriptor(
    provider="test",
    model="test",
    version=None,
    prompt_version="prompt-v1",
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
    """Build a :class:`GradingGroundTruth` through the same JSON-validation
    path (``.from_mapping``) real ``--dataset`` files go through, using the
    documented wire field names (``questionId``/``maxScore``/criteria
    ``id``/``result``) -- this model's ``populate_by_name`` is deliberately
    off (mirrors ``ai_grading.AIGradingResult``), so it cannot be constructed
    from Python-style snake_case keyword arguments at all."""
    defaults: dict[str, object] = {
        "questionId": "q1",
        "score": 4,
        "maxScore": 5,
        "criteria": [
            {"id": "c1", "result": "pass"},
            {"id": "c2", "result": "fail"},
        ],
        "source": "human",
    }
    defaults.update(overrides)
    return GradingGroundTruth.from_mapping(defaults)


def _evaluate(
    truth: GradingGroundTruth, response: GradingResponse | None, **kwargs: object
) -> SampleOutcome:
    kwargs.setdefault("subject", "subj")
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


def test_omitted_labeled_criterion_counts_as_a_mismatch_not_a_smaller_denominator() -> None:
    """Code review finding: truth has c1 and c2 labeled, but the response
    only returns c1 (correctly). The denominator must stay 2 (every labeled
    ground-truth criterion), not shrink to 1 -- otherwise a provider could
    clear the 85% criterion-agreement gate just by omitting hard criteria."""
    response = _response(
        criteria=[
            {"id": "c1", "result": "pass", "confidence": 0.9, "rationale": "根拠1"},
        ]
    )
    outcome = _evaluate(_truth(), response)
    assert outcome.criterion_total == 2
    assert outcome.criterion_matches == 1


def test_unlabeled_response_criterion_is_ignored_not_penalized() -> None:
    """A criterion id the human labeler never recorded (not in
    ``truth.criteria``) must not affect the denominator either way --
    only labeled criteria are counted."""
    response = _response(
        criteria=[
            {"id": "c1", "result": "pass", "confidence": 0.9, "rationale": "根拠1"},
            {"id": "c2", "result": "fail", "confidence": 0.6, "rationale": "根拠2"},
            {"id": "c-unlabeled", "result": "pass", "confidence": 0.9, "rationale": "根拠3"},
        ]
    )
    outcome = _evaluate(_truth(), response)
    assert outcome.criterion_total == 2
    assert outcome.criterion_matches == 2


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
    # Interpolated p95 of [1.0, 9.0]: rank = 0.95 * 1 = 0.95 -> 1.0 + 8.0*0.95 = 8.6.
    assert summary.latency_p95 == pytest.approx(8.6)
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


def test_p50_is_the_true_interpolated_median_for_an_even_sized_bucket() -> None:
    """Code review finding: nearest-rank with Python's round() (banker's
    rounding) does not compute a median -- ``[1.0, 9.0]`` must report p50 as
    the textbook median ``5.0``, not one of the two endpoints."""
    outcomes = [
        _evaluate(_truth(), _response(), latency_seconds=1.0),
        _evaluate(_truth(), _response(), latency_seconds=9.0),
    ]
    summary = summarize_by_provider(outcomes)[0]
    assert summary.latency_p50 == pytest.approx(5.0)


def test_p50_for_an_odd_sized_bucket_is_the_middle_value() -> None:
    outcomes = [_evaluate(_truth(), _response(), latency_seconds=v) for v in (1.0, 2.0, 9.0)]
    summary = summarize_by_provider(outcomes)[0]
    assert summary.latency_p50 == pytest.approx(2.0)


def test_p95_interpolates_between_the_two_highest_observations() -> None:
    outcomes = [
        _evaluate(_truth(), _response(), latency_seconds=v) for v in (1.0, 2.0, 3.0, 4.0, 10.0)
    ]
    summary = summarize_by_provider(outcomes)[0]
    # rank = 0.95 * (5 - 1) = 3.8 -> interpolate between index 3 (4.0) and
    # index 4 (10.0) with weight 0.8: 4.0 + (10.0 - 4.0) * 0.8 = 8.8
    assert summary.latency_p95 == pytest.approx(8.8)


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


def test_prompt_version_alone_changes_the_config_key() -> None:
    """Code review finding: a prompt template edit with the same model,
    version, temperature, and structured-output mode is still a different,
    non-reproducible configuration and must key a separate bucket."""
    same_everything_else = ProviderDescriptor(
        provider="test",
        model=_DESCRIPTOR.model,
        version=_DESCRIPTOR.version,
        prompt_version="prompt-v2",
        temperature=_DESCRIPTOR.temperature,
        structured_output_mode=_DESCRIPTOR.structured_output_mode,
    )
    assert descriptor_key(same_everything_else) != _CONFIG


def test_descriptor_key_does_not_collide_when_a_field_contains_the_delimiter() -> None:
    """Code review finding: a naive ``"|"``-joined key is ambiguous when a
    field value itself contains ``"|"`` -- ``model="a|b", version="c"`` and
    ``model="a", version="b|c"`` must not produce the same key."""
    first = ProviderDescriptor(
        provider="test",
        model="a|b",
        version="c",
        prompt_version="p1",
        temperature=0.0,
        structured_output_mode="json_schema",
    )
    second = ProviderDescriptor(
        provider="test",
        model="a",
        version="b|c",
        prompt_version="p1",
        temperature=0.0,
        structured_output_mode="json_schema",
    )
    assert descriptor_key(first) != descriptor_key(second)


def test_descriptor_key_is_stable_across_int_and_float_temperature() -> None:
    """Code review finding: ``ProviderDescriptor`` is a plain dataclass, so a
    directly-constructed instance is never coerced -- an adapter passing the
    Python int literal ``0`` for ``temperature`` keeps it as an ``int`` at
    runtime, while the same value loaded through ``_DescriptorInput``
    (pydantic, a ``float`` field) becomes ``0.0``. ``json.dumps`` renders
    these differently (``0`` vs ``0.0``), splitting one configuration into
    two metric buckets depending on which construction path produced it."""
    int_temperature = ProviderDescriptor(
        provider="test",
        model="m",
        version=None,
        prompt_version="p1",
        temperature=0,
        structured_output_mode="json_schema",
    )
    float_temperature = ProviderDescriptor(
        provider="test",
        model="m",
        version=None,
        prompt_version="p1",
        temperature=0.0,
        structured_output_mode="json_schema",
    )
    assert descriptor_key(int_temperature) == descriptor_key(float_temperature)


def test_descriptor_key_folds_negative_zero_temperature_to_positive_zero() -> None:
    """``-0.0 == 0.0`` in Python but the two floats serialize to different
    JSON text (``"-0.0"`` vs ``"0.0"``), which would otherwise split one
    configuration into two buckets (code review finding)."""
    negative_zero = ProviderDescriptor(
        provider="test",
        model="m",
        version=None,
        prompt_version="p1",
        temperature=-0.0,
        structured_output_mode="json_schema",
    )
    positive_zero = ProviderDescriptor(
        provider="test",
        model="m",
        version=None,
        prompt_version="p1",
        temperature=0.0,
        structured_output_mode="json_schema",
    )
    assert descriptor_key(negative_zero) == descriptor_key(positive_zero)


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
        GradingGroundTruth.from_mapping(
            {"questionId": "q", "score": 6, "maxScore": 5, "source": "human"}
        )


def test_ground_truth_rejects_negative_score() -> None:
    with pytest.raises(ValidationError):
        GradingGroundTruth.from_mapping(
            {"questionId": "q", "score": -1, "maxScore": 5, "source": "human"}
        )


def test_ground_truth_rejects_blank_question_id() -> None:
    with pytest.raises(ValidationError):
        GradingGroundTruth.from_mapping(
            {"questionId": "   ", "score": 1, "maxScore": 5, "source": "human"}
        )


def test_ground_truth_rejects_duplicate_criterion_ids() -> None:
    with pytest.raises(ValidationError):
        GradingGroundTruth.from_mapping(
            {
                "questionId": "q",
                "score": 1,
                "maxScore": 5,
                "criteria": [
                    {"id": "c1", "result": "pass"},
                    {"id": "c1", "result": "fail"},
                ],
                "source": "human",
            }
        )


def test_ground_truth_requires_source_field() -> None:
    """Code review finding: an omitted ``source`` used to be accepted (the
    field was optional and unconstrained), so a real label file with no
    provenance -- or an AI-generated response mistakenly fed in as if it
    were ground truth -- would be scored as if it were a genuine human
    label, producing a meaningless or circular agreement rate."""
    with pytest.raises(ValidationError):
        GradingGroundTruth.from_mapping({"questionId": "q", "score": 1, "maxScore": 5})


def test_ground_truth_rejects_a_non_human_source() -> None:
    with pytest.raises(ValidationError):
        GradingGroundTruth.from_mapping(
            {"questionId": "q", "score": 1, "maxScore": 5, "source": "ai"}
        )


def _input_mapping(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "prompt_text": "設問文",
        "model_answer": "模範解答",
        "rubric_text": "採点基準",
        "max_score": 5,
        "ocr_clean": "答案テキスト",
        "ocr_noisy": None,
    }
    defaults.update(overrides)
    return defaults


def test_input_record_accepts_a_blank_ocr_clean_for_an_unanswered_question() -> None:
    """Code review finding: a student can leave a question blank, and the
    correct OCR/transcribed reading of that blank answer is itself an empty
    string -- rejecting it would make one blank real answer abort validation
    for the entire dataset, since every sample is validated up front."""
    record = GradingInputRecord.from_mapping(_input_mapping(ocr_clean=""))
    assert record.ocr_clean == ""


def test_input_record_accepts_a_blank_ocr_noisy_too() -> None:
    record = GradingInputRecord.from_mapping(_input_mapping(ocr_clean="答案", ocr_noisy=""))
    assert record.ocr_noisy == ""


def test_input_record_still_rejects_a_blank_prompt_text() -> None:
    """Only the OCR fields (a legitimate "nothing was written" sentinel) are
    exempt from the non-blank check -- authored content like the question
    prompt is never legitimately blank."""
    with pytest.raises(ValidationError):
        GradingInputRecord.from_mapping(_input_mapping(prompt_text=""))


def test_ground_truth_accepts_the_documented_real_human_label_schema() -> None:
    """business-rules-and-evaluation-data.md section 6.3's per-answer label
    schema (mirrors simplified-design-specification.md section 9.2): a real
    label file must not be rejected for using the documented field names, or
    for carrying the human-label-only fields this model itself does not use
    for PoC 2 metrics (code review finding: an earlier version of this model
    invented its own snake_case fields and rejected every one of these)."""
    truth = GradingGroundTruth.from_mapping(
        {
            "questionId": "q1",
            "score": 4,
            "maxScore": 5,
            "criteria": [{"id": "c1", "result": "pass"}],
            "comment": "確定コメント",
            "annotations": [{"type": "underline", "target": "答案の一部"}],
            "handwritingQuality": "clean",
            "layoutType": "grid",
            "source": "human",
        }
    )
    assert truth.question_id == "q1"
    assert truth.comment == "確定コメント"
    assert truth.handwriting_quality == "clean"
    assert truth.layout_type == "grid"
    assert truth.source == "human"


def test_from_mapping_does_not_truncate_a_non_integer_score() -> None:
    """Code review finding: ``int(data["score"])`` used to silently truncate
    4.9 to 4. A non-integer score in the dataset is a malformed label, not a
    rounding problem."""
    with pytest.raises(ValidationError):
        GradingGroundTruth.from_mapping(
            {"questionId": "q", "score": 4.9, "maxScore": 5, "source": "human"}
        )


def test_from_mapping_does_not_stringify_a_missing_field() -> None:
    """Code review finding: ``str(data[...])`` used to turn a missing/``None``
    value into the literal string ``"None"``."""
    with pytest.raises((ValidationError, KeyError)):
        GradingGroundTruth.from_mapping(
            {"questionId": None, "score": 1, "maxScore": 5, "source": "human"}
        )


def test_from_mapping_rejects_score_as_string() -> None:
    with pytest.raises(ValidationError):
        GradingGroundTruth.from_mapping(
            {"questionId": "q", "score": "4", "maxScore": 5, "source": "human"}
        )


def _load_fixture_outcomes() -> list[SampleOutcome]:
    outcomes: list[SampleOutcome] = []
    for path in sorted(_FIXTURES.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        truth = GradingGroundTruth.from_mapping(raw["ground_truth"])
        subject = raw["subject"]
        for provider, variants in raw.get("recorded", {}).items():
            for variant, cell in variants.items():
                latency_raw = cell.get("latency_seconds")
                latency_seconds = float(latency_raw) if latency_raw is not None else None
                descriptor_raw = cell["descriptor"]
                descriptor = ProviderDescriptor(
                    provider=provider,
                    model=str(descriptor_raw["model"]),
                    version=descriptor_raw.get("version"),
                    prompt_version=str(descriptor_raw["prompt_version"]),
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
                        subject=subject,
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


def test_markdown_table_escapes_pipes_in_config_key_so_columns_stay_aligned() -> None:
    """Code review finding: whenever a ``config_key`` (or any other cell
    value) contains a literal ``|`` -- e.g. a model name that happens to
    include one -- inserted verbatim into a Markdown table row, each one
    opens extra cells and shifts every following column out of alignment."""
    descriptor_with_pipe = ProviderDescriptor(
        provider="test",
        model="model|with|pipes",
        version=None,
        prompt_version="prompt-v1",
        temperature=0.0,
        structured_output_mode="json_schema",
    )
    outcome = _evaluate(_truth(), _response(), config_key=descriptor_key(descriptor_with_pipe))
    table = to_markdown_table(summarize_by_provider([outcome]))
    header_row, _divider, data_row = table.splitlines()
    # Cells are always joined with " | " (space-pipe-space); an escaped
    # ``\|`` inside a cell's own value has no surrounding spaces, so
    # splitting on the literal delimiter still recovers the true columns.
    header_cells = header_row.strip("|").split(" | ")
    data_cells = data_row.strip("|").split(" | ")
    assert len(header_cells) == len(data_cells)
    assert "\\|" in data_row


def test_markdown_table_escapes_pipes_and_newlines_in_subject_and_provider_too() -> None:
    """Code review finding: ``subject`` and ``provider`` come straight from
    the dataset, same as ``config_key`` -- a valid subject or provider name
    containing ``|`` or a newline must not corrupt the table either, not
    just a ``config_key`` collision."""
    outcome = _evaluate(
        _truth(), _response(), subject="日本史|世界史", provider="provider\nwith\nnewlines"
    )
    table = to_markdown_table(summarize_by_provider([outcome]))
    header_row, _divider, data_row = table.splitlines()
    header_cells = header_row.strip("|").split(" | ")
    data_cells = data_row.strip("|").split(" | ")
    assert len(header_cells) == len(data_cells)
    assert "日本史\\|世界史" in data_row
    assert "provider with newlines" in data_row
