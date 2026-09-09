"""The grading call must never ask a model to transcribe an identifier
(Issue #117).

Found on real material against real Vertex AI, not in any test: a rubric
criterion's registered id is ``f"{test_id}:{number}:rubric:c{n}"`` with a
32-hex-character ``test_id`` -- 45 characters -- and the prompt asked the
model to write it back verbatim. It came back with one character duplicated,
4 times out of 4; the same questions with short ids never mismatched. The
grading job then failed `PERMANENT` on
``response_criterion_ids != rubric_criterion_ids``.

Structured output does not help: a JSON Schema constrains the *shape* of a
response, never that a string inside that shape is an accurate copy of an
input. So the fix is not a shorter id -- a shorter id is still transcription,
just with better odds. The model is asked to *choose a number*, and this
module pins that property from the outside:

* nothing that must round-trip appears in the text sent to the model
  (:func:`test_no_registered_identifier_is_sent_for_the_model_to_echo`), and
* the identifiers come back as a bounded choice, not free text
  (:func:`test_criterion_choice_is_an_enum_of_the_rubric_positions`).

These are written against the *property*, not against a particular length or
a particular field name: any future change that reintroduces "write this
string back to me" fails here regardless of how long the string is.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from auto_scoring.adapters.ai_grading._prompt import build_grading_user_content
from auto_scoring.adapters.ai_grading._schema import strict_ai_grading_result_schema
from auto_scoring.domain.ai_grading import parse_ai_grading_result
from auto_scoring.domain.ai_provider import (
    GradingRequest,
    ProviderDescriptor,
    SchemaViolation,
    grading_response_from_result,
)
from auto_scoring.domain.models import RubricCriterion, ScoringMethod
from auto_scoring.jobs.grading_processor import build_rubric_prompt

#: A test id shaped exactly like a real one (`adapters.test_intake` uses
#: ``uuid4().hex``), so the ids below are the real 34/45-character values --
#: the very lengths the live run failed on.
_TEST_ID = uuid4().hex
#: ``:12`` rather than ``:1`` only so the criterion ids below come out at
#: exactly the 45 characters the live run measured, rather than 44.
_QUESTION_ID = f"{_TEST_ID}:12"
_CRITERION_IDS = tuple(f"{_QUESTION_ID}:rubric:c{n}" for n in range(1, 5))

_CRITERIA = tuple(
    RubricCriterion(id=criterion_id, description=f"観点{n}", max_points=5, position=n - 1)
    for n, criterion_id in enumerate(_CRITERION_IDS, start=1)
)


def _request() -> GradingRequest:
    rubric_text, criterion_ids = build_rubric_prompt(ScoringMethod.ADDITIVE, _CRITERIA)
    return GradingRequest(
        question_id=_QUESTION_ID,
        prompt_text="設問文",
        answer_image=b"\x89PNG\r\n\x1a\n",
        ocr_text="答案テキスト",
        model_answer="模範解答",
        rubric_text=rubric_text,
        criterion_ids=criterion_ids,
        max_score=20,
    )


def test_the_ids_under_test_are_the_lengths_that_actually_failed() -> None:
    """Guards the guard: if id construction is ever shortened, this module
    must not quietly start proving the property on 5-character strings."""
    assert len(_QUESTION_ID) >= 34
    assert all(len(criterion_id) == 45 for criterion_id in _CRITERION_IDS)


def test_no_registered_identifier_is_sent_for_the_model_to_echo() -> None:
    """Neither the question id nor any criterion id reaches the model.

    An identifier the model never sees is an identifier it cannot
    mis-transcribe. This is the whole fix: it is stated as "absent from the
    prompt", not as "shorter than N characters", because shortening only
    lowers the odds.
    """
    request = _request()
    content = build_grading_user_content(request)
    assert request.question_id not in content
    for criterion_id in request.criterion_ids:
        assert criterion_id not in content
    # The rubric text itself is what carries the criteria into the prompt --
    # so the same check has to hold there, or the assertion above would pass
    # only because the ids happened not to be interpolated twice.
    assert request.question_id not in request.rubric_text
    for criterion_id in request.criterion_ids:
        assert criterion_id not in request.rubric_text


def test_rubric_prompt_numbers_the_criteria_in_registered_order() -> None:
    """The positions the model chooses between are 1..N over the rubric's own
    ``position`` order -- the same order ``criterion_ids`` is returned in, so
    a choice can be mapped back without the model naming anything."""
    rubric_text, criterion_ids = build_rubric_prompt(ScoringMethod.ADDITIVE, _CRITERIA)
    assert criterion_ids == _CRITERION_IDS
    for position, criterion in enumerate(_CRITERIA, start=1):
        assert f"{position}. {criterion.description}" in rubric_text


def test_criterion_choice_is_an_enum_of_the_rubric_positions() -> None:
    """The response schema fixes the candidate set (Issue #101's "ask it as a
    multiple-choice question, not as free text"), and fixes how many answers
    there must be -- so a provider that does enforce the schema cannot even
    emit an out-of-range or short ``criteria`` list."""
    schema = strict_ai_grading_result_schema(criterion_count=4)
    criteria = schema["properties"]["criteria"]
    assert criteria["minItems"] == 4
    assert criteria["maxItems"] == 4
    item = _resolve(schema, criteria["items"])
    properties = item["properties"]
    assert isinstance(properties, dict)
    assert properties["index"]["enum"] == [1, 2, 3, 4]


def test_response_schema_declares_no_question_identifier() -> None:
    """One call grades one question; echoing its id back proves nothing and
    was the second place a 34-character string had to be copied."""
    schema = strict_ai_grading_result_schema(criterion_count=1)
    assert "questionId" not in schema["properties"]


@pytest.mark.parametrize("criterion_count", [0, -1])
def test_schema_refuses_a_rubric_with_no_criteria(criterion_count: int) -> None:
    """A question with no registered criterion never reaches a provider
    (`GradingJobProcessor.process` fails it as a setup problem first), so an
    empty candidate set here would be a bug, not an input to tolerate."""
    with pytest.raises(ValueError):
        strict_ai_grading_result_schema(criterion_count=criterion_count)


def _resolve(schema: dict[str, object], node: dict[str, object]) -> dict[str, object]:
    """Follow a local ``$ref`` into the schema's own ``$defs``."""
    ref = node.get("$ref")
    if not isinstance(ref, str):
        return node
    defs = schema["$defs"]
    assert isinstance(defs, dict)
    resolved = defs[ref.rsplit("/", 1)[-1]]
    assert isinstance(resolved, dict)
    return resolved


def test_an_out_of_range_position_is_refused_with_a_field_level_diagnosis() -> None:
    """The one failure the ``index`` design can still produce, and it has to
    be as diagnosable as every other schema violation (Issue #121).

    A provider that ignores the ``enum`` and answers ``5`` for a four-criterion
    rubric cannot be mapped back onto the rubric, so nothing is scored --
    but ``Job.last_error`` must say *which field* and *why*, not just
    "SchemaViolation". The detail is a field path and a reason code, both
    built from this project's own literals and an integer: no provider-written
    value can ride along (Issue #97 round 4's rule).
    """
    raw = json.dumps(
        {
            "recognition": {"text": "答案", "confidence": 0.9},
            "grading": {"score": 4, "maxScore": 20, "confidence": 0.8},
            "criteria": [
                {"index": 5, "result": "pass", "confidence": 0.9, "rationale": "根拠"},
            ],
            "comment": "コメント",
            "rationale": "全体根拠",
            "annotations": [],
        }
    )
    descriptor = ProviderDescriptor(
        provider="test",
        model="test",
        version=None,
        prompt_version="v1",
        temperature=0.0,
        structured_output_mode="json_schema",
    )

    with pytest.raises(SchemaViolation) as caught:
        grading_response_from_result(
            parse_ai_grading_result(raw),
            question_id=_QUESTION_ID,
            criterion_ids=_CRITERION_IDS,
            descriptor=descriptor,
            latency_seconds=0.0,
        )

    assert caught.value.detail == "criteria.0.index: out_of_range"
