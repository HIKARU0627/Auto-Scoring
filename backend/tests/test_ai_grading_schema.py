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
    describe_schema_violation,
    parse_ai_grading_result,
)
from auto_scoring.domain.models import COMMENT_TRUNCATION_MARK, MAX_COMMENT_CHARS

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


#: The comment length a live Vertex AI run actually returned for a
#: long-answer question (Issue #121: 147 and 157 characters, against a cap
#: of 120). Used verbatim so these tests fix the behaviour at the size that
#: really occurred, not at an arbitrary cap+1.
_OVER_CAP_LENGTH = 147


def test_over_long_comment_is_truncated_not_rejected() -> None:
    """Issue #121: a comment over the cap must never cost the grade.

    The live run's failures were complete, ``finishReason: STOP`` responses
    whose score, criterion ids and question id were all correct -- discarded
    whole because one comment ran 147 characters. The response is trusted;
    only its comment is too long, so the comment is what gives.
    """
    over_long = "あ" * _OVER_CAP_LENGTH
    result = _parse({"comment": over_long})

    # The grade itself survives intact -- the whole point of the change.
    assert result.grading.score == 4
    assert result.grading.max_score == 5
    assert result.question_id == "q1"
    assert result.criteria[0].id == "c1"

    assert len(result.comment) <= MAX_COMMENT_CHARS
    assert result.comment.endswith(COMMENT_TRUNCATION_MARK)
    assert over_long.startswith(result.comment.removesuffix(COMMENT_TRUNCATION_MARK))


def test_over_long_annotation_comment_is_truncated_not_rejected() -> None:
    """The field the live run actually failed on: ``annotations.0.comment``
    (Issue #121's recorded ``loc``), not the top-level ``comment``."""
    over_long = "い" * _OVER_CAP_LENGTH
    result = _parse({"annotations": [{"target": "行く", "type": "comment", "comment": over_long}]})

    assert result.grading.score == 4
    annotation_comment = result.annotations[0].comment
    assert annotation_comment is not None
    assert len(annotation_comment) <= MAX_COMMENT_CHARS
    assert annotation_comment.endswith(COMMENT_TRUNCATION_MARK)


def test_comment_at_the_cap_is_left_exactly_as_sent() -> None:
    """Truncation must not touch a comment that already fits: a response
    ending in a real ellipsis stays distinguishable from a truncated one
    only if the mark is never added to text that did not need cutting."""
    at_cap = "う" * MAX_COMMENT_CHARS
    assert _parse({"comment": at_cap}).comment == at_cap


def test_blank_comment_is_still_rejected() -> None:
    """Truncating an over-long comment does not weaken the other end: a
    comment with nothing in it still has nothing to display."""
    for blank in ("", "   "):
        with pytest.raises(ValidationError):
            _parse({"comment": blank})


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
    result = _parse({"annotations": [{"target": "行く", "type": "underline", "comment": "過去形"}]})
    assert result.annotations[0].target == "行く"
    with pytest.raises(ValidationError):
        _parse({"annotations": [{"target": "行く", "type": "underline", "x": 0.1, "y": 0.2}]})


def test_annotation_type_outside_the_fixed_set_is_rejected() -> None:
    """business-rules-and-evaluation-data.md section 2 (5) fixes the MVP
    Annotation kinds; a provider returning an unsupported type (even
    section 12.1's own illustrative "correction") is a schema violation,
    not a value to accept and fail on later at persistence/rendering time."""
    with pytest.raises(ValidationError):
        _parse({"annotations": [{"target": "行く", "type": "correction"}]})


def test_comment_type_annotation_without_comment_text_is_rejected() -> None:
    """Code review finding: a ``type: "comment"`` annotation with no
    ``comment`` has nothing to display, and ``domain.models.Annotation``
    requires non-blank text to construct one -- reject it here, at the
    untrusted response boundary, rather than letting it crash later at
    persistence or rendering time."""
    with pytest.raises(ValidationError):
        _parse({"annotations": [{"target": "行く", "type": "comment"}]})


def test_comment_type_annotation_with_comment_text_is_accepted() -> None:
    result = _parse(
        {"annotations": [{"target": "行く", "type": "comment", "comment": "過去形に注意"}]}
    )
    assert result.annotations[0].comment == "過去形に注意"


def test_malformed_json_is_a_validation_error_not_a_silent_default() -> None:
    with pytest.raises(ValidationError):
        parse_ai_grading_result("{not valid json")


def test_score_as_string_is_not_coerced() -> None:
    """strict=True: a provider sending "score": "4" is a violation, not a 4."""
    with pytest.raises(ValidationError):
        _parse({"grading": {"score": "4", "maxScore": 5, "confidence": 0.85}})


def test_confidence_as_string_is_not_coerced() -> None:
    with pytest.raises(ValidationError):
        _parse({"grading": {"score": 4, "maxScore": 5, "confidence": "0.85"}})


def test_max_score_as_string_is_not_coerced() -> None:
    with pytest.raises(ValidationError):
        _parse({"grading": {"score": 4, "maxScore": "5", "confidence": 0.85}})


@pytest.mark.parametrize("field", ["comment", "rationale"])
def test_whitespace_only_top_level_field_is_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        _parse({field: "   　  "})


def test_whitespace_only_criterion_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse(
            {
                "criteria": [
                    {"id": "  ", "result": "pass", "confidence": 0.9, "rationale": "a"},
                ]
            }
        )


def test_whitespace_only_criterion_rationale_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse(
            {
                "criteria": [
                    {"id": "c1", "result": "pass", "confidence": 0.9, "rationale": "   "},
                ]
            }
        )


def test_whitespace_only_question_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse({"questionId": "   "})


def test_whitespace_only_annotation_target_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse({"annotations": [{"target": "  ", "type": "underline"}]})


def test_recognition_text_may_be_empty_for_an_unreadable_region() -> None:
    """Unlike comment/rationale, recognition.text is not a _NonBlankStr: an
    empty string is the legitimate sentinel for "nothing recognised"
    (mirrors domain.ocr.OcrResult, not a value to reject)."""
    result = _parse({"recognition": {"text": "", "confidence": 0.1}})
    assert result.recognition.text == ""


def test_snake_case_question_id_is_rejected_not_populated_by_name() -> None:
    """Code review finding: the documented wire contract is camelCase
    (``questionId``) only. Accepting the Python-style ``question_id`` too
    would let a non-conformant provider response pass as schema-valid,
    understating the real schema violation rate."""
    payload = dict(_VALID)
    payload["question_id"] = payload.pop("questionId")
    with pytest.raises(ValidationError):
        parse_ai_grading_result(json.dumps(payload))


def test_snake_case_max_score_is_rejected_not_populated_by_name() -> None:
    payload = dict(_VALID)
    assert isinstance(payload["grading"], dict)
    grading: dict[str, object] = dict(payload["grading"])
    grading["max_score"] = grading.pop("maxScore")
    payload["grading"] = grading
    with pytest.raises(ValidationError):
        parse_ai_grading_result(json.dumps(payload))


# --------------------------------------------------------------------------- #
# describe_schema_violation (Issue #121: which field, and why -- never a value)
# --------------------------------------------------------------------------- #


def _violation(overrides: dict[str, object] | None = None, remove: list[str] | None = None) -> str:
    with pytest.raises(ValidationError) as caught:
        _parse(overrides, remove)
    return describe_schema_violation(caught.value)


def test_violation_names_the_field_and_the_reason() -> None:
    """Issue #121: ``Job.last_error`` stopped at "[gemini SchemaViolation]",
    so identifying the cause needed the provider response captured by hand.
    The field path and pydantic's own error code are both fixed literals of
    this schema, so both can be said out loud."""
    assert _violation(remove=["rationale"]) == "rationale: missing"


def test_violation_names_a_nested_field_by_its_full_path() -> None:
    """The live failure's own ``loc``: the offending comment was inside
    ``annotations[0]``, not at the top level, and a summary that said only
    "comment" would have pointed at the wrong field."""
    summary = _violation(
        {"annotations": [{"target": "行く", "type": "underline", "comment": "  "}]}
    )
    assert summary == "annotations.0.comment: string_too_short"


@pytest.mark.parametrize(
    ("overrides", "remove", "secret"),
    [
        ({"comment": ""}, None, ""),
        ({"rationale": "生徒の答案から写した文字列"}, ["comment"], "生徒の答案から写した文字列"),
        ({"grading": {"score": 6, "maxScore": 5, "confidence": 0.5}}, None, "6"),
    ],
)
def test_violation_never_echoes_the_value_that_failed(
    overrides: dict[str, object], remove: list[str] | None, secret: str
) -> None:
    """``str(ValidationError)`` embeds each error's ``input_value``, which at
    this boundary can be OCR'd student answer text (AGENTS.md "Security").
    The summary is built from ``loc`` and ``type`` only -- never ``input``."""
    summary = _violation(overrides, remove)
    assert summary
    if secret:
        assert secret not in summary


def test_violation_hides_an_unexpected_field_s_own_name() -> None:
    """``extra_forbidden``'s ``loc`` *is* the offending key, copied verbatim
    from the provider's response -- the one path segment that is not a
    literal of this schema, so it is the one that gets replaced."""
    summary = _violation({"生徒の答案らしき文字列": "x"})
    assert "生徒の答案らしき文字列" not in summary
    assert summary.endswith("extra_forbidden")
