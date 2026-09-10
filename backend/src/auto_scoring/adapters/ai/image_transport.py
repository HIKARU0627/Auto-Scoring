"""Choosing which image-capable transport this host can actually talk to
(Issue #125).

``AUTO_SCORING_AI_GRADING_TRANSPORT`` is one comma-separated priority list,
read by `adapters.ai_grading.factory` for grading and by all three
image-carrying adapters -- 採点基準の抽出, 回答欄の検出, 資料の分類 -- for
their own calls. Sharing the variable is deliberate and predates this module:
an operator who has configured grading has configured a vendor that can also
look at a page, and a second variable would only be a way for the two to
disagree.

What this module owns is everything those three then did identically: which
transports can be sent an image, which credential variable belongs to which
vendor, which base URL and per-request retention opt-out each one needs, and
"take the first entry that works here". What it deliberately does **not**
own is the sentence each adapter says when nothing works -- 採点基準が抽出
できない, 回答欄が検出できない and 分類できない are three different things to
tell a reviewer, and each factory still writes its own.

``codex_app_server`` is in :data:`KNOWN_TRANSPORTS` but not in
:data:`IMAGE_CAPABLE_TRANSPORTS`: its protocol carries no image input at all,
and every one of these three calls is about looking at a page. Leaving it in
the candidate list would guarantee one failed call before every run.

**No message this module produces may quote a configuration *value*.** All
three factories publish theirs (they become the ``reason`` an
``Unconfigured*`` adapter returns, which the app shows on screen), and a
value is whatever an operator typed -- which is how an API key pasted into
the wrong variable would reach a log. Only variable names and the fixed
transport ids written in this repository travel.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from auto_scoring.adapters.ai.image_call import (
    ChatCompletionsImageCall,
    ImageJsonCall,
    VertexGeminiImageCall,
)
from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.ai_grading.openai_provider import NO_RESPONSE_STORAGE, OPENAI_BASE_URL
from auto_scoring.adapters.ai_grading.openrouter_provider import (
    OPENROUTER_BASE_URL,
    ZERO_DATA_RETENTION_PROVIDER_PREFERENCE,
)

TRANSPORT_ENV_VAR = "AUTO_SCORING_AI_GRADING_TRANSPORT"

#: Transports that can be sent an image, in the order the grading chain
#: prefers them (Issue #81).
IMAGE_CAPABLE_TRANSPORTS = ("gemini", "openrouter", "openai")

#: Every transport id `adapters.ai_grading.factory` recognizes. Used only to
#: decide whether a listed value may be quoted back in a message: these are
#: literals written in this repository, so naming one publishes nothing --
#: while anything else in that variable is a value an operator typed.
KNOWN_TRANSPORTS = ("gemini", "codex_app_server", "openrouter", "openai")

TokenSourceFactory = Callable[[str | None], AdcTokenSource]


def default_token_source(project_id: str | None) -> AdcTokenSource:
    return AdcTokenSource(project_id=project_id)


class NoUsableTransport(Exception):
    """No entry in the priority list could be built here.

    :attr:`skipped` says why, one entry per transport tried, in the order
    they were tried -- variable names and fixed transport ids only. Each
    factory decides whether its own message quotes them.
    """

    def __init__(self, skipped: tuple[str, ...]) -> None:
        super().__init__("; ".join(skipped))
        self.skipped = skipped


class MissingCredentials(Exception):
    """One transport has no credentials here; try the next one. Carries only
    variable *names*."""


def transport_priority_list(values: Mapping[str, str]) -> tuple[str, ...]:
    """The configured priority order, blanks dropped. Empty when the variable
    is unset -- which each factory reports in its own words."""
    raw = values.get(TRANSPORT_ENV_VAR, "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def select_image_capable_call(
    transports: tuple[str, ...],
    values: Mapping[str, str],
    *,
    token_source_factory: TokenSourceFactory,
    schema_name: str,
    temperature: float,
    timeout_seconds: float,
) -> ImageJsonCall:
    """The first entry of ``transports`` that can carry an image and has
    credentials on this host.

    Raises :class:`NoUsableTransport` when none can. Never guesses a vendor
    or a model: every credential is read from its own variable, and a
    transport whose variable is unset is skipped rather than defaulted.

    ``token_source_factory`` is the one host probe made here (is there an ADC
    login?), injected for the reason ``docs/quality-gates.md`` records as
    "ホストを見る判定はテストへ注入する": whether ``gcloud`` has been logged
    into differs between a developer machine and a CI runner, and a test that
    cannot say which world it is in passes in one and fails in the other.
    """
    skipped: list[str] = []
    for transport in transports:
        if transport not in IMAGE_CAPABLE_TRANSPORTS:
            # Named, not silently dropped: an operator whose whole chain is
            # `codex_app_server` needs to know this is off *because of that*,
            # not because something is broken. Only a recognized id is
            # quoted -- see the module docstring.
            skipped.append(
                f"{transport} (no image input)"
                if transport in KNOWN_TRANSPORTS
                else "an unrecognized transport id"
            )
            continue
        try:
            return _build(
                transport,
                values,
                token_source_factory=token_source_factory,
                schema_name=schema_name,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
            )
        except MissingCredentials as exc:
            skipped.append(f"{transport} ({exc})")
    raise NoUsableTransport(tuple(skipped))


def _build(
    transport: str,
    values: Mapping[str, str],
    *,
    token_source_factory: TokenSourceFactory,
    schema_name: str,
    temperature: float,
    timeout_seconds: float,
) -> ImageJsonCall:
    if transport == "gemini":
        model = _require(values, "AUTO_SCORING_GEMINI_MODEL")
        try:
            tokens = token_source_factory(
                values.get("AUTO_SCORING_VERTEX_PROJECT", "").strip() or None
            )
        except AdcCredentialsError as exc:
            raise MissingCredentials(str(exc)) from None
        return VertexGeminiImageCall(
            model=model,
            tokens=tokens,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            location=values.get("AUTO_SCORING_VERTEX_LOCATION", "").strip() or "global",
        )
    if transport == "openrouter":
        return ChatCompletionsImageCall(
            provider="openrouter",
            api_key=_require(values, "AUTO_SCORING_OPENROUTER_API_KEY"),
            model=_require(values, "AUTO_SCORING_OPENROUTER_MODEL"),
            base_url=OPENROUTER_BASE_URL,
            label="OpenRouter",
            schema_name=schema_name,
            # The same zero-data-retention routing preference, and the same
            # ``store: false``, the grading adapters send -- imported rather
            # than restated, so the same material is treated the same way
            # whichever call sends it. Issue #95 decision 7 permits sending
            # it to the configured provider; it does not permit leaving
            # copies of it around.
            extra_payload={"provider": ZERO_DATA_RETENTION_PROVIDER_PREFERENCE},
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )
    return ChatCompletionsImageCall(
        provider="openai",
        api_key=_require(values, "AUTO_SCORING_OPENAI_API_KEY"),
        model=_require(values, "AUTO_SCORING_OPENAI_MODEL"),
        base_url=OPENAI_BASE_URL,
        label="OpenAI",
        schema_name=schema_name,
        extra_payload=dict(NO_RESPONSE_STORAGE),
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )


def _require(values: Mapping[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise MissingCredentials(f"{key} is not set")
    return value
