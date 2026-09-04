"""``ReplayAIProvider`` — an :class:`AIProvider` that replays recorded responses.

Purpose:

* Run the whole harness (schema validation, metrics, report) **without API keys**.
* Guarantee the aggregation is reproducible from the same data (受入条件, Issue #14):
  the inputs are static JSON files, so two runs produce byte-identical reports.
* Serve as the reference implementation for the ``AIProvider`` contract test.

A recording whose ``raw_response`` fails schema validation surfaces as
:class:`SchemaViolation`, exactly as a real provider would.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from auto_scoring.domain.ai_grading import AIGradingResult
from auto_scoring.domain.ai_provider import (
    GradingRequest,
    GradingResponse,
    ProviderDescriptor,
    ProviderUnavailable,
    SchemaViolation,
    TokenUsage,
)


class Recording(BaseModel):
    """One recorded provider call, stored as ``<variant>/<question_id>.json``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    synthetic: bool = Field(alias="_synthetic", default=False)
    raw_response: dict[str, Any]
    usage: TokenUsage | None = None
    latency_s: float | None = Field(default=None, ge=0.0)


class ReplayAIProvider:
    """Replays recordings for one ``(candidate, ocr_variant)`` pair."""

    def __init__(self, descriptor: ProviderDescriptor, recordings: dict[str, Recording]) -> None:
        self._descriptor = descriptor
        self._recordings = recordings

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    def grade(self, request: GradingRequest) -> GradingResponse:
        recording = self._recordings.get(request.question_id)
        if recording is None:
            raise ProviderUnavailable(
                f"{self._descriptor.provider}: no recording for {request.question_id!r}"
            )
        try:
            result = AIGradingResult.model_validate(recording.raw_response)
        except ValidationError as exc:
            raise SchemaViolation(self._descriptor.provider, _first_error(exc)) from exc
        return GradingResponse(
            result=result,
            descriptor=self._descriptor,
            usage=recording.usage,
            latency_s=recording.latency_s,
        )


def _first_error(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:  # pragma: no cover - defensive
        return "unknown validation error"
    first = errors[0]
    location = ".".join(str(part) for part in first["loc"]) or "<root>"
    return f"{location}: {first['msg']}"


def load_replay_provider(fixtures_dir: Path, candidate: str, variant: str) -> ReplayAIProvider:
    """Build a provider from ``fixtures_dir/recorded/<candidate>/``.

    ``descriptor.json`` holds the reproducibility conditions; ``<variant>/*.json``
    hold one :class:`Recording` per question.
    """
    candidate_dir = fixtures_dir / "recorded" / candidate
    descriptor = ProviderDescriptor.model_validate_json(
        (candidate_dir / "descriptor.json").read_text(encoding="utf-8")
    )
    variant_dir = candidate_dir / variant
    if not variant_dir.is_dir():
        raise FileNotFoundError(f"no recordings for variant {variant!r} in {candidate_dir}")
    recordings: dict[str, Recording] = {}
    for path in sorted(variant_dir.glob("*.json")):
        recordings[path.stem] = Recording.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
    return ReplayAIProvider(descriptor, recordings)
