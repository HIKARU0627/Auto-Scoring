"""Schema tests for the structured AI grading output (簡易設計書 §9.2 / §10).

These guard the promoted contract: no consumer parses free text, unknown keys
are rejected, and Recognition vs Grading confidence stay separate.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from auto_scoring.domain.ai_grading import AIGradingResult

_SCHEMA_FILE = (
    Path(__file__).resolve().parents[2] / "docs" / "schema" / "ai-grading-result.schema.json"
)

_VALID: dict[str, Any] = {
    "questionId": "q3",
    "recognition": {"text": "光合成によって酸素が発生する", "confidence": 0.91},
    "grading": {
        "score": 4,
        "maxScore": 5,
        "confidence": 0.63,
        "rationale": "酸素発生には言及。理由の説明が不足。",
    },
    "criteria": [
        {"id": "c1", "result": "pass", "confidence": 0.97, "rationale": "酸素に言及"},
        {"id": "c2", "result": "partial", "confidence": 0.76, "rationale": "理由が不十分"},
    ],
    "comment": "理由の説明が不足しています。",
    "annotations": [],
}


def test_parses_camelcase_payload() -> None:
    result = AIGradingResult.model_validate(_VALID)
    assert result.question_id == "q3"
    assert result.grading.max_score == 5
    assert [c.result for c in result.criteria] == ["pass", "partial"]


def test_recognition_and_grading_confidence_are_independent() -> None:
    result = AIGradingResult.model_validate(_VALID)
    # 簡易設計書 §10: "文字認識 98% / 採点判断 63%" は許容される状態。
    assert result.recognition.confidence == 0.91
    assert result.grading.confidence == 0.63
    assert result.recognition.confidence != result.grading.confidence


def test_unknown_key_is_rejected() -> None:
    payload = {**_VALID, "verdict": "approve"}
    with pytest.raises(ValidationError, match="verdict"):
        AIGradingResult.model_validate(payload)


def test_score_above_max_is_rejected() -> None:
    payload = {**_VALID, "grading": {**_VALID["grading"], "score": 6}}
    with pytest.raises(ValidationError, match="score must not exceed max_score"):
        AIGradingResult.model_validate(payload)


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_confidence_out_of_range_is_rejected(bad: float) -> None:
    payload = {**_VALID, "recognition": {"text": "x", "confidence": bad}}
    with pytest.raises(ValidationError):
        AIGradingResult.model_validate(payload)


def test_empty_rationale_is_rejected() -> None:
    payload = {**_VALID, "grading": {**_VALID["grading"], "rationale": ""}}
    with pytest.raises(ValidationError):
        AIGradingResult.model_validate(payload)


def test_at_least_one_criterion_required() -> None:
    payload = {**_VALID, "criteria": []}
    with pytest.raises(ValidationError):
        AIGradingResult.model_validate(payload)


def test_comment_length_capped_at_120() -> None:
    payload = {**_VALID, "comment": "あ" * 121}
    with pytest.raises(ValidationError):
        AIGradingResult.model_validate(payload)


def test_invalid_criterion_result_is_rejected() -> None:
    payload = {
        **_VALID,
        "criteria": [{"id": "c1", "result": "maybe", "confidence": 0.5, "rationale": "x"}],
    }
    with pytest.raises(ValidationError):
        AIGradingResult.model_validate(payload)


def test_result_is_frozen() -> None:
    result = AIGradingResult.model_validate(_VALID)
    with pytest.raises(ValidationError):
        result.comment = "changed"


def test_committed_json_schema_matches_model() -> None:
    """``docs/schema/ai-grading-result.schema.json`` is the data-less label schema
    (業務ルール §6.3 / §6.7). Regenerate it when the model changes:

        uv run python -m auto_scoring.domain.ai_grading  # see module __main__
    """
    committed = json.loads(_SCHEMA_FILE.read_text(encoding="utf-8"))
    assert committed == AIGradingResult.model_json_schema()
