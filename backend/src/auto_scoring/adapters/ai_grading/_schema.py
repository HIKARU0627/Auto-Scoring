"""Strict-mode JSON Schema for ``AIGradingResult``, shared by every
``AIProvider`` adapter that constrains a model's output to it (Issue #44
code review finding).

OpenAI-compatible "strict" Structured Outputs (what
``openrouter_provider.py``'s ``response_format`` requests, and what Codex
app-server's ``turn/start.outputSchema`` accepts as a hint) require every
declared object property to be listed in that object's ``required`` array,
with optionality expressed as a nullable type instead of an absent key or a
``default`` keyword. Pydantic's own ``model_json_schema()`` does the
opposite for a field with a default (e.g. ``AIGradingResult.annotations``,
``AnnotationCandidate.comment``): it omits the field from ``required`` and
emits a ``default`` keyword instead -- a shape a strict backend rejects as
an invalid schema before ever running the model, and which the domain
schema itself cannot express any other way without changing the wire
format's real optionality semantics (``ai_grading.py``).

**Per request, not once (Issue #117).** The one thing this schema pins that
the domain model cannot is the candidate set for ``criteria[].index``: how
many rubric criteria there are is a property of the question being graded,
not of the wire format. Fixing it here turns "which criterion is this?"
into a multiple-choice question with the alternatives written down -- the
same move Issue #101 made for attribution -- rather than a free-text field
a model has to fill in correctly. It is defence in depth, not the fix
itself: a schema is only as good as the provider's enforcement of it (a
live Vertex AI probe showed ``responseJsonSchema`` honouring the shape of
the schema while ignoring its ``maxLength`` keywords -- docs/poc-2-ai-
grading.md section 7.4), and the real guarantee is that a small integer is
not a transcription of anything.
"""

from __future__ import annotations

from typing import Any

from auto_scoring.domain.ai_grading import AIGradingResult


def strict_ai_grading_result_schema(*, criterion_count: int) -> dict[str, Any]:
    """``AIGradingResult.model_json_schema(by_alias=True)``, rewritten so
    every object node's ``required`` lists all of its declared properties
    (dropping any ``default`` keyword instead), and so ``criteria`` is
    exactly ``criterion_count`` entries choosing from positions
    ``1..criterion_count``.

    ``criterion_count`` is the length of the calling
    ``GradingRequest.criterion_ids``. Zero or fewer is rejected rather than
    emitted as an empty ``enum``: `GradingJobProcessor.process` already
    fails a question with no registered rubric before any provider call, so
    it could only arrive here as a bug upstream, and an empty candidate set
    would ask a model to pick from nothing.
    """
    if criterion_count < 1:
        raise ValueError(
            f"strict_ai_grading_result_schema needs at least one criterion, got {criterion_count!r}"
        )
    schema = AIGradingResult.model_json_schema(by_alias=True)
    _make_strict(schema)
    _pin_criteria(schema, criterion_count)
    return schema


def _pin_criteria(schema: dict[str, Any], criterion_count: int) -> None:
    """Narrow ``criteria`` to this question's own rubric.

    ``minItems``/``maxItems`` say "one judgement per criterion, no more and
    no fewer" -- the same 1:1 correspondence
    `GradingJobProcessor.process` rejects a response for failing, stated up
    front where a strict provider can enforce it instead of only after the
    call. The ``enum`` is the candidate set itself.
    """
    criteria = schema["properties"]["criteria"]
    criteria["minItems"] = criterion_count
    criteria["maxItems"] = criterion_count
    item = _resolve(schema, criteria["items"])
    item["properties"]["index"]["enum"] = list(range(1, criterion_count + 1))


def _resolve(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    """Follow a local ``$ref`` into ``schema``'s own ``$defs``.

    Pydantic emits ``criteria.items`` as a ``$ref`` to a shared
    ``CriterionResultOutput`` definition; narrowing that definition is
    correct precisely because it is only referenced from ``criteria``.
    """
    ref = node.get("$ref")
    if ref is None:
        return node
    resolved: dict[str, Any] = schema["$defs"][ref.rsplit("/", 1)[-1]]
    return resolved


def _make_strict(node: object) -> None:
    if isinstance(node, dict):
        node.pop("default", None)
        properties = node.get("properties")
        if node.get("type") == "object" and isinstance(properties, dict):
            node["required"] = list(properties.keys())
            node.setdefault("additionalProperties", False)
        for value in node.values():
            _make_strict(value)
    elif isinstance(node, list):
        for item in node:
            _make_strict(item)
