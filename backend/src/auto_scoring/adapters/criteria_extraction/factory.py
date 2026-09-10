"""Config-driven construction of the `CriteriaExtractor` (Issue #103).

**No new configuration.** `adapters.ai.image_transport` reads the same
``AUTO_SCORING_AI_GRADING_TRANSPORT`` priority list, and the same per-vendor
credentials, that ``adapters.ai_grading.factory`` already reads: an operator
who has configured grading has configured extraction, and a second variable
would only create a way for the two to disagree about which vendor this
install talks to.

Two deliberate differences from the grading chain:

* **``codex_app_server`` is skipped** -- it has no image input, and every
  measured criteria document needs one.
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
from collections.abc import Mapping

from auto_scoring.adapters.ai.image_transport import (
    IMAGE_CAPABLE_TRANSPORTS,
    TRANSPORT_ENV_VAR,
    NoUsableTransport,
    TokenSourceFactory,
    default_token_source,
    select_image_capable_call,
    transport_priority_list,
)
from auto_scoring.adapters.criteria_extraction.extractor import (
    DEFAULT_TIMEOUT_SECONDS,
    SCHEMA_NAME,
    StructuredCriteriaExtractor,
)
from auto_scoring.domain.criteria_extraction import CriteriaExtractor


class CriteriaExtractorConfigError(Exception):
    """No image-capable transport could be built on this host."""


def create_criteria_extractor(
    env: Mapping[str, str] | None = None,
    *,
    token_source_factory: TokenSourceFactory = default_token_source,
) -> CriteriaExtractor:
    """Build the first usable image-capable transport in the configured
    priority order.

    Raises :class:`CriteriaExtractorConfigError` when the transport list is
    unset, names no image-capable transport, or names only ones whose
    credentials are missing here. Never guesses a vendor or a model.
    """
    values = env if env is not None else os.environ
    transports = transport_priority_list(values)
    if not transports:
        raise CriteriaExtractorConfigError(
            f"{TRANSPORT_ENV_VAR} is required: a comma-separated priority list drawn from "
            f"{list(IMAGE_CAPABLE_TRANSPORTS)} (highest priority first)"
        )

    candidates = tuple(
        transport for transport in transports if transport in IMAGE_CAPABLE_TRANSPORTS
    )
    if not candidates:
        raise CriteriaExtractorConfigError(
            f"{TRANSPORT_ENV_VAR} lists no transport that accepts images; 採点基準の抽出には "
            f"{list(IMAGE_CAPABLE_TRANSPORTS)} のいずれかが必要です"
        )

    try:
        call = select_image_capable_call(
            candidates,
            values,
            token_source_factory=token_source_factory,
            schema_name=SCHEMA_NAME,
            temperature=_parse_temperature(values),
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        )
    except NoUsableTransport as exc:
        raise CriteriaExtractorConfigError(
            f"none of the image-capable transports listed in {TRANSPORT_ENV_VAR} have usable "
            f"credentials on this host: {'; '.join(exc.skipped)}"
        ) from None
    return StructuredCriteriaExtractor(call)


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
