"""Parse provider-reported token usage from HTTP JSON bodies (Issue #187)."""

from __future__ import annotations

from typing import Any

from auto_scoring.domain.ai_provider import TokenUsage


def parse_openai_chat_usage(data: dict[str, Any]) -> TokenUsage | None:
    """Read ``usage`` from an OpenAI-compatible chat completion body."""
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if not isinstance(prompt, int) or not isinstance(completion, int):
        return None
    if prompt < 0 or completion < 0:
        return None
    return TokenUsage(input_tokens=prompt, output_tokens=completion)


def parse_gemini_usage(data: dict[str, Any]) -> TokenUsage | None:
    """Read ``usageMetadata`` from a Vertex/Gemini generateContent body."""
    metadata = data.get("usageMetadata")
    if not isinstance(metadata, dict):
        return None
    prompt = metadata.get("promptTokenCount")
    completion = metadata.get("candidatesTokenCount")
    if not isinstance(prompt, int) or not isinstance(completion, int):
        return None
    if prompt < 0 or completion < 0:
        return None
    return TokenUsage(input_tokens=prompt, output_tokens=completion)
