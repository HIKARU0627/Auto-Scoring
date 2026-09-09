"""Config-driven construction of the `OCRProvider` (Issue #114).

**One variable.** ``AUTO_SCORING_DOCUMENT_AI_PROCESSOR`` holds the full
processor resource name Cloud Console shows,
``projects/<p>/locations/<l>/processors/<id>``. Project, location and
processor id have to agree -- a processor only exists in the location it was
created in -- so three separate variables would only create a way for an
operator to make them disagree, and "is OCR configured on this host?" would
stop being a single question (decided with the project owner, Issue #114).

**No API key, ever.** Document AI is reached with Application Default
Credentials: the project owner's Google Cloud organization policy forbids API
keys outright, which is the same constraint `adapters.ai_grading._google_adc`
documents for Vertex AI. That is also why the project id never has to be
configured separately -- it is inside the resource name, and ADC resolves its
own quota project at runtime.

Only ``AUTO_SCORING_VERTEX_PROJECT`` is read besides, and only to pick which
project ADC bills the token to -- the exact same override the three Vertex AI
callers already use, so a host that configured grading has already configured
this.

Every message this module produces is published (it becomes
`adapters.ocr.unconfigured_provider.UnconfiguredOCRProvider.reason`, which
``GET /ocr/availability`` returns and the sidecar log records), so it names
configuration *variables* only, never their values -- the rule
`adapters.ai_grading.factory` states for its counterpart and
``tests/test_ocr_availability.py`` enforces here.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.ocr.document_ai_provider import DocumentAiOCRProvider
from auto_scoring.domain.ocr import OCRProvider

_PROCESSOR_ENV_VAR = "AUTO_SCORING_DOCUMENT_AI_PROCESSOR"
_PROJECT_ENV_VAR = "AUTO_SCORING_VERTEX_PROJECT"

TokenSourceFactory = Callable[[str | None], AdcTokenSource]


class OCRProviderConfigError(Exception):
    """No OCR provider could be built on this host. Carries variable *names* only."""


def _default_token_source(project_id: str | None) -> AdcTokenSource:
    return AdcTokenSource(project_id=project_id)


def create_ocr_provider(
    env: Mapping[str, str] | None = None,
    *,
    token_source_factory: TokenSourceFactory = _default_token_source,
) -> OCRProvider:
    """Build the Document AI adapter for this host.

    Raises :class:`OCRProviderConfigError` when the processor is not
    configured, is not a processor resource name, or when this host has no
    Application Default Credentials. Callers turn that into
    `adapters.ocr.unconfigured_provider.UnconfiguredOCRProvider` so the app
    still starts and still grades -- simplified-design-specification.md
    section 24: "OCR失敗: **採点は止めない。**"

    ``token_source_factory`` is the one host probe this function makes,
    injected so a test states which world it is in rather than inheriting
    whatever the machine happens to have (AGENTS.md "Architecture").
    """
    values = env if env is not None else os.environ
    processor = values.get(_PROCESSOR_ENV_VAR, "").strip()
    if not processor:
        raise OCRProviderConfigError(
            f"{_PROCESSOR_ENV_VAR} is not set: the full Document AI processor resource name, "
            "projects/<project>/locations/<location>/processors/<id>"
        )
    try:
        tokens = token_source_factory(values.get(_PROJECT_ENV_VAR, "").strip() or None)
    except AdcCredentialsError as exc:
        raise OCRProviderConfigError(str(exc)) from None
    try:
        return DocumentAiOCRProvider(processor=processor, tokens=tokens)
    except ValueError:
        # `DocumentAiOCRProvider` validates the resource name at construction.
        # Its own message is repeated here rather than interpolated, so no
        # part of the operator's value can reach a published string even if
        # that message changes.
        raise OCRProviderConfigError(
            f"{_PROCESSOR_ENV_VAR} is not a Document AI processor resource name; it must look "
            "like projects/<project>/locations/<location>/processors/<id>"
        ) from None
