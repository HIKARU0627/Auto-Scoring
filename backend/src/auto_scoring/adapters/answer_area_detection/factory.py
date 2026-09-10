"""Config-driven construction of the `AnswerAreaDetector` (Issue #105).

**No new configuration.** `adapters.ai.image_transport` reads the same
``AUTO_SCORING_AI_GRADING_TRANSPORT`` priority list, and the same per-vendor
credentials, that ``adapters.ai_grading.factory`` already reads: an operator
who has configured grading has configured detection, and a second variable
would only create a way for the two to disagree about which vendor this
install talks to.

Two deliberate differences from the grading chain:

* **``codex_app_server`` is skipped** -- it has no image input, and the page
  image is the only input detection has.
* **No fallback chain -- the first usable transport wins.** Detection is a
  single action a person starts from a screen and watches; a failure lands in
  front of them with a reason and a button to press again.
  `FallbackAIProvider` exists for the unattended grading queue, where nobody
  is watching, and borrowing it here would spend a second vendor's quota on a
  call the reviewer is about to retry anyway.

Every message this module produces is published (it becomes
`UnconfiguredAnswerAreaDetector.reason`, which the detect endpoint returns and
the app displays), so it names configuration *variables* only, never their
values -- the rule ``adapters.ai_grading.factory``'s docstring states and
``tests/test_grading_availability.py`` enforces for its counterpart.
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
from auto_scoring.adapters.answer_area_detection.detector import (
    DEFAULT_TIMEOUT_SECONDS,
    SCHEMA_NAME,
    StructuredAnswerAreaDetector,
)
from auto_scoring.domain.answer_area_detection import AnswerAreaDetector


class AnswerAreaDetectorConfigError(Exception):
    """No image-capable transport could be built on this host."""


def create_answer_area_detector(
    env: Mapping[str, str] | None = None,
    *,
    token_source_factory: TokenSourceFactory = default_token_source,
) -> AnswerAreaDetector:
    """Build the first image-capable, credentialed transport named by
    ``AUTO_SCORING_AI_GRADING_TRANSPORT``.

    Raises :class:`AnswerAreaDetectorConfigError` when the variable is unset,
    lists no image-capable transport, or lists only ones whose credentials
    are missing here. Callers turn that into
    `domain.answer_area_detection.UnconfiguredAnswerAreaDetector` so the
    screen still opens and says why -- the reviewer can always draw the boxes
    by hand.
    """
    values = env if env is not None else os.environ
    transports = transport_priority_list(values)
    if not transports:
        raise AnswerAreaDetectorConfigError(
            f"{TRANSPORT_ENV_VAR} is required: a comma-separated priority list. Answer-area "
            f"detection needs an image-capable transport, one of {list(IMAGE_CAPABLE_TRANSPORTS)}"
        )

    try:
        call = select_image_capable_call(
            transports,
            values,
            token_source_factory=token_source_factory,
            schema_name=SCHEMA_NAME,
            temperature=0.0,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        )
    except NoUsableTransport as exc:
        raise AnswerAreaDetectorConfigError(
            f"none of the transports listed in {TRANSPORT_ENV_VAR} can detect answer areas on "
            f"this host: {'; '.join(exc.skipped)}"
        ) from None
    return StructuredAnswerAreaDetector(call)
