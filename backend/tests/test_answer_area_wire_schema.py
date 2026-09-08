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
    strict_answer_area_detection_schema,
)
from auto_scoring.domain.answer_area_detection import (
    MAX_NOTE_CHARS,
    UNASSIGNED_QUESTION_LABEL,
    AnswerAreaDetectionOutput,
    parse_answer_area_detection,
    question_number_choices,
)

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
