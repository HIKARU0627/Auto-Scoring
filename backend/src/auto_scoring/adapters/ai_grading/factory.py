"""Config-driven construction of the ``AIProvider`` chain (Issues #44, #35).

``AUTO_SCORING_AI_GRADING_TRANSPORT`` takes a **comma-separated priority
list**, highest priority first, which for the adopted configuration is the
Issue #81 order ``gemini,codex_app_server,openrouter,openai``
(business-rules-and-evaluation-data.md section 3 (B)). Transports whose
credentials are not configured on this host are left out of the chain rather
than built and allowed to fail -- ``docs/ai-grading-pipeline.md``:
"認証情報が揃っているものだけをチェーンに組む" -- an unconfigured provider
must not consume one step of the chain by failing. A single value still
works and yields that one adapter directly, which is what every existing
caller and ``.env.local`` passes.

``docs/poc-2-ai-grading.md`` section 7.1 lists each transport's variables.
This module only maps that configuration onto adapters; it is still not
wired into ``api.app.create_app`` (that wiring is future MVP work).
"""

from __future__ import annotations

import math
import os
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path

from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.ai_grading.codex_app_server_provider import CodexAppServerProvider
from auto_scoring.adapters.ai_grading.fallback_provider import FallbackAIProvider
from auto_scoring.adapters.ai_grading.openai_provider import OpenAIAIProvider
from auto_scoring.adapters.ai_grading.openrouter_provider import OpenRouterAIProvider
from auto_scoring.adapters.ai_grading.vertex_gemini_provider import VertexGeminiAIProvider
from auto_scoring.domain.ai_provider import AIProvider

_TRANSPORT_ENV_VAR = "AUTO_SCORING_AI_GRADING_TRANSPORT"

#: Transport ids in the priority order Issue #81 adopted, used only to
#: render a helpful message; the actual order comes from the caller's
#: configuration, so an operator can shorten or reorder the chain without
#: editing code.
_KNOWN_TRANSPORTS = ("gemini", "codex_app_server", "openrouter", "openai")

#: OpenAI-compatible sampling `temperature` is documented as accepting 0-2,
#: and Vertex AI's Gemini `generationConfig.temperature` has the same
#: ceiling; above 2 the request itself is invalid (code review finding).
_MAX_TEMPERATURE = 2.0

#: Transports that accept a sampling temperature at all. Codex app-server's
#: protocol has none (see `codex_app_server_provider`), so selecting only
#: that transport must not make an out-of-range temperature a hard error
#: for a value nothing would have applied.
_TEMPERATURE_AWARE_TRANSPORTS = frozenset({"gemini", "openrouter", "openai"})


class AIProviderConfigError(Exception):
    """The AI-grading transport configuration is missing or invalid."""


#: How this module asks the host "could I run this?" and "is ADC set up?".
#: Both are boundaries in AGENTS.md's sense (filesystem, network) and both
#: are therefore injectable rather than reached for directly: whether the
#: `codex` binary or a `gcloud` login exists differs between a developer
#: machine and a CI runner, so a caller that cannot state which world it is
#: in gets a test that passes in one and fails in the other -- which is
#: exactly what happened (CI: "the 'codex' executable was not found on this
#: host"; the same three tests were green locally only because this project's
#: own review tooling installs `codex`).
ExecutableAvailable = Callable[[str], bool]
TokenSourceFactory = Callable[[str | None], AdcTokenSource]


def _executable_available(name: str) -> bool:
    """Whether ``name`` resolves to something runnable on this host.

    ``shutil.which`` covers a bare command resolved through ``PATH``;
    ``Path(name).is_file()`` covers an absolute or relative path given
    directly in ``AUTO_SCORING_CODEX_EXECUTABLE``.
    """
    return shutil.which(name) is not None or Path(name).is_file()


def _default_token_source(project_id: str | None) -> AdcTokenSource:
    return AdcTokenSource(project_id=project_id)


class _MissingCredentials(Exception):
    """One transport in a multi-transport chain has no credentials here.

    Internal: turned into a skip when other transports remain, and into an
    :class:`AIProviderConfigError` when nothing is left to build. Carries
    only variable *names*, never values (AGENTS.md "Security").
    """


def create_ai_provider(
    env: Mapping[str, str] | None = None,
    *,
    executable_available: ExecutableAvailable = _executable_available,
    token_source_factory: TokenSourceFactory = _default_token_source,
) -> AIProvider:
    """Build the adapter (or fallback chain) selected by
    ``AUTO_SCORING_AI_GRADING_TRANSPORT``.

    Raises :class:`AIProviderConfigError` if the variable is unset, names an
    unknown transport, repeats one, or if *no* listed transport has usable
    credentials -- never falls back to a default vendor or a guessed value.
    A transport that cannot be built is only skipped while at least one
    other transport in the list still can be.

    ``executable_available`` and ``token_source_factory`` are the two host
    probes this function makes, injected so a caller can state which world
    it is in rather than inheriting whatever the machine happens to have
    (AGENTS.md "Architecture": inject boundaries from outside). Production
    passes neither and gets the real ones; a test passes both and gets the
    same answer on a developer machine and a CI runner.
    """
    values = env if env is not None else os.environ
    transports = _parse_transports(values)
    prompt_version = _require(values, "AUTO_SCORING_AI_GRADING_PROMPT_VERSION")
    # Read only when a selected transport actually applies it: a
    # codex_app_server-only configuration must not be rejected over a value
    # nothing would have used (existing behaviour, kept). The 0.0 below is
    # never sent anywhere in that case.
    temperature = (
        _parse_temperature(values) if set(transports) & _TEMPERATURE_AWARE_TRANSPORTS else 0.0
    )

    providers: list[AIProvider] = []
    skipped: list[str] = []
    for transport in transports:
        try:
            providers.append(
                _build(
                    transport,
                    values,
                    prompt_version=prompt_version,
                    temperature=temperature,
                    executable_available=executable_available,
                    token_source_factory=token_source_factory,
                )
            )
        except _MissingCredentials as exc:
            skipped.append(f"{transport} ({exc})")

    if not providers:
        raise AIProviderConfigError(
            f"none of the transports listed in {_TRANSPORT_ENV_VAR} have usable credentials "
            f"on this host: {'; '.join(skipped)}"
        )
    if len(providers) == 1:
        return providers[0]
    return FallbackAIProvider(providers)


def _parse_transports(values: Mapping[str, str]) -> tuple[str, ...]:
    raw = values.get(_TRANSPORT_ENV_VAR, "")
    transports = tuple(item.strip() for item in raw.split(",") if item.strip())
    if not transports:
        raise AIProviderConfigError(
            f"{_TRANSPORT_ENV_VAR} is required: a comma-separated priority list drawn from "
            f"{list(_KNOWN_TRANSPORTS)} (highest priority first)"
        )
    unknown = [transport for transport in transports if transport not in _KNOWN_TRANSPORTS]
    if unknown:
        raise AIProviderConfigError(
            f"{_TRANSPORT_ENV_VAR} lists unknown transport(s) {unknown}; supported values are "
            f"{list(_KNOWN_TRANSPORTS)}"
        )
    if len(set(transports)) != len(transports):
        # A repeat is always a configuration mistake, and a silently-deduped
        # one would leave the operator believing a provider they named twice
        # is being tried twice.
        raise AIProviderConfigError(f"{_TRANSPORT_ENV_VAR} lists the same transport twice")
    return transports


def _build(
    transport: str,
    values: Mapping[str, str],
    *,
    prompt_version: str,
    temperature: float,
    executable_available: ExecutableAvailable,
    token_source_factory: TokenSourceFactory,
) -> AIProvider:
    if transport == "gemini":
        return _build_vertex_gemini(
            values,
            prompt_version=prompt_version,
            temperature=temperature,
            token_source_factory=token_source_factory,
        )
    if transport == "openrouter":
        return OpenRouterAIProvider(
            api_key=_require_credential(values, "AUTO_SCORING_OPENROUTER_API_KEY"),
            model=_require_credential(values, "AUTO_SCORING_OPENROUTER_MODEL"),
            prompt_version=prompt_version,
            temperature=temperature,
        )
    if transport == "openai":
        return OpenAIAIProvider(
            api_key=_require_credential(values, "AUTO_SCORING_OPENAI_API_KEY"),
            model=_require_credential(values, "AUTO_SCORING_OPENAI_MODEL"),
            prompt_version=prompt_version,
            temperature=temperature,
        )
    # codex_app_server: no API key lives here at all -- authentication is
    # the operator's own `codex login` session on this host (docs/poc-2-ai-
    # grading.md section 7.1). That session state is not inspectable from
    # this process, but the executable that would carry it *is*: a host
    # where `codex` is not installed cannot possibly grade anything, so
    # leaving this link in the chain there just guarantees one wasted
    # failure ahead of every provider below it -- exactly what
    # docs/ai-grading-pipeline.md's "認証情報が揃っているものだけをチェーンに
    # 組む" rules out (code review finding). Being installed is necessary,
    # not sufficient: a host with `codex` but no login still fails at call
    # time, and the chain falls through then.
    #
    # No temperature either: Codex app-server's protocol has no sampling-
    # temperature parameter, so CodexAppServerProvider does not accept one
    # (see codex_app_server_provider._UNCONFIGURABLE_TEMPERATURE -- code
    # review finding).
    executable = values.get("AUTO_SCORING_CODEX_EXECUTABLE", "").strip() or "codex"
    if not executable_available(executable):
        raise _MissingCredentials(f"the {executable!r} executable was not found on this host")
    return CodexAppServerProvider(
        model=values.get("AUTO_SCORING_CODEX_MODEL", "").strip() or None,
        prompt_version=prompt_version,
        executable=executable,
    )


def _build_vertex_gemini(
    values: Mapping[str, str],
    *,
    prompt_version: str,
    temperature: float,
    token_source_factory: TokenSourceFactory,
) -> AIProvider:
    """Gemini through Vertex AI, authenticated with ADC.

    There is no ``AUTO_SCORING_GEMINI_API_KEY`` path: Gemini API keys are
    blocked by this project's Google Cloud organization policy
    (``_google_adc``). Missing ADC is a *skippable* missing credential, not
    a hard configuration error, so a chain that also lists another transport
    still starts on a developer machine with no `gcloud` login.
    """
    model = _require_credential(values, "AUTO_SCORING_GEMINI_MODEL")
    try:
        tokens = token_source_factory(values.get("AUTO_SCORING_VERTEX_PROJECT", "").strip() or None)
    except AdcCredentialsError as exc:
        raise _MissingCredentials(str(exc)) from None
    return VertexGeminiAIProvider(
        model=model,
        prompt_version=prompt_version,
        tokens=tokens,
        temperature=temperature,
        location=values.get("AUTO_SCORING_VERTEX_LOCATION", "").strip() or "global",
    )


def _require(values: Mapping[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise AIProviderConfigError(f"{key} is required and must be a non-blank string")
    return value


def _require_credential(values: Mapping[str, str], key: str) -> str:
    """Like :func:`_require`, but a missing value marks this transport
    unconfigured rather than failing the whole chain."""
    value = values.get(key, "").strip()
    if not value:
        raise _MissingCredentials(f"{key} is not set")
    return value


def _parse_temperature(values: Mapping[str, str]) -> float:
    """Validate ``AUTO_SCORING_AI_GRADING_TEMPERATURE`` at this trust
    boundary (AGENTS.md "Security": validate every input that crosses a
    trust boundary) rather than letting a malformed value surface later as
    an unclassified ``ValueError`` from ``float()``, or as a non-finite/
    negative/too-large value that only fails once a real call is made --
    either at ``ProviderDescriptor.__post_init__`` or, for the
    ``_MAX_TEMPERATURE`` ceiling, as a remote 4xx response (code review
    finding)."""
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
    if value > _MAX_TEMPERATURE:
        raise AIProviderConfigError(
            f"AUTO_SCORING_AI_GRADING_TEMPERATURE must be <= {_MAX_TEMPERATURE}, got {value!r}"
        )
    return value
