"""Schema-validation boundary tests for AI structured grading output.

These prove Issue #14's acceptance criterion directly: a malformed response
raises (``pydantic.ValidationError``) instead of being salvaged by a
free-text parse. No adapter, no network -- pure JSON in, validated model or
exception out.
"""

import json

import pytest
from pydantic import ValidationError

from auto_scoring.domain.ai_grading import (
    AIGradingResult,
    parse_ai_grading_result,
)
from auto_scoring.domain.models import MAX_COMMENT_CHARS

_VALID: dict[str, object] = {
    "questionId": "q1",
    "recognition": {"text": "光合成によって酸素が発生する", "confidence": 0.9},
    "grading": {"score": 4, "maxScore": 5, "confidence": 0.85},
    "criteria": [
        {
            "id": "c1",
            "result": "pass",
            "confidence": 0.95,
            "rationale": "反応の名称に正しく言及している。",
        }
    ],
    "comment": "理由の説明が不足しています。",
    "rationale": "criterion c1のみ充足のため4点とした。",
    "annotations": [],
}


def _parse(
    overrides: dict[str, object] | None = None, remove: list[str] | None = None
) -> AIGradingResult:
    payload = dict(_VALID)
    if overrides:
        payload.update(overrides)
    for key in remove or ():
        payload.pop(key, None)
    return parse_ai_grading_result(json.dumps(payload))


def test_valid_payload_parses() -> None:
    result = _parse()
    assert result.question_id == "q1"
    assert result.grading.score == 4
    assert result.criteria[0].result == "pass"


def test_recognition_and_grading_confidence_are_independent_fields() -> None:
    """section 10: 文字認識98% / 採点判断63% must both survive, unmixed."""
    result = _parse(
        {
            "recognition": {"text": "...", "confidence": 0.98},
            "grading": {"score": 3, "maxScore": 5, "confidence": 0.63},
        }
    )
    assert result.recognition.confidence == pytest.approx(0.98)
    assert result.grading.confidence == pytest.approx(0.63)


@pytest.mark.parametrize("missing", ["rationale", "comment", "criteria", "grading", "recognition"])
def test_missing_required_field_is_rejected(missing: str) -> None:
    with pytest.raises(ValidationError):
        _parse(remove=[missing])


def test_empty_criteria_list_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse({"criteria": []})


def test_score_exceeding_max_score_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse({"grading": {"score": 6, "maxScore": 5, "confidence": 0.5}})


def test_confidence_out_of_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse({"grading": {"score": 4, "maxScore": 5, "confidence": 1.2}})


def test_empty_rationale_is_rejected() -> None:
    """根拠 (rationale) is required non-empty, per Issue #14 acceptance."""
    with pytest.raises(ValidationError):
        _parse({"rationale": ""})


def test_comment_over_character_cap_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse({"comment": "あ" * (MAX_COMMENT_CHARS + 1)})


def test_unknown_extra_field_is_rejected_not_ignored() -> None:
    """extra='forbid': a provider adding a stray field must fail loudly, not
    be silently dropped -- a dropped field could hide a real schema drift."""
    with pytest.raises(ValidationError):
        _parse({"explanation": "unexpected extra field"})


def test_duplicate_criterion_ids_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse(
            {
                "criteria": [
                    {"id": "c1", "result": "pass", "confidence": 0.9, "rationale": "a"},
                    {"id": "c1", "result": "fail", "confidence": 0.5, "rationale": "b"},
                ]
            }
        )


def test_annotation_never_carries_coordinates() -> None:
    """section 12.1: AI returns target + type (+ optional comment), never x/y/rect."""
    result = _parse(
        {"annotations": [{"target": "行く", "type": "correction", "comment": "過去形"}]}
    )
    assert result.annotations[0].target == "行く"
    with pytest.raises(ValidationError):
        _parse({"annotations": [{"target": "行く", "type": "correction", "x": 0.1, "y": 0.2}]})


def test_malformed_json_is_a_validation_error_not_a_silent_default() -> None:
    with pytest.raises(ValidationError):
        parse_ai_grading_result("{not valid json")
