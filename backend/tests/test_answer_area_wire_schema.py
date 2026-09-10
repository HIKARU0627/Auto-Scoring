"""The JSON Schema the detection adapters put on the wire (Issue #105).

Separate from `test_answer_area_detection.py` because it is about
``adapters.answer_area_detection._prompt``, not the domain: the domain decides
what an answer is allowed to say, this decides how the model is asked.

Two things are pinned together here on purpose -- the enum the model is
offered, and the set a response is validated against. They are built from one
helper (`question_number_choices`), and a change that lets them drift makes
the multiple-choice attribution meaningless while every other test still
passes.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from auto_scoring.adapters.answer_area_detection._prompt import (
    ANSWER_AREA_SYSTEM_INSTRUCTIONS,
    build_answer_area_user_content,
    strict_answer_area_detection_schema,
)
from auto_scoring.domain.answer_area_detection import (
    MAX_NOTE_CHARS,
    UNASSIGNED_QUESTION_LABEL,
    AnswerAreaDetectionError,
    AnswerAreaDetectionOutput,
    AnswerAreaDetectionRequest,
    parse_answer_area_detection,
    question_number_choices,
)
from auto_scoring.domain.answer_area_snapping import PageRuling
from auto_scoring.domain.profile import NormalizedBBox

_NUMBERS = ("Q1", "Q2", "Q3")


def _area(
    *,
    page: int = 1,
    number: str = "Q1",
    bbox: tuple[float, float, float, float] = (0.1, 0.2, 0.6, 0.4),
    note: str | None = None,
) -> dict[str, object]:
    x0, y0, x1, y1 = bbox
    return {
        "page": page,
        "question_number": number,
        "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        "note": note,
    }


def _parse(areas: list[dict[str, object]], *, page_count: int = 2) -> AnswerAreaDetectionOutput:
    return parse_answer_area_detection(
        json.dumps({"areas": areas}), question_numbers=_NUMBERS, page_count=page_count
    )


class TestWireSchema:
    def test_question_number_is_an_enum_of_this_tests_questions(self) -> None:
        schema = strict_answer_area_detection_schema(_NUMBERS)
        assert _question_number_node(schema)["enum"] == question_number_choices(_NUMBERS)

    def test_the_enum_matches_what_the_parser_accepts(self) -> None:
        """The one invariant tying the two halves together: the model is
        offered exactly the values a response is later checked against.
        """
        schema = strict_answer_area_detection_schema(_NUMBERS)
        choices = _question_number_node(schema)["enum"]
        assert isinstance(choices, list)
        for choice in choices:
            _parse([_area(number=str(choice))])

    def test_value_constraints_are_stripped_from_the_wire_schema(self) -> None:
        """Vertex AI compiles ``responseJsonSchema`` into a decoding constraint
        and answered 400 INVALID_ARGUMENT for all 11 measured subjects in Issue
        #103 when numeric bounds and length limits made it too large.

        A future change that re-adds one has to fail here rather than in front
        of a reviewer pressing 自動検出.
        """
        blocked = {
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "minLength",
            "maxLength",
            "minItems",
            "maxItems",
            "pattern",
            "format",
        }
        assert _keywords(strict_answer_area_detection_schema(_NUMBERS)) & blocked == set()

    def test_the_dropped_bounds_are_still_enforced_locally(self) -> None:
        """Dropping them from the wire costs nothing only because this is
        true. Asserted next to the stripping test so the two can never be
        changed independently.
        """
        with pytest.raises(ValidationError):
            _parse([_area(bbox=(0.1, 0.2, 1.5, 0.4))])
        with pytest.raises(ValidationError):
            _parse([_area(note="あ" * (MAX_NOTE_CHARS + 1))])

    def test_every_object_lists_all_properties_as_required(self) -> None:
        """Strict Structured Outputs and Vertex's ``responseJsonSchema`` both
        reject optionality expressed as an absent key plus a ``default``.
        """
        for node in _objects(strict_answer_area_detection_schema(_NUMBERS)):
            required, properties = node["required"], node["properties"]
            assert isinstance(required, list)
            assert isinstance(properties, dict)
            assert set(required) == set(properties)
            assert node["additionalProperties"] is False

    def test_the_instructions_offer_the_unassigned_choice(self) -> None:
        """The whole design rests on the model using it instead of picking a
        plausible question number, so it is named in words as well as in the
        enum.
        """
        assert UNASSIGNED_QUESTION_LABEL in ANSWER_AREA_SYSTEM_INSTRUCTIONS


class TestMeasuredRulingInThePrompt:
    """Issue #122: the model is handed the page's real printed lines.

    Measured, it does not locate a thin ruled column -- it returns a
    stereotyped one (see `domain.answer_area_snapping`). Listing the lines
    turns the coordinate into the same kind of multiple choice the question
    number already is.
    """

    def test_the_measured_lines_are_listed_for_the_model_to_copy(self) -> None:
        content = build_answer_area_user_content(
            AnswerAreaDetectionRequest(
                page_images=(b"png",),
                question_numbers=_NUMBERS,
                page_rulings=(PageRuling(vertical=(0.6671, 0.7158), horizontal=(0.25,)),),
            )
        )

        assert "0.6671" in content
        assert "0.7158" in content
        assert "0.2500" in content

    def test_a_page_without_ruling_is_listed_as_having_none(self) -> None:
        """Left out entirely, "this page has no printed lines" would read as
        an oversight the model might try to compensate for."""
        content = build_answer_area_user_content(
            AnswerAreaDetectionRequest(
                page_images=(b"png", b"png"),
                question_numbers=_NUMBERS,
                page_rulings=(PageRuling(vertical=(0.5,)), PageRuling()),
            )
        )

        assert "Page 2" in content
        assert "(none)" in content

    def test_nothing_is_said_when_the_caller_measured_nothing(self) -> None:
        content = build_answer_area_user_content(
            AnswerAreaDetectionRequest(page_images=(b"png",), question_numbers=_NUMBERS)
        )

        assert "Measured ruling" not in content

    def test_the_instructions_tell_the_model_to_copy_the_values(self) -> None:
        """The list is useless without the rule that says what to do with it.
        Same belt-and-braces the question-number enum gets: stated once where
        it can be read, once where it can be enforced (the snap in
        `domain.answer_area_detection.regions_from_detection`).
        """
        assert "Measured ruling" not in ANSWER_AREA_SYSTEM_INSTRUCTIONS
        assert "measured ruling" in ANSWER_AREA_SYSTEM_INSTRUCTIONS
        assert "copied exactly" in ANSWER_AREA_SYSTEM_INSTRUCTIONS


def _question_number_node(schema: dict[str, object]) -> dict[str, object]:
    for node in _objects(schema):
        properties = node["properties"]
        assert isinstance(properties, dict)
        if "question_number" in properties:
            found = properties["question_number"]
            assert isinstance(found, dict)
            return found
    raise AssertionError("the schema has no question_number property")


def _objects(node: object) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    if isinstance(node, dict):
        if node.get("type") == "object" and isinstance(node.get("properties"), dict):
            found.append(node)
        for value in node.values():
            found.extend(_objects(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_objects(item))
    return found


def _keywords(node: object) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        found.update(node.keys())
        for value in node.values():
            found |= _keywords(value)
    elif isinstance(node, list):
        for item in node:
            found |= _keywords(item)
    return found


class TestMeasuredBoxesInThePrompt:
    """Issue #164's first half, in the prompt.

    The pattern is the one this module already documents for the question
    number and for the ruling: state it where it can be read, enforce it
    where it can be enforced. What is new is that offering *both* lists at
    once measurably makes the answer worse, which is why the ruling section
    now stands aside.
    """

    def _request(
        self,
        *,
        pages: int = 1,
        boxes: tuple[tuple[NormalizedBBox, ...], ...] = (),
        rulings: tuple[PageRuling, ...] = (),
    ) -> AnswerAreaDetectionRequest:
        return AnswerAreaDetectionRequest(
            page_images=tuple(b"png" for _ in range(pages)),
            question_numbers=_NUMBERS,
            page_boxes=boxes,
            page_rulings=rulings,
        )

    def test_the_measured_boxes_are_listed_with_their_indexes(self) -> None:
        content = build_answer_area_user_content(
            self._request(boxes=((NormalizedBBox(x0=0.81, y0=0.25, x1=0.86, y1=0.48),),))
        )

        assert "box 0" in content
        assert "0.8100" in content

    def test_a_page_with_no_measured_box_is_listed_as_such(self) -> None:
        """Left out, "this page has no printed box" would read as an
        oversight -- the same reason the ruling section lists an unruled
        page."""
        content = build_answer_area_user_content(
            self._request(
                pages=2,
                boxes=((NormalizedBBox(x0=0.1, y0=0.2, x1=0.3, y1=0.4),), ()),
            )
        )

        assert "no printed box measured" in content

    def test_the_ruling_stands_aside_for_a_page_whose_boxes_were_measured(self) -> None:
        """Measured, and the reason this is not just tidiness: with both
        lists in front of it the model went back to assembling a rectangle
        out of line numbers -- on one subject it answered with a rectangle
        covering the blank half of the page for a question whose box was in
        the list it had just been given. Three runs of the real material
        with the ruling withheld put that subject's boxes exactly on the
        printed ones every time.
        """
        content = build_answer_area_user_content(
            self._request(
                boxes=((NormalizedBBox(x0=0.1, y0=0.2, x1=0.3, y1=0.4),),),
                rulings=(PageRuling(vertical=(0.5,), horizontal=(0.5,)),),
            )
        )

        assert "Measured ruling" not in content

    def test_the_ruling_is_still_offered_for_a_page_with_no_measured_box(self) -> None:
        """One measured subject's answer space is an open region under
        「考え方・計算過程」 with no printed border anywhere. Nothing can be
        chosen for it, so Issue #122's repair is all there is."""
        content = build_answer_area_user_content(
            self._request(
                pages=2,
                boxes=((NormalizedBBox(x0=0.1, y0=0.2, x1=0.3, y1=0.4),), ()),
                rulings=(PageRuling(vertical=(0.5,)), PageRuling(vertical=(0.7,))),
            )
        )

        assert "Measured ruling" in content
        assert "Page 2 vertical lines" in content
        assert "Page 1 vertical lines" not in content

    def test_the_instructions_tell_the_model_to_choose_rather_than_estimate(self) -> None:
        assert "measured" in ANSWER_AREA_SYSTEM_INSTRUCTIONS
        assert "box_indexes" in ANSWER_AREA_SYSTEM_INSTRUCTIONS
        assert "questions_not_on_these_pages" in ANSWER_AREA_SYSTEM_INSTRUCTIONS

    def test_a_box_list_that_does_not_cover_every_page_is_refused(self) -> None:
        """An index is positional and per page. Resolved against the wrong
        page's list it produces a perfectly plausible rectangle on the wrong
        part of the paper -- silently."""
        with pytest.raises(AnswerAreaDetectionError):
            AnswerAreaDetectionRequest(
                page_images=(b"png", b"png"),
                question_numbers=_NUMBERS,
                page_boxes=((NormalizedBBox(x0=0.1, y0=0.2, x1=0.3, y1=0.4),),),
            )
