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
"""

from __future__ import annotations

from typing import Any

from auto_scoring.domain.ai_grading import AIGradingResult


def strict_ai_grading_result_schema() -> dict[str, Any]:
    """``AIGradingResult.model_json_schema(by_alias=True)``, rewritten so
    every object node's ``required`` lists all of its declared properties
    (dropping any ``default`` keyword instead)."""
    schema = AIGradingResult.model_json_schema(by_alias=True)
    _make_strict(schema)
    return schema


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
