"""Every AI-generated natural-language field (rationale/comment/note) must be
Japanese, and that language rule is defined exactly once (Issue #140).

A real 8-subject run returned ``rationale``/``comment`` in English for three
subjects and in Japanese for the other three -- the model followed the
language of the material it was given, because nothing told it otherwise.
The same run's criteria-extraction ``note`` came back in English too, and
went straight to the teacher's screen. ``domain.ai_response_language`` fixes
the wording once; this module pins that every adapter's prompt text and
every human-facing schema field description actually quotes it, rather than
each adapter writing (and inevitably drifting on) its own sentence.

Both places matter and are tested separately: a structured-output backend
enforces the schema, including each field's own ``description``, while the
free-text system/developer instructions travel over a separate channel nothing
requires a schema-driven decoder to have read as closely. Stating the rule in
only one of the two lets a model default back to the material's language for
whichever field the other channel did not reach -- the exact failure this
Issue was filed against.

Because every one of these assertions imports
``auto_scoring.domain.ai_response_language`` and checks for its *exact*
content, deleting or rewording the shared constant turns every test in this
module red at once -- there is nowhere left for an adapter to fall back to a
copy of its own.
"""

from __future__ import annotations

from typing import Any

from auto_scoring.adapters.ai_classification.classifier import (
    attribution_response_schema,
    role_response_schema,
)
from auto_scoring.adapters.ai_grading._prompt import GRADING_SYSTEM_INSTRUCTIONS
from auto_scoring.adapters.ai_grading._schema import strict_ai_grading_result_schema
from auto_scoring.adapters.answer_area_detection._prompt import (
    ANSWER_AREA_SYSTEM_INSTRUCTIONS,
    strict_answer_area_detection_schema,
)
from auto_scoring.adapters.criteria_extraction._prompt import (
    CRITERIA_SYSTEM_INSTRUCTIONS,
    strict_criteria_extraction_schema,
)
from auto_scoring.domain.ai_response_language import (
    FIELD_LANGUAGE_NOTE,
    RESPONSE_LANGUAGE_INSTRUCTION,
)
from auto_scoring.domain.material_classifier import AttributionCandidate


def _resolve(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    """Follow a local ``$ref`` into ``schema``'s own ``$defs``."""
    ref = node.get("$ref")
    if not isinstance(ref, str):
        return node
    defs = schema["$defs"]
    assert isinstance(defs, dict)
    resolved = defs[ref.rsplit("/", 1)[-1]]
    assert isinstance(resolved, dict)
    return resolved


def _description(prop: dict[str, Any]) -> str:
    """A property's own ``description``, or the one on its non-null branch of
    an ``anyOf`` -- ``Field(description=...)`` lands in either place
    depending on whether it wraps the inner type or the ``T | None`` union
    (both patterns are in use across these three domain modules)."""
    if "description" in prop:
        value = prop["description"]
        assert isinstance(value, str)
        return value
    for branch in prop.get("anyOf", ()):
        if "description" in branch:
            value = branch["description"]
            assert isinstance(value, str)
            return value
    return ""


# --------------------------------------------------------------------------- #
# The prompt text each adapter sends over its trusted instruction channel.
# --------------------------------------------------------------------------- #


def test_grading_prompt_states_the_shared_language_instruction() -> None:
    assert RESPONSE_LANGUAGE_INSTRUCTION in GRADING_SYSTEM_INSTRUCTIONS


def test_criteria_extraction_prompt_states_the_shared_language_instruction() -> None:
    assert RESPONSE_LANGUAGE_INSTRUCTION in CRITERIA_SYSTEM_INSTRUCTIONS


def test_answer_area_detection_prompt_states_the_shared_language_instruction() -> None:
    assert RESPONSE_LANGUAGE_INSTRUCTION in ANSWER_AREA_SYSTEM_INSTRUCTIONS


# --------------------------------------------------------------------------- #
# The wire schema's own field descriptions -- the other channel a
# structured-output backend actually reads.
# --------------------------------------------------------------------------- #


def test_ai_grading_schema_prose_fields_require_japanese() -> None:
    schema = strict_ai_grading_result_schema(criterion_count=1)
    assert FIELD_LANGUAGE_NOTE in _description(schema["properties"]["comment"])
    assert FIELD_LANGUAGE_NOTE in _description(schema["properties"]["rationale"])

    criterion = _resolve(schema, schema["properties"]["criteria"]["items"])
    assert FIELD_LANGUAGE_NOTE in _description(criterion["properties"]["rationale"])

    annotation = _resolve(schema, schema["properties"]["annotations"]["items"])
    assert FIELD_LANGUAGE_NOTE in _description(annotation["properties"]["comment"])


def test_ai_grading_verbatim_quote_field_is_exempt() -> None:
    """``target`` must be copied verbatim from the student's OCR reading
    (Issue #141) -- translating it would corrupt the very text the app
    matches back onto the answer's word boxes, so it must not carry the
    language instruction meant for the model's own prose."""
    schema = strict_ai_grading_result_schema(criterion_count=1)
    annotation = _resolve(schema, schema["properties"]["annotations"]["items"])
    assert FIELD_LANGUAGE_NOTE not in _description(annotation["properties"]["target"])


def test_criteria_extraction_schema_notes_require_japanese() -> None:
    schema = strict_criteria_extraction_schema()
    assert FIELD_LANGUAGE_NOTE in _description(schema["properties"]["note"])

    question = _resolve(schema, schema["properties"]["questions"]["items"])
    assert FIELD_LANGUAGE_NOTE in _description(question["properties"]["note"])


def test_criteria_extraction_transcribed_fields_are_exempt() -> None:
    """``description`` (a criterion's text) and ``model_answer`` are copied
    out of the 採点基準 document, not the model's own judgement -- pushing
    them toward Japanese would mismatch the source for a subject whose
    material is not Japanese."""
    schema = strict_criteria_extraction_schema()
    question = _resolve(schema, schema["properties"]["questions"]["items"])
    assert FIELD_LANGUAGE_NOTE not in _description(question["properties"]["model_answer"])

    criterion = _resolve(schema, question["properties"]["criteria"]["items"])
    assert FIELD_LANGUAGE_NOTE not in _description(criterion["properties"]["description"])


def test_answer_area_detection_schema_note_requires_japanese() -> None:
    schema = strict_answer_area_detection_schema(["1"])
    area = _resolve(schema, schema["properties"]["areas"]["items"])
    assert FIELD_LANGUAGE_NOTE in _description(area["properties"]["note"])


# --------------------------------------------------------------------------- #
# ai_classification (Issue #140 scope note): it never asks the model for
# prose in the first place.
# --------------------------------------------------------------------------- #


def test_classification_schemas_have_no_free_text_field() -> None:
    """Every classification property is either an ``enum``-constrained string
    or a number (`adapters.ai_classification.classifier`) -- there is no
    rationale/comment/note field for the language instruction to reach. This
    is not an oversight; it is why this adapter needed no prompt change for
    Issue #140. If a future change adds a free-text field here, this test
    fails and says where -- it does not silently ship an untranslated one."""
    candidates = (AttributionCandidate(id="t1", label="Test 1"),)
    schemas = (role_response_schema(), attribution_response_schema(candidates))
    for schema in schemas:
        for name, prop in schema["properties"].items():
            if prop.get("type") == "string":
                assert "enum" in prop, (
                    f"{name!r} is free text, not an enum -- Issue #140's shared "
                    "language instruction must be wired to it"
                )
