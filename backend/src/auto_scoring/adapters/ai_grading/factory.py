"""Config-driven selection between ``AIProvider`` transports (Issue #44).

``docs/poc-2-ai-grading.md`` section 7.1 lists the supported
``AUTO_SCORING_AI_GRADING_TRANSPORT`` values and each transport's required
variables. This module only maps that configuration onto a concrete adapter
-- it is not itself wired into ``api.app.create_app`` yet (no caller
constructs a grading job processor in this repository yet; that wiring is
future MVP work, out of scope for Issue #44).
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from auto_scoring.adapters.ai_grading.codex_app_server_provider import CodexAppServerProvider
from auto_scoring.adapters.ai_grading.openrouter_provider import OpenRouterAIProvider
from auto_scoring.domain.ai_provider import AIProvider

_TRANSPORT_ENV_VAR = "AUTO_SCORING_AI_GRADING_TRANSPORT"


class AIProviderConfigError(Exception):
    """The AI-grading transport configuration is missing or invalid."""


def create_ai_provider(env: Mapping[str, str] | None = None) -> AIProvider:
    """Build the adapter selected by ``AUTO_SCORING_AI_GRADING_TRANSPORT``.

    Raises :class:`AIProviderConfigError` if the transport is unset/unknown,
    or a required variable for the selected transport is missing or blank --
    never falls back to a default vendor or a guessed value.
    """
    values = env if env is not None else os.environ
    transport = values.get(_TRANSPORT_ENV_VAR, "").strip()
    prompt_version = _require(values, "AUTO_SCORING_AI_GRADING_PROMPT_VERSION")
    temperature = float(values.get("AUTO_SCORING_AI_GRADING_TEMPERATURE", "0.0"))

    if transport == "openrouter":
        return OpenRouterAIProvider(
            api_key=_require(values, "AUTO_SCORING_OPENROUTER_API_KEY"),
            model=_require(values, "AUTO_SCORING_OPENROUTER_MODEL"),
            prompt_version=prompt_version,
            temperature=temperature,
        )

    if transport == "codex_app_server":
        return CodexAppServerProvider(
            model=values.get("AUTO_SCORING_CODEX_MODEL", "").strip() or None,
            prompt_version=prompt_version,
            temperature=temperature,
            executable=values.get("AUTO_SCORING_CODEX_EXECUTABLE", "").strip() or "codex",
        )

    raise AIProviderConfigError(
        f"{_TRANSPORT_ENV_VAR} must be 'openrouter' or 'codex_app_server', got {transport!r}"
    )


def _require(values: Mapping[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise AIProviderConfigError(f"{key} is required and must be a non-blank string")
    return value
