"""The grading call must tell the model how an annotation's ``target`` is
used (Issue #141).

An annotation carries no coordinates -- the AI never returns PDF coordinates
(simplified-design-spec §12.1) -- so the app places it by looking ``target``
up among the OCR reading's word boxes
(`domain.annotation_layout.resolve_annotation_rect`). That makes ``target``
a *quotation*, not a description, and nothing had ever said so: the prompt
did not mention the field at all, and the generated schema carried a bare
``{"type": "string"}``.

In the live re-verification several models filled it with text that is
nowhere in the reading -- a reading tidied into correct notation, a
handwritten formula rewritten in LaTeX, two non-adjacent sub-answers joined
into one string, an invented placeholder for a blank answer. None of them
could be placed, and six of the run's fourteen annotations failed for this
reason rather than for any matching problem (`docs/pdf-export.md` §2.4.1).

Written against the *property* -- "both channels the model reads state the
verbatim rule" -- rather than against a wording, so a later rewrite of
either message keeps the requirement. **What this cannot check is whether
the instruction works**: that is a question about a model's behaviour, and
it is answered by a live run, not here.
"""

from __future__ import annotations

from typing import Any

from auto_scoring.adapters.ai_grading._prompt import GRADING_SYSTEM_INSTRUCTIONS
from auto_scoring.adapters.ai_grading._schema import strict_ai_grading_result_schema


def _target_property(node: Any) -> dict[str, Any] | None:
    """The ``target`` property node from anywhere in ``node``.

    Searched rather than indexed by path: the annotation object sits behind a
    ``$defs`` reference that `strict_ai_grading_result_schema` may inline or
    keep, and this test is about the field reaching the model, not about
    where the generator chose to put it.
    """
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict) and isinstance(properties.get("target"), dict):
            found: dict[str, Any] = properties["target"]
            return found
        for value in node.values():
            nested = _target_property(value)
            if nested is not None:
                return nested
    elif isinstance(node, list):
        for item in node:
            nested = _target_property(item)
            if nested is not None:
                return nested
    return None


def test_the_schema_tells_the_model_what_target_must_be() -> None:
    target = _target_property(strict_ai_grading_result_schema(criterion_count=3))

    assert target is not None, "the annotation schema no longer declares a 'target' field"
    description = target.get("description", "")
    assert description, (
        "'target' is sent to the model as a bare string with no description; "
        "nothing then tells it the field must quote the reading (Issue #141)"
    )
    assert "verbatim" in description.lower()
    assert "reading" in description.lower()


def test_the_system_instructions_state_the_verbatim_rule_too() -> None:
    """Both channels, not one. A schema description and a system instruction
    are read by different models to different degrees, and the two provider
    adapters send them by different mechanisms (``system`` role message vs
    ``thread/start.developerInstructions``) -- so the rule that decides
    whether a mark can be placed at all is stated in both."""
    instructions = GRADING_SYSTEM_INSTRUCTIONS.lower()

    assert "'target'" in instructions or '"target"' in instructions
    assert "verbatim" in instructions
