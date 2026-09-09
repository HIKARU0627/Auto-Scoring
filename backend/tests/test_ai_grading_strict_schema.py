"""Tests for the strict-mode JSON Schema shared by every ``AIProvider``
adapter that requests OpenAI-style Structured Outputs (Issue #44 code
review finding: an OpenAI-compatible strict backend rejects Pydantic's own
``model_json_schema()`` output outright, since a field with a default is
missing from that object's ``required`` array)."""

from __future__ import annotations

from typing import Any

from auto_scoring.adapters.ai_grading._schema import strict_ai_grading_result_schema


def _assert_no_object_node_omits_a_declared_property(node: object) -> None:
    if isinstance(node, dict):
        assert "default" not in node
        properties = node.get("properties")
        if node.get("type") == "object" and isinstance(properties, dict):
            assert set(node["required"]) == set(properties.keys())
            assert node.get("additionalProperties") is False
        for value in node.values():
            _assert_no_object_node_omits_a_declared_property(value)
    elif isinstance(node, list):
        for item in node:
            _assert_no_object_node_omits_a_declared_property(item)


def test_strict_schema_requires_every_declared_property() -> None:
    schema = strict_ai_grading_result_schema(criterion_count=3)
    _assert_no_object_node_omits_a_declared_property(schema)


def test_strict_schema_still_has_the_expected_top_level_shape() -> None:
    """A sanity check that the transform did not also strip real content:
    the top-level object still declares the documented wire fields
    (docs/poc-2-ai-grading.md section 9.2)."""
    schema: dict[str, Any] = strict_ai_grading_result_schema(criterion_count=3)
    assert schema["type"] == "object"
    assert set(schema["properties"]) == {
        "recognition",
        "grading",
        "criteria",
        "comment",
        "rationale",
        "annotations",
        "answerImage",
    }
    assert set(schema["required"]) == set(schema["properties"])


def test_strict_schema_asks_every_provider_what_the_answer_image_shows() -> None:
    """``answerImage`` (Issue #136) reaches a provider as a required field
    whose candidate values are written down, and whose fourth option is
    ``null``.

    Both halves matter. Required, because a provider that simply omits the
    field leaves the pipeline where it was before this Issue -- grading an
    image nobody checked. Nullable, because the alternative to "I cannot
    tell" would be a model picking one of the three anyway, and one of the
    three stops the grade.
    """
    schema: dict[str, Any] = strict_ai_grading_result_schema(criterion_count=3)
    assert "answerImage" in schema["required"]

    finding = schema["properties"]["answerImage"]
    types = {branch.get("type") for branch in finding["anyOf"]}
    assert "null" in types

    refs = [branch["$ref"] for branch in finding["anyOf"] if "$ref" in branch]
    assert len(refs) == 1
    definition = schema["$defs"][refs[0].rsplit("/", 1)[-1]]
    assert set(definition["enum"]) == {"answer", "blank", "not_the_answer"}
