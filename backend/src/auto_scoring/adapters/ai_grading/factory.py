"""Config-driven selection between ``AIProvider`` transports (Issue #44).

``docs/poc-2-ai-grading.md`` section 7.1 lists the supported
``AUTO_SCORING_AI_GRADING_TRANSPORT`` values and each transport's required
variables. This module only maps that configuration onto a concrete adapter
-- it is not itself wired into ``api.app.create_app`` yet (no caller
constructs a grading job processor in this repository yet; that wiring is
future MVP work, out of scope for Issue #44).
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping

from auto_scoring.adapters.ai_grading.codex_app_server_provider import CodexAppServerProvider
from auto_scoring.adapters.ai_grading.openrouter_provider import OpenRouterAIProvider
from auto_scoring.domain.ai_provider import AIProvider

_TRANSPORT_ENV_VAR = "AUTO_SCORING_AI_GRADING_TRANSPORT"

#: OpenRouter's Chat Completions API is OpenAI-compatible, and OpenAI's
#: sampling `temperature` is documented as accepting 0-2; above 2 the
#: request itself is invalid (code review finding).
_OPENROUTER_MAX_TEMPERATURE = 2.0


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

    if transport == "openrouter":
        return OpenRouterAIProvider(
            api_key=_require(values, "AUTO_SCORING_OPENROUTER_API_KEY"),
            model=_require(values, "AUTO_SCORING_OPENROUTER_MODEL"),
            prompt_version=prompt_version,
            # OpenRouter/OpenAI-compatible sampling temperature tops out at
            # 2.0; accepting anything higher here would build a provider
            # whose every grading call fails remotely as a 4xx instead of
            # failing fast at configuration time (code review finding).
            temperature=_parse_temperature(values, maximum=_OPENROUTER_MAX_TEMPERATURE),
        )

    if transport == "codex_app_server":
        # No temperature here: Codex app-server's protocol has no sampling-
        # temperature parameter, so CodexAppServerProvider does not accept
        # one either (see codex_app_server_provider._UNCONFIGURABLE_TEMPERATURE
        # -- code review finding).
        return CodexAppServerProvider(
            model=values.get("AUTO_SCORING_CODEX_MODEL", "").strip() or None,
            prompt_version=prompt_version,
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


def _parse_temperature(values: Mapping[str, str], *, maximum: float | None = None) -> float:
    """Validate ``AUTO_SCORING_AI_GRADING_TEMPERATURE`` at this trust
    boundary (AGENTS.md "Security": validate every input that crosses a
    trust boundary) rather than letting a malformed value surface later as
    an unclassified ``ValueError`` from ``float()``, or as a non-finite/
    negative/too-large value that only fails once a real call is made --
    either at ``ProviderDescriptor.__post_init__`` or, for a
    provider-specific ceiling like ``maximum``, as a remote 4xx response
    (code review finding)."""
    raw = values.get("AUTO_SCORING_AI_GRADING_TEMPERATURE", "0.0")
    try:
        value = float(raw)
    except ValueError as exc:
        raise AIProviderConfigError(
            f"AUTO_SCORING_AI_GRADING_TEMPERATURE must be a number, got {raw!r}"
        ) from exc
    if not math.isfinite(value) or value < 0:
        raise AIProviderConfigError(
            f"AUTO_SCORING_AI_GRADING_TEMPERATURE must be finite and >= 0, got {value!r}"
        )
    if maximum is not None and value > maximum:
        raise AIProviderConfigError(
            f"AUTO_SCORING_AI_GRADING_TEMPERATURE must be <= {maximum}, got {value!r}"
        )
    return value
