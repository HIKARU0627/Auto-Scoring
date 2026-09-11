"""`domain.test_registration.build_questions_and_rubrics` -- turning a
confirmed profile's regions into a test's real `Question`/`Rubric` rows
(Issue #16).
"""

from __future__ import annotations

import pytest

from auto_scoring.domain.criteria_extraction import CriteriaDraft, CriteriaQuestion
from auto_scoring.domain.models import NormalizedRect
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
    kind: RegionKind,
    label: str,
    *,
    page_index: int = 0,
    text: str | None = None,
    bbox: NormalizedBBox = _BBOX,
    region_id: str | None = None,
) -> Region:
    return Region(
        region_id=region_id or f"{kind.value}-{label}-p{page_index}",
        kind=kind,
        page_index=page_index,
        bbox=bbox,
        label=label,
        confirmed=True,
        text=text,
    )


def _rect(bbox: NormalizedBBox) -> NormalizedRect:
    return NormalizedRect(x=bbox.x0, y=bbox.y0, width=bbox.x1 - bbox.x0, height=bbox.y1 - bbox.y0)


def _draft_with_one_question() -> CriteriaDraft:
    return CriteriaDraft(test_id="test-1", questions=(CriteriaQuestion(number="1", points=5),))


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


def test_a_descriptive_score_field_selects_the_number_attached_to_ten() -> None:
    """A bare "first standalone integer" search would resolve "問1
    配点5点" to 1 (from "問1") instead of 5 (the actual score, immediately
    before "点") -- `Question.points` drives grading, so silently picking
    the wrong number is worse than rejecting an unclear field (Issue #16
    review round 8).
    """
    regions = [
        _region(RegionKind.QUESTION, "1", text="問1"),
        _region(RegionKind.SCORE, "1", text="問1 配点5点"),
    ]

    questions, _ = build_questions_and_rubrics("test-1", regions)

    assert questions[0].points == 5


def test_a_score_field_with_no_unit_and_multiple_numbers_is_rejected() -> None:
    """Without a "点" to anchor to, a field containing more than one number
    is ambiguous -- unlike a bare candidate-generated "5", it must not be
    accepted by picking whichever number happens to come first.
    """
    regions = [
        _region(RegionKind.QUESTION, "1", text="問1"),
        _region(RegionKind.SCORE, "1", text="問1 5"),
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


def test_an_answer_area_spanning_two_pages_builds_question_with_page_2_and_answer_area_2() -> None:
    """Issue #108: a question whose answer area spans 2 pages is supported."""
    regions = [
        _region(RegionKind.QUESTION, "1", page_index=0, text="問1"),
        _region(
            RegionKind.ANSWER_AREA,
            "1",
            page_index=0,
            bbox=NormalizedBBox(x0=0.1, y0=0.2, x1=0.9, y1=0.5),
        ),
        _region(
            RegionKind.ANSWER_AREA,
            "1",
            page_index=1,
            bbox=NormalizedBBox(x0=0.1, y0=0.3, x1=0.8, y1=0.6),
        ),
        _region(RegionKind.SCORE, "1", page_index=0, text="5点"),
    ]

    questions, _rubrics = build_questions_and_rubrics("test-1", regions)
    assert len(questions) == 1
    q = questions[0]
    assert q.page == 1
    assert q.page_2 == 2
    assert q.pages == (1, 2)
    assert q.answer_area == _rect(NormalizedBBox(x0=0.1, y0=0.2, x1=0.9, y1=0.5))
    assert q.answer_area_2 == _rect(NormalizedBBox(x0=0.1, y0=0.3, x1=0.8, y1=0.6))


def test_an_answer_area_spanning_three_pages_is_rejected() -> None:
    """Issue #108: answer areas spanning > 2 pages are rejected."""
    regions = [
        _region(RegionKind.QUESTION, "1", page_index=0, text="問1"),
        _region(RegionKind.ANSWER_AREA, "1", page_index=0),
        _region(RegionKind.ANSWER_AREA, "1", page_index=1),
        _region(RegionKind.ANSWER_AREA, "1", page_index=2),
        _region(RegionKind.SCORE, "1", page_index=0, text="5点"),
    ]

    with pytest.raises(CrossPageRegionError, match="span 3 pages"):
        build_questions_and_rubrics("test-1", regions)


def test_two_page_question_rejects_region_on_third_page() -> None:
    """All regions for a 2-page question must reside on one of its 2 pages."""
    regions = [
        _region(RegionKind.QUESTION, "1", page_index=0, text="問1"),
        _region(RegionKind.ANSWER_AREA, "1", page_index=0),
        _region(RegionKind.ANSWER_AREA, "1", page_index=1),
        _region(RegionKind.SCORE, "1", page_index=2, text="5点"),
    ]

    with pytest.raises(CrossPageRegionError):
        build_questions_and_rubrics("test-1", regions)


# --------------------------------------------------------------------------- #
# Issue #120/#159/#161: where the score and the comment go when nobody placed
# them -- which, since #161, is nowhere derived from the answer box at all
# --------------------------------------------------------------------------- #

_ANSWER_BBOX = NormalizedBBox(x0=0.1, y0=0.2, x1=0.9, y1=0.5)


def _new_path_regions() -> list[Region]:
    """What the #101 → #103 → #105 path actually confirms: a question and its
    answer box. Issue #103 removed `SCORE` / `RUBRIC` / `MODEL_ANSWER` from
    the screen so the 配点 has exactly one input, and `ANNOTATION_AREA` was
    never on it either -- so neither region exists on this path.
    """
    return [
        _region(RegionKind.QUESTION, "1", text="問1"),
        Region(
            region_id="answer_area-1",
            kind=RegionKind.ANSWER_AREA,
            page_index=0,
            bbox=_ANSWER_BBOX,
            label="1",
            confirmed=True,
        ),
        _region(RegionKind.SCORE, "1", text="5点"),
    ]


def test_no_annotation_region_leaves_the_comment_position_to_the_export() -> None:
    """Issue #161: `comment_area` no longer gets derived from the answer box
    either. Issue #120 derived it as the band directly below the box, and the
    live re-verification measured that band on the student's own writing for
    fourteen of sixteen answer-box questions -- the worst at 19.1% ink
    against 0.0015% for blank paper.

    Deriving nothing is what makes the fix structural rather than a
    coordinate tweak: there is no longer a code path that puts prose on the
    answer sheet, so a future caller cannot reach the same accident from
    somewhere else. The notes go to an appended note page instead
    (`domain.pdf_export.build_note_pages`).
    """
    regions = [r for r in _new_path_regions() if r.kind is not RegionKind.SCORE]

    questions, _ = build_questions_and_rubrics(
        "test-1", regions, criteria=_draft_with_one_question()
    )

    question = questions[0]
    assert question.answer_area is not None, "the answer box was still confirmed"
    assert question.comment_area is None


def test_no_score_region_leaves_the_score_position_to_the_export() -> None:
    """Issue #159: the score no longer gets a position derived from the answer
    box, because that band was measured sitting on the student's writing. It
    stays `None` here and
    `domain.pdf_export.fallback_score_areas` resolves it into the page's left
    margin at export time -- the one place on these sheets measured empty.
    """
    regions = [r for r in _new_path_regions() if r.kind is not RegionKind.SCORE]

    questions, _ = build_questions_and_rubrics(
        "test-1", regions, criteria=_draft_with_one_question()
    )

    question = questions[0]
    assert question.answer_area is not None, "the answer box was still confirmed"
    assert question.score_area is None


def test_a_hand_placed_score_region_still_wins_over_the_derived_one() -> None:
    """The pre-#101 path (a hand-written `PUT /profile` carrying `SCORE` /
    `ANNOTATION_AREA` regions) is still supported and still authoritative --
    deriving is the fallback for a question nobody placed, never an override.
    """
    regions = [*_new_path_regions(), _region(RegionKind.ANNOTATION_AREA, "1")]

    questions, _ = build_questions_and_rubrics("test-1", regions)

    question = questions[0]
    assert question.score_area == _rect(_BBOX)
    assert question.comment_area == _rect(_BBOX)


def test_a_question_with_no_answer_area_gets_no_derived_areas() -> None:
    """A question that exists only in the 採点基準 draft has no coordinates at
    all, so there is nothing to derive from -- and inventing a rect would put
    the score at a guessed spot on the page. It stays unplaceable, and
    `domain.pdf_export.unplaceable_question_ids` is what makes that visible
    before an export runs.
    """
    questions, _ = build_questions_and_rubrics(
        "test-1",
        [_region(RegionKind.QUESTION, "1", text="問1")],
        criteria=_draft_with_one_question(),
    )

    question = questions[0]
    assert question.answer_area is None
    assert question.score_area is None
    assert question.comment_area is None
