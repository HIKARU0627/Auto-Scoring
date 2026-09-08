"""Config-driven construction of the `CriteriaExtractor` (Issue #103).

**No new configuration.** This reads the same
``AUTO_SCORING_AI_GRADING_TRANSPORT`` priority list, and the same per-vendor
credentials, that ``adapters.ai_grading.factory`` already reads: an operator
who has configured grading has configured extraction, and a second variable
would only create a way for the two to disagree about which vendor this
install talks to.

Two deliberate differences from the grading chain:

* **``codex_app_server`` is skipped.** Its protocol has no image input, and
  every measured criteria document needs one (6 of 11 have no text layer at
  all). Leaving it in the list would guarantee one failed call before every
  extraction.
* **No fallback chain -- the first usable transport wins.** Extraction is a
  single action a person starts from a screen and watches; a failure lands
  in front of them with a reason and a button to press again.
  `FallbackAIProvider` exists for the unattended grading queue, where
  nobody is watching, and borrowing it here would spend a second vendor's
  quota on a call the reviewer is about to retry anyway.

Every message this module produces is published (it becomes
`UnconfiguredCriteriaExtractor.reason`, which the extract endpoint returns
and the app displays), so it names configuration *variables* only, never
their values -- the rule ``adapters.ai_grading.factory``'s docstring states
and ``tests/test_grading_availability.py`` enforces for its counterpart.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.criteria_extraction.extractor import (
    ChatCompletionsCriteriaExtractor,
    VertexGeminiCriteriaExtractor,
)
from auto_scoring.domain.criteria_extraction import CriteriaExtractor

_TRANSPORT_ENV_VAR = "AUTO_SCORING_AI_GRADING_TRANSPORT"

#: Transports that can be sent an image. ``codex_app_server`` is absent on
#: purpose -- see the module docstring.
_IMAGE_CAPABLE_TRANSPORTS = ("gemini", "openrouter", "openai")

_OPENAI_BASE_URL = "https://api.openai.com/v1"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

#: Per-request retention opt-outs, copied from the grading adapters so the
#: same material is treated the same way whichever call sends it. OpenAI's
#: ``store: false`` keeps the request out of the account's logs; OpenRouter's
#: two routing fields restrict the request to upstreams that neither train on
#: nor retain it (see ``adapters.ai_grading.openrouter_provider`` for why both
#: are required). Issue #95 decision 7 permits sending this material to the
#: configured provider; it does not permit leaving copies of it around.
_OPENAI_EXTRA = {"store": False}
_OPENROUTER_EXTRA = {"provider": {"data_collection": "deny", "zdr": True}}

TokenSourceFactory = Callable[[str | None], AdcTokenSource]


class CriteriaExtractorConfigError(Exception):
    """No image-capable transport could be built on this host."""


def _default_token_source(project_id: str | None) -> AdcTokenSource:
    return AdcTokenSource(project_id=project_id)


def create_criteria_extractor(
    env: Mapping[str, str] | None = None,
    *,
    token_source_factory: TokenSourceFactory = _default_token_source,
) -> CriteriaExtractor:
    """Build the first usable image-capable transport in the configured
    priority order.

    Raises :class:`CriteriaExtractorConfigError` when the transport list is
    unset, names no image-capable transport, or names only ones whose
    credentials are missing here. Never guesses a vendor or a model.

    ``token_source_factory`` is the one host probe this function makes (is
    there an ADC login?), injected for the reason ``docs/quality-gates.md``
    records as "ホストを見る判定はテストへ注入する": whether `gcloud` has been
    logged into differs between a developer machine and a CI runner, and a
    test that cannot say which world it is in passes in one and fails in the
    other.
    """
    values = env if env is not None else os.environ
    raw = values.get(_TRANSPORT_ENV_VAR, "")
    transports = tuple(item.strip() for item in raw.split(",") if item.strip())
    if not transports:
        raise CriteriaExtractorConfigError(
            f"{_TRANSPORT_ENV_VAR} is required: a comma-separated priority list drawn from "
            f"{list(_IMAGE_CAPABLE_TRANSPORTS)} (highest priority first)"
        )

    candidates = [transport for transport in transports if transport in _IMAGE_CAPABLE_TRANSPORTS]
    if not candidates:
        raise CriteriaExtractorConfigError(
            f"{_TRANSPORT_ENV_VAR} lists no transport that accepts images; 採点基準の抽出には "
            f"{list(_IMAGE_CAPABLE_TRANSPORTS)} のいずれかが必要です"
        )

    temperature = _parse_temperature(values)
    skipped: list[str] = []
    for transport in candidates:
        try:
            return _build(
                transport,
                values,
                temperature=temperature,
                token_source_factory=token_source_factory,
            )
        except _MissingCredentials as exc:
            skipped.append(f"{transport} ({exc})")

    raise CriteriaExtractorConfigError(
        f"none of the image-capable transports listed in {_TRANSPORT_ENV_VAR} have usable "
        f"credentials on this host: {'; '.join(skipped)}"
    )


class _MissingCredentials(Exception):
    """One transport has no credentials here; try the next one. Carries only
    variable *names* (module docstring)."""


def _build(
    transport: str,
    values: Mapping[str, str],
    *,
    temperature: float,
    token_source_factory: TokenSourceFactory,
) -> CriteriaExtractor:
    if transport == "gemini":
        model = _require_credential(values, "AUTO_SCORING_GEMINI_MODEL")
        try:
            tokens = token_source_factory(
                values.get("AUTO_SCORING_VERTEX_PROJECT", "").strip() or None
            )
        except AdcCredentialsError as exc:
            raise _MissingCredentials(str(exc)) from None
        return VertexGeminiCriteriaExtractor(
            model=model,
            tokens=tokens,
            temperature=temperature,
            location=values.get("AUTO_SCORING_VERTEX_LOCATION", "").strip() or "global",
        )
    if transport == "openrouter":
        return ChatCompletionsCriteriaExtractor(
            name="openrouter",
            api_key=_require_credential(values, "AUTO_SCORING_OPENROUTER_API_KEY"),
            model=_require_credential(values, "AUTO_SCORING_OPENROUTER_MODEL"),
            base_url=_OPENROUTER_BASE_URL,
            label="OpenRouter",
            extra_payload=dict(_OPENROUTER_EXTRA),
            temperature=temperature,
        )
    return ChatCompletionsCriteriaExtractor(
        name="openai",
        api_key=_require_credential(values, "AUTO_SCORING_OPENAI_API_KEY"),
        model=_require_credential(values, "AUTO_SCORING_OPENAI_MODEL"),
        base_url=_OPENAI_BASE_URL,
        label="OpenAI",
        extra_payload=dict(_OPENAI_EXTRA),
        temperature=temperature,
    )


def _require_credential(values: Mapping[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise _MissingCredentials(f"{key} is not set")
    return value


def _parse_temperature(values: Mapping[str, str]) -> float:
    """``AUTO_SCORING_AI_GRADING_TEMPERATURE``, defaulting to 0.0.

    A malformed value is **not** an error here, unlike in the grading
    factory: this extractor is not a second place to discover that the
    grading configuration is broken, and refusing to extract over it would
    take away the one screen a reviewer can still use. 0.0 is what this call
    wants anyway -- the extraction should be as close to deterministic as
    the vendor allows.
    """
    raw = values.get("AUTO_SCORING_AI_GRADING_TEMPERATURE", "").strip()
    if not raw:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    if value < 0.0 or value > 2.0:
        return 0.0
    return value
