"""Config-driven construction of the `AnswerAreaDetector` (Issue #105).

**No new configuration.** This reads the same
``AUTO_SCORING_AI_GRADING_TRANSPORT`` priority list, and the same per-vendor
credentials, that ``adapters.ai_grading.factory`` already reads: an operator
who has configured grading has configured detection, and a second variable
would only create a way for the two to disagree about which vendor this
install talks to.

Two deliberate differences from the grading chain:

* **``codex_app_server`` is skipped.** Its protocol has no image input, and
  the page image is the only input detection has (all 11 measured 生徒答案
  PDFs have an empty text layer). Leaving it in the list would guarantee one
  failed call before every detection.
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
from collections.abc import Callable, Mapping

from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.answer_area_detection.detector import (
    ChatCompletionsAnswerAreaDetector,
    VertexGeminiAnswerAreaDetector,
)
from auto_scoring.domain.answer_area_detection import AnswerAreaDetector

_TRANSPORT_ENV_VAR = "AUTO_SCORING_AI_GRADING_TRANSPORT"

#: Transports that can be sent an image, in the order the grading chain
#: prefers them (Issue #81). ``codex_app_server`` is absent on purpose -- see
#: the module docstring.
_IMAGE_CAPABLE_TRANSPORTS = ("gemini", "openrouter", "openai")

#: Every transport id `adapters.ai_grading.factory` recognizes. Used only to
#: decide whether a listed value may be quoted back in a message: these are
#: literals written in this repository, so naming one publishes nothing --
#: while anything else in that variable is a *value* an operator typed, and a
#: value can be an API key pasted into the wrong variable.
_KNOWN_TRANSPORTS = ("gemini", "codex_app_server", "openrouter", "openai")

_OPENAI_BASE_URL = "https://api.openai.com/v1"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

#: Per-request retention opt-outs, copied from the grading adapters so the
#: same material is treated the same way whichever call sends it. OpenAI's
#: ``store: false`` keeps the request out of the account's logs; OpenRouter's
#: two routing fields restrict the request to upstreams that neither train on
#: nor retain it. Issue #95 decision 7 permits sending this material to the
#: configured provider; it does not permit leaving copies of it around.
_OPENAI_EXTRA: dict[str, object] = {"store": False}
_OPENROUTER_EXTRA: dict[str, object] = {"provider": {"data_collection": "deny", "zdr": True}}

TokenSourceFactory = Callable[[str | None], AdcTokenSource]


class AnswerAreaDetectorConfigError(Exception):
    """No image-capable transport could be built on this host."""


def _default_token_source(project_id: str | None) -> AdcTokenSource:
    return AdcTokenSource(project_id=project_id)


def create_answer_area_detector(
    env: Mapping[str, str] | None = None,
    *,
    token_source_factory: TokenSourceFactory = _default_token_source,
) -> AnswerAreaDetector:
    """Build the first image-capable, credentialed transport named by
    ``AUTO_SCORING_AI_GRADING_TRANSPORT``.

    Raises :class:`AnswerAreaDetectorConfigError` when the variable is unset,
    lists no image-capable transport, or lists only ones whose credentials
    are missing here. Callers turn that into
    `domain.answer_area_detection.UnconfiguredAnswerAreaDetector` so the
    screen still opens and says why -- the reviewer can always draw the boxes
    by hand.

    ``token_source_factory`` is the one host probe this function makes,
    injected so a test states which world it is in rather than inheriting
    whatever the machine happens to have (AGENTS.md "Architecture").
    """
    values = env if env is not None else os.environ
    raw = values.get(_TRANSPORT_ENV_VAR, "")
    transports = [item.strip() for item in raw.split(",") if item.strip()]
    if not transports:
        raise AnswerAreaDetectorConfigError(
            f"{_TRANSPORT_ENV_VAR} is required: a comma-separated priority list. Answer-area "
            f"detection needs an image-capable transport, one of {list(_IMAGE_CAPABLE_TRANSPORTS)}"
        )

    skipped: list[str] = []
    for transport in transports:
        if transport not in _IMAGE_CAPABLE_TRANSPORTS:
            # Named, not silently dropped: an operator whose whole chain is
            # `codex_app_server` needs to know detection is off *because of
            # that*, not because something is broken.
            #
            # Only a *recognized* id is quoted, though. An unrecognized entry
            # is whatever the operator typed into the variable -- which is how
            # an API key pasted into the wrong one would end up on screen and
            # in the log (the leak `adapters.ai_grading.factory` fixed for its
            # own message, and what `test_answer_area_detector_factory`'s
            # sentinel matrix catches here).
            skipped.append(
                f"{transport} (no image input)"
                if transport in _KNOWN_TRANSPORTS
                else "an unrecognized transport id"
            )
            continue
        try:
            return _build(transport, values, token_source_factory=token_source_factory)
        except _MissingCredentials as exc:
            skipped.append(f"{transport} ({exc})")

    raise AnswerAreaDetectorConfigError(
        f"none of the transports listed in {_TRANSPORT_ENV_VAR} can detect answer areas on this "
        f"host: {'; '.join(skipped)}"
    )


class _MissingCredentials(Exception):
    """One transport has no credentials here. Carries variable *names* only."""


def _build(
    transport: str,
    values: Mapping[str, str],
    *,
    token_source_factory: TokenSourceFactory,
) -> AnswerAreaDetector:
    if transport == "gemini":
        model = _require_credential(values, "AUTO_SCORING_GEMINI_MODEL")
        try:
            tokens = token_source_factory(
                values.get("AUTO_SCORING_VERTEX_PROJECT", "").strip() or None
            )
        except AdcCredentialsError as exc:
            raise _MissingCredentials(str(exc)) from None
        return VertexGeminiAnswerAreaDetector(
            model=model,
            tokens=tokens,
            location=values.get("AUTO_SCORING_VERTEX_LOCATION", "").strip() or "global",
        )
    if transport == "openrouter":
        return ChatCompletionsAnswerAreaDetector(
            name="openrouter",
            api_key=_require_credential(values, "AUTO_SCORING_OPENROUTER_API_KEY"),
            model=_require_credential(values, "AUTO_SCORING_OPENROUTER_MODEL"),
            base_url=_OPENROUTER_BASE_URL,
            label="OpenRouter",
            extra_payload=dict(_OPENROUTER_EXTRA),
        )
    return ChatCompletionsAnswerAreaDetector(
        name="openai",
        api_key=_require_credential(values, "AUTO_SCORING_OPENAI_API_KEY"),
        model=_require_credential(values, "AUTO_SCORING_OPENAI_MODEL"),
        base_url=_OPENAI_BASE_URL,
        label="OpenAI",
        extra_payload=dict(_OPENAI_EXTRA),
    )


def _require_credential(values: Mapping[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise _MissingCredentials(f"{key} is not set")
    return value
