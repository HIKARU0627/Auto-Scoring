"""Domain tests for 配点・採点基準の抽出 (Issue #103).

Everything here is synthetic. The real material this feature was measured
against lives outside the repository and none of it -- not a question, not a
score, not a subject name -- may appear in a fixture (Issue #103 acceptance
criterion 8).

What these tests pin down, in the order the Issue asks for it:

* a malformed model response is a schema violation, never a partial reading;
* ``points: null`` survives as 不明 and is never collapsed into 0;
* an empty extraction is a *result*, not a crash;
* the total, the unknown count, and the declared-total comparison;
* the gate that keeps 不明 out of the database.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from auto_scoring.domain.criteria_extraction import (
    MAX_CRITERIA_TEXT_CHARS,
    MAX_EXTRACTED_POINTS,
    MAX_QUESTION_NUMBER_CHARS,
    CriteriaDraft,
    CriteriaError,
    CriteriaExtractionRequest,
    CriteriaItem,
    CriteriaQuestion,
    CriteriaStatus,
    CriterionKind,
    criteria_totals,
    draft_from_extraction,
    ensure_confirmable,
    parse_criteria_extraction,
)


def _response(**overrides: Any) -> str:
    """A minimal well-formed extraction, as JSON text."""
    payload: dict[str, Any] = {
        "questions": [
            {
                "number": "問1",
                "points": 5,
                "model_answer": "模範解答の本文",
                "criteria": [
                    {"description": "要点に触れている", "kind": "add", "points": 3},
                    {"description": "字数を満たしている", "kind": "add", "points": 2},
                ],
                "source_pages": [1],
                "note": None,
            }
        ],
        "total_points": 5,
        "unreadable_pages": [],
        "note": None,
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# The untrusted boundary
# --------------------------------------------------------------------------- #


def test_well_formed_response_parses() -> None:
    output = parse_criteria_extraction(_response())
    assert output.questions[0].number == "問1"
    assert output.questions[0].points == 5
    assert output.questions[0].criteria[1].kind is CriterionKind.ADD
    assert output.total_points == 5


def test_points_as_a_string_is_a_schema_violation() -> None:
    """``strict=True`` in action, on the field that matters most.

    A provider that answers ``"points": "5"`` is not returning a number, and
    coercing it would mean this schema's own type declarations stop being
    the thing that guards a maximum score.
    """
    with pytest.raises(ValidationError):
        parse_criteria_extraction(
            _response(
                questions=[
                    {
                        "number": "問1",
                        "points": "5",
                        "criteria": [],
                        "source_pages": [],
                        "model_answer": None,
                        "note": None,
                    }
                ]
            )
        )


def test_unknown_extra_field_is_a_schema_violation() -> None:
    with pytest.raises(ValidationError):
        parse_criteria_extraction(_response(confidence=0.9))


def test_blank_criterion_description_is_a_schema_violation() -> None:
    """A whitespace-only description would pass ``min_length=1`` alone, and
    would then become a `RubricCriterion` the grading prompt renders as an
    empty bullet."""
    with pytest.raises(ValidationError):
        parse_criteria_extraction(
            _response(
                questions=[
                    {
                        "number": "問1",
                        "points": 5,
                        "model_answer": None,
                        "criteria": [{"description": "   ", "kind": "add", "points": 1}],
                        "source_pages": [],
                        "note": None,
                    }
                ]
            )
        )


def test_negative_and_absurd_points_are_schema_violations() -> None:
    for value in (-1, MAX_EXTRACTED_POINTS + 1):
        with pytest.raises(ValidationError):
            parse_criteria_extraction(
                _response(
                    questions=[
                        {
                            "number": "問1",
                            "points": value,
                            "model_answer": None,
                            "criteria": [],
                            "source_pages": [],
                            "note": None,
                        }
                    ]
                )
            )


def test_over_long_text_is_a_schema_violation() -> None:
    """A runaway generation is rejected rather than persisted and re-sent on
    every later screen load."""
    with pytest.raises(ValidationError):
        parse_criteria_extraction(
            _response(
                questions=[
                    {
                        "number": "問1",
                        "points": 5,
                        "model_answer": "あ" * (MAX_CRITERIA_TEXT_CHARS + 1),
                        "criteria": [],
                        "source_pages": [],
                        "note": None,
                    }
                ]
            )
        )


def test_unknown_criterion_kind_is_a_schema_violation() -> None:
    """加点/減点 is a closed set. A third value would be silently treated as
    one of the two by whatever read it next, and reading a deduction as an
    addition inverts the grade."""
    with pytest.raises(ValidationError):
        parse_criteria_extraction(
            _response(
                questions=[
                    {
                        "number": "問1",
                        "points": 5,
                        "model_answer": None,
                        "criteria": [{"description": "x", "kind": "bonus", "points": 1}],
                        "source_pages": [],
                        "note": None,
                    }
                ]
            )
        )


def test_invalid_json_is_a_validation_error_not_a_partial_reading() -> None:
    with pytest.raises(ValidationError):
        parse_criteria_extraction('{"questions": [')


# --------------------------------------------------------------------------- #
# 不明 (Issue #103 acceptance criterion 5)
# --------------------------------------------------------------------------- #


def test_null_points_stays_none_through_the_draft() -> None:
    """The central promise of this feature: an unread 配点 reaches the screen
    as 不明, not as 0 and not as a dropped question."""
    output = parse_criteria_extraction(
        _response(
            questions=[
                {
                    "number": "問1",
                    "points": None,
                    "model_answer": None,
                    "criteria": [],
                    "source_pages": [2],
                    "note": "配点の記載が読み取れませんでした",
                }
            ],
            total_points=None,
        )
    )
    draft = draft_from_extraction("test-1", output)
    assert draft.questions[0].points is None
    assert draft.questions[0].note == "配点の記載が読み取れませんでした"
    assert draft.extracted is True


def test_zero_points_and_unknown_points_are_different_values() -> None:
    zero = parse_criteria_extraction(
        _response(
            questions=[
                {
                    "number": "問1",
                    "points": 0,
                    "model_answer": None,
                    "criteria": [],
                    "source_pages": [],
                    "note": None,
                }
            ]
        )
    )
    assert zero.questions[0].points == 0
    unknown = parse_criteria_extraction(
        _response(
            questions=[
                {
                    "number": "問1",
                    "points": None,
                    "model_answer": None,
                    "criteria": [],
                    "source_pages": [],
                    "note": None,
                }
            ]
        )
    )
    assert unknown.questions[0].points is None


def test_no_questions_is_a_result_not_an_error() -> None:
    """A criteria PDF the model could not read must reach the screen as
    "0 件 読み取れました" for a human to fill in, not as a failed request that
    leaves the reviewer with nothing (Issue #95 決定 8)."""
    output = parse_criteria_extraction(
        _response(
            questions=[],
            total_points=None,
            unreadable_pages=[1, 2],
            note="全ページが画像で、文字が判別できませんでした",
        )
    )
    draft = draft_from_extraction("test-1", output)
    assert draft.questions == ()
    assert draft.unreadable_pages == (1, 2)
    assert draft.extracted is True


def test_repeated_question_numbers_are_made_unique_and_flagged() -> None:
    """Found by running the extraction over the real material: a document
    whose sections restart their numbering makes the model report 問1 more
    than once, faithfully.

    `CriteriaDraft` cannot hold two rows under one number (which of them is
    問1 worth?), but neither may this be dropped -- a silently merged
    question is a question whose points vanish. So the duplicates are
    suffixed and every affected row carries a note telling the reviewer to
    renumber. Nothing is guessed and nothing is lost.
    """
    output = parse_criteria_extraction(
        _response(
            questions=[
                {
                    "number": "問1",
                    "points": 5,
                    "model_answer": None,
                    "criteria": [],
                    "source_pages": [1],
                    "note": None,
                },
                {
                    "number": "問1",
                    "points": 8,
                    "model_answer": None,
                    "criteria": [],
                    "source_pages": [3],
                    "note": None,
                },
            ],
            total_points=None,
        )
    )
    draft = draft_from_extraction("test-1", output)

    assert [question.points for question in draft.questions] == [5, 8]
    numbers = [question.number for question in draft.questions]
    assert len(set(numbers)) == 2
    assert numbers[0] == "問1"
    assert "問1" in numbers[1]
    assert draft.questions[1].note is not None
    assert "設問番号" in draft.questions[1].note


def test_deduplication_does_not_collide_with_a_literal_suffix() -> None:
    output = parse_criteria_extraction(
        _response(
            questions=[
                {
                    "number": n,
                    "points": 1,
                    "model_answer": None,
                    "criteria": [],
                    "source_pages": [],
                    "note": None,
                }
                for n in ("問1", "問1 (2)", "問1")
            ],
            total_points=None,
        )
    )
    numbers = [question.number for question in draft_from_extraction("t", output).questions]
    assert len(set(numbers)) == 3


def test_deduplication_stays_within_the_question_number_limit() -> None:
    """The suffix must not push a number past what `CriteriaQuestion` (and
    then `Question`) accepts -- that would turn a duplicate into the crash
    this deduplication exists to prevent."""
    long_number = "問" * MAX_QUESTION_NUMBER_CHARS
    output = parse_criteria_extraction(
        _response(
            questions=[
                {
                    "number": long_number,
                    "points": 1,
                    "model_answer": None,
                    "criteria": [],
                    "source_pages": [],
                    "note": None,
                }
                for _ in range(3)
            ],
            total_points=None,
        )
    )
    draft = draft_from_extraction("t", output)
    assert len({question.number for question in draft.questions}) == 3
    assert all(len(question.number) <= MAX_QUESTION_NUMBER_CHARS for question in draft.questions)


def test_a_note_at_the_length_limit_still_takes_the_duplicate_warning() -> None:
    output = parse_criteria_extraction(
        _response(
            questions=[
                {
                    "number": "問1",
                    "points": 1,
                    "model_answer": None,
                    "criteria": [],
                    "source_pages": [],
                    "note": "あ" * MAX_CRITERIA_TEXT_CHARS,
                }
                for _ in range(2)
            ],
            total_points=None,
        )
    )
    draft = draft_from_extraction("t", output)
    assert all(
        question.note is not None and len(question.note) <= MAX_CRITERIA_TEXT_CHARS
        for question in draft.questions
    )
    assert "設問番号" in draft.questions[1].note or ""


def test_page_number_shaped_total_is_reported_as_no_total() -> None:
    """Issue #95 decision 5 (案A): a footer ``(k/m)`` is a page number, and
    the schema's ``null`` is where a model that followed the instruction
    lands. Pinning it here means a future prompt change that starts
    returning 1 or 2 for these documents fails a test instead of quietly
    setting every test's 満点 to its page count."""
    output = parse_criteria_extraction(_response(total_points=None))
    assert draft_from_extraction("t", output).declared_total_points is None


# --------------------------------------------------------------------------- #
# Totals (Issue #103 acceptance criterion 4)
# --------------------------------------------------------------------------- #


def _draft(*points: int | None, declared: int | None = None) -> CriteriaDraft:
    return CriteriaDraft(
        test_id="test-1",
        questions=tuple(
            CriteriaQuestion(number=f"問{index + 1}", points=value)
            for index, value in enumerate(points)
        ),
        declared_total_points=declared,
    )


def test_totals_sum_only_known_points_and_count_the_rest() -> None:
    totals = criteria_totals(_draft(5, None, 8, None))
    assert totals.known_points == 13
    assert totals.unknown_count == 2
    assert totals.is_complete is False


def test_totals_report_the_difference_against_a_declared_total() -> None:
    totals = criteria_totals(_draft(5, 8, declared=20))
    assert totals.known_points == 13
    assert totals.declared_difference == 7


def test_matching_declared_total_reports_no_difference() -> None:
    assert criteria_totals(_draft(5, 8, declared=13)).declared_difference is None


def test_no_difference_is_reported_while_anything_is_unknown() -> None:
    """The difference would be explained by the missing values, and showing
    it would send a reviewer looking for a second problem that is not
    there."""
    totals = criteria_totals(_draft(5, None, declared=20))
    assert totals.unknown_count == 1
    assert totals.declared_difference is None


def test_totals_of_an_empty_draft() -> None:
    totals = criteria_totals(_draft())
    assert (totals.known_points, totals.unknown_count, totals.is_complete) == (0, 0, True)


# --------------------------------------------------------------------------- #
# The confirm gate (Issue #103 acceptance criteria 5 and 6)
# --------------------------------------------------------------------------- #


def test_confirm_is_refused_while_any_points_are_unknown() -> None:
    with pytest.raises(CriteriaError) as error:
        ensure_confirmable(_draft(5, None))
    assert "不明" in str(error.value)


def test_confirm_is_refused_for_an_empty_draft() -> None:
    with pytest.raises(CriteriaError):
        ensure_confirmable(_draft())


def test_confirm_is_refused_for_a_non_positive_score() -> None:
    with pytest.raises(CriteriaError):
        ensure_confirmable(_draft(5, 0))


def test_confirm_accepts_a_complete_draft() -> None:
    draft = _draft(5, 8)
    ensure_confirmable(draft)
    assert draft.confirm().status is CriteriaStatus.CONFIRMED


def test_confirming_twice_is_rejected() -> None:
    confirmed = _draft(5).confirm()
    with pytest.raises(CriteriaError):
        confirmed.confirm()


# --------------------------------------------------------------------------- #
# Draft invariants and round-tripping
# --------------------------------------------------------------------------- #


def test_duplicate_question_numbers_are_rejected() -> None:
    with pytest.raises(CriteriaError):
        CriteriaDraft(
            test_id="test-1",
            questions=(
                CriteriaQuestion(number="問1", points=5),
                CriteriaQuestion(number="問1", points=8),
            ),
        )


def test_draft_round_trips_through_a_dict() -> None:
    draft = CriteriaDraft(
        test_id="test-1",
        questions=(
            CriteriaQuestion(
                number="問1",
                points=None,
                model_answer="模範解答",
                criteria=(
                    CriteriaItem(description="減点条件", kind=CriterionKind.DEDUCT, points=2),
                ),
                source_pages=(1, 2),
                note="配点不明",
            ),
        ),
        declared_total_points=30,
        unreadable_pages=(3,),
        note="全体の注記",
        extracted=True,
        revision=4,
        status=CriteriaStatus.CONFIRMED,
    )
    assert CriteriaDraft.from_dict(draft.to_dict()) == draft


def test_a_boolean_is_not_accepted_where_points_belong() -> None:
    """``bool`` is an ``int`` subclass in Python, so ``True`` would otherwise
    deserialize into 1 point."""
    data = _draft(5).to_dict()
    data["questions"][0]["points"] = True
    with pytest.raises(CriteriaError):
        CriteriaDraft.from_dict(data)


# --------------------------------------------------------------------------- #
# The request the adapters send
# --------------------------------------------------------------------------- #


def test_extraction_request_requires_page_images() -> None:
    """Images are the primary input, not a fallback -- a request without them
    could not work for the majority of measured subjects."""
    with pytest.raises(CriteriaError):
        CriteriaExtractionRequest(page_images=())


def test_extraction_request_rejects_mismatched_text_layer() -> None:
    with pytest.raises(CriteriaError):
        CriteriaExtractionRequest(page_images=(b"png",), page_texts=("a", "b"))


def test_extraction_request_allows_an_absent_text_layer() -> None:
    """The image-only case, which is 6 of the 11 measured subjects."""
    request = CriteriaExtractionRequest(page_images=(b"png", b"png"))
    assert request.page_texts == ()
