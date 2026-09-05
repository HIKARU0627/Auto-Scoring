"""`domain.test_registration.build_questions_and_rubrics` -- turning a
confirmed profile's regions into a test's real `Question`/`Rubric` rows
(Issue #16).
"""

from __future__ import annotations

import pytest

from auto_scoring.domain.profile import NormalizedBBox, Region, RegionKind
from auto_scoring.domain.test_registration import (
    CrossPageRegionError,
    DuplicateQuestionNumberError,
    IncompleteRegionsError,
    InvalidScoreError,
    QuestionNumberTooLongError,
    build_questions_and_rubrics,
)

_BBOX = NormalizedBBox(x0=0.1, y0=0.1, x1=0.5, y1=0.2)


def _region(
    kind: RegionKind, label: str, *, page_index: int = 0, text: str | None = None
) -> Region:
    return Region(
        region_id=f"{kind.value}-{label}",
        kind=kind,
        page_index=page_index,
        bbox=_BBOX,
        label=label,
        confirmed=True,
        text=text,
    )


def test_builds_one_question_from_its_regions() -> None:
    regions = [
        _region(RegionKind.QUESTION, "1", page_index=1, text="問1"),
        _region(RegionKind.ANSWER_AREA, "1", page_index=1),
        _region(RegionKind.ANNOTATION_AREA, "1", page_index=1),
        _region(RegionKind.SCORE, "1", page_index=1, text="5点"),
        _region(RegionKind.MODEL_ANSWER, "1", text="光合成は葉緑体で行われる"),
        _region(RegionKind.RUBRIC, "1", text="葉緑体という語を含む"),
    ]

    questions, rubrics = build_questions_and_rubrics("test-1", regions)

    assert len(questions) == 1
    question = questions[0]
    assert question.id == "test-1:1"
    assert question.number == "1"
    assert question.page == 2  # page_index=1 -> 1-based page 2
    assert question.points == 5
    assert question.model_answer == "光合成は葉緑体で行われる"
    assert question.answer_area is not None
    assert question.score_area is not None
    assert question.comment_area is not None

    assert len(rubrics) == 1
    rubric = rubrics[0]
    assert rubric.question_id == question.id
    assert len(rubric.criteria) == 1
    assert rubric.criteria[0].description == "葉緑体という語を含む"
    assert rubric.criteria[0].max_points == 5


def test_multiple_questions_are_grouped_independently() -> None:
    regions = [
        _region(RegionKind.QUESTION, "1", text="問1"),
        _region(RegionKind.SCORE, "1", text="3点"),
        _region(RegionKind.QUESTION, "2", text="問2"),
        _region(RegionKind.SCORE, "2", text="7点"),
    ]

    questions, _ = build_questions_and_rubrics("test-1", regions)

    by_number = {q.number: q for q in questions}
    assert set(by_number) == {"1", "2"}
    assert by_number["1"].points == 3
    assert by_number["2"].points == 7


def test_question_without_a_rubric_region_gets_no_rubric() -> None:
    regions = [
        _region(RegionKind.QUESTION, "1", text="問1"),
        _region(RegionKind.SCORE, "1", text="5点"),
    ]

    questions, rubrics = build_questions_and_rubrics("test-1", regions)

    assert len(questions) == 1
    assert rubrics == []


def test_a_label_with_no_question_region_is_ignored() -> None:
    # A stray manually-added ANSWER_AREA with no matching QUESTION heading
    # must not become a question -- only labels with a QUESTION region do.
    regions = [
        _region(RegionKind.ANSWER_AREA, "orphan"),
        _region(RegionKind.QUESTION, "1", text="問1"),
        _region(RegionKind.SCORE, "1", text="5点"),
    ]

    questions, _ = build_questions_and_rubrics("test-1", regions)

    assert [q.number for q in questions] == ["1"]


def test_duplicate_question_regions_for_the_same_number_are_rejected() -> None:
    regions = [
        _region(RegionKind.QUESTION, "1", text="問1"),
        _region(RegionKind.QUESTION, "1", text="重複した問1"),
        _region(RegionKind.SCORE, "1", text="5点"),
    ]

    with pytest.raises(DuplicateQuestionNumberError):
        build_questions_and_rubrics("test-1", regions)


def test_missing_score_region_is_rejected() -> None:
    regions = [_region(RegionKind.QUESTION, "1", text="問1")]

    with pytest.raises(InvalidScoreError):
        build_questions_and_rubrics("test-1", regions)


def test_non_numeric_score_text_is_rejected() -> None:
    regions = [
        _region(RegionKind.QUESTION, "1", text="問1"),
        _region(RegionKind.SCORE, "1", text="配点未定"),
    ]

    with pytest.raises(InvalidScoreError):
        build_questions_and_rubrics("test-1", regions)


@pytest.mark.parametrize("score_text", ["-5", "-5点", "5.5", "5.5点", "5.", "-5.5"])
def test_negative_or_decimal_score_text_is_rejected(score_text: str) -> None:
    """A bare digit search would extract a positive integer ("5") out of
    "-5" or "5.5" and let it through as if it were a valid score -- the
    non-positive check downstream never sees the sign or fraction that made
    the original value invalid.
    """
    regions = [
        _region(RegionKind.QUESTION, "1", text="問1"),
        _region(RegionKind.SCORE, "1", text=score_text),
    ]

    with pytest.raises(InvalidScoreError):
        build_questions_and_rubrics("test-1", regions)


def test_zero_score_is_rejected() -> None:
    regions = [
        _region(RegionKind.QUESTION, "1", text="問1"),
        _region(RegionKind.SCORE, "1", text="0点"),
    ]

    with pytest.raises(InvalidScoreError):
        build_questions_and_rubrics("test-1", regions)


def test_a_score_too_large_for_sqlites_integer_column_is_rejected() -> None:
    """`QuestionRow.points` is a SQLite `INTEGER` (signed 64-bit); Python's
    `int` has no such ceiling. Without this check, a score this large would
    pass every check here and only fail once `uow.questions.add()` hands it
    to the sqlite3 driver, as an unhandled `OverflowError` (500) instead of
    a normal 422 (Issue #16 review round 5).
    """
    regions = [
        _region(RegionKind.QUESTION, "1", text="問1"),
        _region(RegionKind.SCORE, "1", text="99999999999999999999点"),
    ]

    with pytest.raises(InvalidScoreError):
        build_questions_and_rubrics("test-1", regions)


def test_a_score_with_thousands_of_digits_is_rejected_as_invalid_not_a_crash() -> None:
    """A `SCORE` region text with far more digits than any legitimate score
    needs must not reach `int()` at all -- Python's own int-string
    conversion has a digit-count limit (4300 by default) and raises a bare
    `ValueError` past it, which `confirm_profile` would not translate into
    its usual 422 (Issue #16 review round 6).
    """
    regions = [
        _region(RegionKind.QUESTION, "1", text="問1"),
        _region(RegionKind.SCORE, "1", text="9" * 5000 + "点"),
    ]

    with pytest.raises(InvalidScoreError):
        build_questions_and_rubrics("test-1", regions)


def test_a_question_number_too_long_for_a_safe_filename_is_rejected() -> None:
    """`Question.id` (`f"{test_id}:{number}"`) becomes a filename component
    (hex-encoded, then wrapped in `write_atomic`'s own temp-file name) --
    an unbounded, human-editable label could push it past Windows' 255-byte
    filename-component limit, only failing much later when a submission
    with an answer area tries to finalize against an already-confirmed,
    immutable profile (Issue #16 review round 6).
    """
    long_number = "1" * 41
    regions = [
        _region(RegionKind.QUESTION, long_number, text="問1"),
        _region(RegionKind.SCORE, long_number, text="5点"),
    ]

    with pytest.raises(QuestionNumberTooLongError):
        build_questions_and_rubrics("test-1", regions)


def test_no_questions_at_all_is_rejected() -> None:
    regions = [_region(RegionKind.ANSWER_AREA, "orphan")]

    with pytest.raises(IncompleteRegionsError):
        build_questions_and_rubrics("test-1", regions)


def test_an_answer_area_on_a_different_page_than_its_question_is_rejected() -> None:
    """`Question.page` is a single page, and `answer_area` carries no page
    of its own -- `adapters.submission_intake` crops it out of exactly
    `question.page`'s rendered image. An ANSWER_AREA confirmed on a
    different page than its QUESTION would silently crop every submission
    against the wrong page's geometry (Issue #16 review round 4).
    """
    regions = [
        _region(RegionKind.QUESTION, "1", page_index=0, text="問1"),
        _region(RegionKind.ANSWER_AREA, "1", page_index=1),
        _region(RegionKind.SCORE, "1", page_index=0, text="5点"),
    ]

    with pytest.raises(CrossPageRegionError):
        build_questions_and_rubrics("test-1", regions)


def test_a_score_region_on_a_different_page_than_its_question_is_rejected() -> None:
    regions = [
        _region(RegionKind.QUESTION, "1", page_index=0, text="問1"),
        _region(RegionKind.SCORE, "1", page_index=1, text="5点"),
    ]

    with pytest.raises(CrossPageRegionError):
        build_questions_and_rubrics("test-1", regions)


def test_an_annotation_area_on_a_different_page_than_its_question_is_rejected() -> None:
    regions = [
        _region(RegionKind.QUESTION, "1", page_index=0, text="問1"),
        _region(RegionKind.SCORE, "1", page_index=0, text="5点"),
        _region(RegionKind.ANNOTATION_AREA, "1", page_index=1),
    ]

    with pytest.raises(CrossPageRegionError):
        build_questions_and_rubrics("test-1", regions)
