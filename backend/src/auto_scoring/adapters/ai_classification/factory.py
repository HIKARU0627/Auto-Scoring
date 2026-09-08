"""Build the material classifier from the same configuration grading uses
(Issue #101).

Reads the same ``AUTO_SCORING_AI_GRADING_TRANSPORT`` priority list as
`adapters.ai_grading.factory`, and builds a classifier over the first
transport in it that has usable credentials on this host. Sharing the
variable is deliberate: an operator who has configured grading has, by
definition, configured a provider that can also look at a page image, and a
second variable to keep in step would be a second thing to get wrong.

**No fallback chain.** Grading builds one because a failed grading call
blocks a whole submission; a failed *classification* call blocks nothing --
the file stays unresolved and the reviewer picks its role, which they can do
anyway. Adding a chain here would multiply the cost and the wait of the one
thing Issue #101 explicitly asks to keep cheap.

``codex_app_server`` is not supported: its protocol carries no image input,
and classification is entirely about looking at a page. A host configured
with only that transport gets :class:`ClassifierUnavailable` and the manual
path, which is the honest answer rather than a chain link that always fails.

No message raised from this module may quote a configuration *value* -- only
variable names and the fixed transport ids (the same rule
`adapters.ai_grading.factory` documents, for the same reason: this text is
published through the API and shown on screen).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from auto_scoring.adapters.ai_classification._calls import (
    ChatCompletionsJsonCall,
    StructuredJsonCall,
    VertexGeminiJsonCall,
)
from auto_scoring.adapters.ai_classification.classifier import StructuredMaterialClassifier
from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.ai_grading.openai_provider import (
    NO_RESPONSE_STORAGE,
    OPENAI_BASE_URL,
)
from auto_scoring.adapters.ai_grading.openrouter_provider import (
    OPENROUTER_BASE_URL,
    ZERO_DATA_RETENTION_PROVIDER_PREFERENCE,
)
from auto_scoring.domain.material_classifier import ClassifierUnavailable, MaterialClassifier

_TRANSPORT_ENV_VAR = "AUTO_SCORING_AI_GRADING_TRANSPORT"

#: Transports that can carry an image and a JSON-schema constraint. Ordered
#: only for the message below; the actual order comes from the operator's own
#: priority list.
_IMAGE_CAPABLE_TRANSPORTS = ("gemini", "openrouter", "openai")

TokenSourceFactory = Callable[[str | None], AdcTokenSource]


def _default_token_source(project_id: str | None) -> AdcTokenSource:
    return AdcTokenSource(project_id=project_id)


def create_material_classifier(
    env: Mapping[str, str] | None = None,
    *,
    token_source_factory: TokenSourceFactory = _default_token_source,
) -> MaterialClassifier:
    """The classifier for this host.

    Raises :class:`ClassifierUnavailable` -- carrying a reason safe to show
    on screen -- when nothing usable is configured. Callers treat that as
    "offer the manual path", never as a hard failure: role rules still work,
    and a reviewer assigning roles by hand is the same act they perform to
    confirm a proposal.
    """
    values = env if env is not None else os.environ
    transports = [
        item.strip() for item in values.get(_TRANSPORT_ENV_VAR, "").split(",") if item.strip()
    ]
    if not transports:
        raise ClassifierUnavailable(
            f"{_TRANSPORT_ENV_VAR} is not set, so no AI classification is available on this host"
        )
    prompt_version = values.get("AUTO_SCORING_AI_GRADING_PROMPT_VERSION", "").strip()
    if not prompt_version:
        raise ClassifierUnavailable(
            "AUTO_SCORING_AI_GRADING_PROMPT_VERSION is required for AI classification"
        )

    for transport in transports:
        call = _build_call(transport, values, token_source_factory=token_source_factory)
        if call is not None:
            return StructuredMaterialClassifier(call, prompt_version=prompt_version)

    raise ClassifierUnavailable(
        f"none of the transports listed in {_TRANSPORT_ENV_VAR} can classify on this host; "
        f"AI classification needs one of {list(_IMAGE_CAPABLE_TRANSPORTS)} with credentials"
    )


def _build_call(
    transport: str,
    values: Mapping[str, str],
    *,
    token_source_factory: TokenSourceFactory,
) -> StructuredJsonCall | None:
    """One transport's call object, or ``None`` if it is unusable here."""
    if transport == "gemini":
        model = values.get("AUTO_SCORING_GEMINI_MODEL", "").strip()
        if not model:
            return None
        try:
            tokens = token_source_factory(
                values.get("AUTO_SCORING_VERTEX_PROJECT", "").strip() or None
            )
        except AdcCredentialsError:
            return None
        return VertexGeminiJsonCall(
            model=model,
            tokens=tokens,
            location=values.get("AUTO_SCORING_VERTEX_LOCATION", "").strip() or "global",
        )
    if transport == "openrouter":
        api_key = values.get("AUTO_SCORING_OPENROUTER_API_KEY", "").strip()
        model = values.get("AUTO_SCORING_OPENROUTER_MODEL", "").strip()
        if not api_key or not model:
            return None
        return ChatCompletionsJsonCall(
            provider="openrouter",
            api_key=api_key,
            model=model,
            base_url=OPENROUTER_BASE_URL,
            label="OpenRouter",
            # The same zero-data-retention routing preference the grading
            # adapter sends -- imported rather than restated, so the two
            # cannot drift: the material crossing this boundary is the
            # school's copyrighted work (Issue #95 decision 7 permits sending
            # it, not storing it elsewhere).
            extra_payload={"provider": ZERO_DATA_RETENTION_PROVIDER_PREFERENCE},
        )
    if transport == "openai":
        api_key = values.get("AUTO_SCORING_OPENAI_API_KEY", "").strip()
        model = values.get("AUTO_SCORING_OPENAI_MODEL", "").strip()
        if not api_key or not model:
            return None
        return ChatCompletionsJsonCall(
            provider="openai",
            api_key=api_key,
            model=model,
            base_url=OPENAI_BASE_URL,
            label="OpenAI",
            extra_payload=dict(NO_RESPONSE_STORAGE),
        )
    # `codex_app_server`, or an id this build does not know. Either way there
    # is no image-carrying call to make.
    return None
