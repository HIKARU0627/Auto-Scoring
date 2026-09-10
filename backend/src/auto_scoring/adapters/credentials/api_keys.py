"""What the settings screen edits, and how it reaches the provider chain
(Issue #96).

**The key never travels through `os.environ`.** The four provider factories
(`adapters.ai_grading.factory` and its three siblings) each take a
``Mapping[str, str]`` rather than reading the process environment themselves,
so a user-entered key reaches all of them by being *layered over* a copy of
the environment in the composition root -- one dict, built here, handed to
`api.sidecar.run`'s four ``build_*`` calls. Nothing mutates `os.environ`, and
so nothing this app spawns inherits the key: `adapters.ai_grading.
codex_app_server_provider` starts a `codex` child with a deliberately minimal
environment, and it stays minimal. That property is worth stating because the
obvious implementation -- `os.environ[...] = key` -- would have quietly given
it away (docs/sidecar-api.md section 6).

**Which layer wins, and why it differs per variable.** The credential store is
the *user's* answer to "what is my key"; the environment is a *developer's*
answer to "how is this machine set up". They are not competing statements
about the same thing, so:

* an API **key** from the credential store wins over the environment -- Issue
  #96 requires the sidecar to look at the store first and fall back to
  environment variables, so that a key typed into the screen is the one that
  gets used even on a machine that also has a ``.env.local``;
* the transport **priority order** does not move: `AUTO_SCORING_AI_GRADING_
  TRANSPORT` from the environment always wins, because Issue #96's decision
  says the development machines keep their Vertex-first order. This module
  only supplies an order when the environment names none -- which is exactly
  the distributed case, and there the default is OpenRouter.

Both of those are reported per-variable (`ApiKeySettings.sources`) so the
screen can say which layer each value came from rather than leaving the user
to guess why the key they typed does or does not appear to be in use.

**One provider, on purpose.** OpenRouter is the distributed default because
one key reaches many vendors' models, so the user has exactly one account to
create (Issue #96's decision). The table below is a table so a second entry
is a data change, not a redesign; it is not one yet because a second entry
means a second account for the user to sign up for and a second thing to
explain, and nobody has asked for that.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from auto_scoring.adapters.credentials.store import (
    CredentialStore,
    CredentialStoreUnavailableError,
)

TRANSPORT_VARIABLE: Final = "AUTO_SCORING_AI_GRADING_TRANSPORT"
PROMPT_VERSION_VARIABLE: Final = "AUTO_SCORING_AI_GRADING_PROMPT_VERSION"

#: The prompt-template tag a distributed install grades under when nothing
#: sets `AUTO_SCORING_AI_GRADING_PROMPT_VERSION` -- which is every installed
#: copy, since only a developer's ``.env.local`` sets it. It is *required*
#: configuration for the factory, so without a default here a user who
#: entered a perfectly good key would still be told grading is unconfigured.
#:
#: It has to stay equal to the value in ``.env.example``, which is the tag
#: `adapters.ai_grading._prompt` is bumped alongside; ``test_api_keys.py``
#: fails if the two drift, because a silently stale tag would pool results
#: from two different prompt templates under one name.
DEFAULT_PROMPT_VERSION: Final = "v3"

#: What `GET /grading/availability` says on a host that has simply not been
#: given a key yet. It replaces the factory's own message (which names
#: environment variables) only in that case -- see
#: :meth:`ApiKeySettings.missing_api_key_reason`. A person who has just
#: installed this app has no environment variables and cannot act on the
#: names of any.
NO_API_KEY_REASON: Final = (
    "AI 採点の API キーが未設定です。設定画面の「API キー」タブでキーを入力してください。"
    "取込・手動添削・PDF 出力は、キーが無くても使えます。"
)

#: Longest key any provider issues, with room to spare. A bound at the trust
#: boundary, so a paste accident cannot push megabytes into the credential
#: store (AGENTS.md "Security": validate every input that crosses one).
MAX_API_KEY_LENGTH: Final = 512


class InvalidApiKeyError(ValueError):
    """The submitted key is not something this app will store.

    Says what is wrong with the *shape* and never echoes the value.
    """


class ConfigurationSource(StrEnum):
    """Where an effective configuration value came from."""

    CREDENTIAL_STORE = "credential_store"
    ENVIRONMENT = "environment"
    #: This app's own built-in default, used where nothing else spoke.
    #: Spelled out rather than "default" because `default` is a reserved
    #: word in the generated Dart client and comes out as `default_`.
    DEFAULT = "builtin_default"
    NONE = "none"


@dataclass(frozen=True)
class ApiKeySlot:
    """One provider the user can hold an API key for."""

    id: str
    label: str
    #: The environment variable the provider factories read this key from.
    #: Also the entry name it is filed under in the credential store, so
    #: what Windows Credential Manager shows matches what the factories and
    #: the documentation call it.
    key_variable: str
    #: The transport id `AUTO_SCORING_AI_GRADING_TRANSPORT` uses.
    transport: str
    model_variable: str
    #: The model used when the environment names none. OpenRouter's own
    #: routing id, not a vendor SDK model name.
    default_model: str
    #: Where the user goes to create the key. Shown on the settings screen;
    #: a person who has never heard of OpenRouter needs it more than any
    #: wording on the field.
    console_url: str


API_KEY_SLOTS: Final[tuple[ApiKeySlot, ...]] = (
    ApiKeySlot(
        id="openrouter",
        label="OpenRouter",
        key_variable="AUTO_SCORING_OPENROUTER_API_KEY",
        transport="openrouter",
        model_variable="AUTO_SCORING_OPENROUTER_MODEL",
        default_model="google/gemini-2.5-flash",
        console_url="https://openrouter.ai/settings/keys",
    ),
)


@dataclass(frozen=True)
class ApiKeyStatus:
    """What the screen may know about one slot. **Never the value.**"""

    slot: ApiKeySlot
    configured: bool
    source: ConfigurationSource
    model: str
    model_source: ConfigurationSource


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def validate_api_key(value: str) -> str:
    """The submitted key, stripped, or raise :class:`InvalidApiKeyError`.

    Rejects a blank value, anything over :data:`MAX_API_KEY_LENGTH`, and any
    character outside printable ASCII. That last one is not cosmetic: the key
    is sent as an HTTP ``Authorization`` header, and a newline in a header
    value is a request-splitting primitive. httpx would refuse it too --
    catching it here means the user is told their paste picked up a line
    break instead of seeing a failure from three layers down.
    """
    stripped = value.strip()
    if not stripped:
        raise InvalidApiKeyError("API キーが空です。")
    if len(stripped) > MAX_API_KEY_LENGTH:
        raise InvalidApiKeyError(f"API キーが長すぎます（{MAX_API_KEY_LENGTH} 文字まで）。")
    if any(not (" " <= character <= "~") for character in stripped):
        raise InvalidApiKeyError(
            "API キーに使えない文字が含まれています。"
            "改行や全角文字が混ざっていないか確認してください。"
        )
    return stripped


class ApiKeySettings:
    """The credential store and this process's environment, read together.

    Built once in the composition root and shared by the settings endpoints
    and the startup wiring, so "what the screen reports" and "what the
    provider chain was actually built from" cannot drift apart.
    """

    def __init__(
        self,
        store: CredentialStore,
        environment: Mapping[str, str],
        *,
        slots: Iterable[ApiKeySlot] = API_KEY_SLOTS,
    ) -> None:
        self._store = store
        self._environment = dict(environment)
        self._slots = tuple(slots)
        self._changed_since_start = False

    @property
    def slots(self) -> tuple[ApiKeySlot, ...]:
        return self._slots

    @property
    def store_unavailable_reason(self) -> str | None:
        return self._store.unavailable_reason()

    @property
    def changed_since_start(self) -> bool:
        """Whether a key was saved or removed since this process started.

        The provider chain is built once, at startup, from whatever was
        stored then -- so this is exactly the question "is the running
        sidecar still the one this configuration describes?", and the screen
        turns it into a restart button. Tracking the edits this process made
        is precise in a way that comparing values would not be: a key
        replaced by a different key of the same length leaves every
        observable status identical.
        """
        return self._changed_since_start

    def slot(self, slot_id: str) -> ApiKeySlot | None:
        return next((slot for slot in self._slots if slot.id == slot_id), None)

    def key(self, slot: ApiKeySlot) -> tuple[str, ConfigurationSource] | None:
        """The key in force for ``slot`` and where it came from, if any.

        The credential store first, the environment second -- the order
        Issue #96 requires, so a key typed into the screen is the one that
        gets used even on a machine that also has a ``.env.local``.
        """
        candidates = (
            (self._store.get(slot.key_variable), ConfigurationSource.CREDENTIAL_STORE),
            (self._environment.get(slot.key_variable), ConfigurationSource.ENVIRONMENT),
        )
        for value, source in candidates:
            if not _blank(value):
                return str(value).strip(), source
        return None

    def status(self, slot: ApiKeySlot) -> ApiKeyStatus:
        resolved = self.key(slot)
        model = self._environment.get(slot.model_variable)
        return ApiKeyStatus(
            slot=slot,
            configured=resolved is not None,
            source=ConfigurationSource.NONE if resolved is None else resolved[1],
            model=slot.default_model if _blank(model) else str(model).strip(),
            model_source=(
                ConfigurationSource.DEFAULT if _blank(model) else ConfigurationSource.ENVIRONMENT
            ),
        )

    def statuses(self) -> tuple[ApiKeyStatus, ...]:
        return tuple(self.status(slot) for slot in self._slots)

    def save(self, slot: ApiKeySlot, value: str) -> str:
        """Store ``value`` for ``slot``; returns the stored form.

        Raises :class:`InvalidApiKeyError` for a value this app will not
        store and `store.CredentialStoreUnavailableError` when this host has
        nowhere to keep it. It never reports success for a save that did not
        happen -- a user who is told their key is kept and finds it gone at
        the next launch has been lied to about the one thing this screen is
        for.
        """
        validated = validate_api_key(value)
        self._store.set(slot.key_variable, validated)
        self._changed_since_start = True
        return validated

    def delete(self, slot: ApiKeySlot) -> None:
        self._store.delete(slot.key_variable)
        self._changed_since_start = True

    def transport_order(self) -> tuple[str, ConfigurationSource]:
        """The provider priority list in force, and where it came from."""
        configured = self._environment.get(TRANSPORT_VARIABLE)
        if not _blank(configured):
            return str(configured).strip(), ConfigurationSource.ENVIRONMENT
        usable = ",".join(slot.transport for slot in self._slots if self.key(slot) is not None)
        if usable:
            return usable, ConfigurationSource.DEFAULT
        return "", ConfigurationSource.NONE

    def effective_environment(self) -> dict[str, str]:
        """A copy of this process's environment with the stored keys layered
        over it -- what the four provider factories are built from.

        A copy, never `os.environ` itself: see the module docstring for what
        mutating the real environment would give away.
        """
        values = dict(self._environment)
        for slot in self._slots:
            resolved = self.key(slot)
            if resolved is None:
                continue
            values[slot.key_variable] = resolved[0]
            if _blank(values.get(slot.model_variable)):
                values[slot.model_variable] = slot.default_model
        transport, source = self.transport_order()
        if transport and source is ConfigurationSource.DEFAULT:
            values[TRANSPORT_VARIABLE] = transport
        if transport and _blank(values.get(PROMPT_VERSION_VARIABLE)):
            values[PROMPT_VERSION_VARIABLE] = DEFAULT_PROMPT_VERSION
        return values

    def missing_api_key_reason(self) -> str | None:
        """:data:`NO_API_KEY_REASON` when this host has no AI configuration
        at all, and ``None`` when it has some.

        The distinction matters because the factory's own message names
        environment variables. On a developer machine that names a transport
        and got the credentials wrong, that message is the useful one and is
        left alone. On a freshly installed copy, where nothing is set
        because nothing has been entered yet, it is noise -- the honest
        answer is "no key yet, here is where to put one".
        """
        if not _blank(self._environment.get(TRANSPORT_VARIABLE)):
            return None
        if any(self.key(slot) is not None for slot in self._slots):
            return None
        return NO_API_KEY_REASON

    def describe_sources(self) -> str:
        """One log line's worth of "where did this come from", value-free."""
        transport, transport_source = self.transport_order()
        rendered = ", ".join(
            f"{status.slot.id}={status.source.value}" for status in self.statuses()
        )
        order = transport or "(none)"
        return (
            f"API keys: {rendered or 'none'}; transport order {order} from {transport_source.value}"
        )


__all__ = [
    "API_KEY_SLOTS",
    "DEFAULT_PROMPT_VERSION",
    "MAX_API_KEY_LENGTH",
    "NO_API_KEY_REASON",
    "PROMPT_VERSION_VARIABLE",
    "TRANSPORT_VARIABLE",
    "ApiKeySettings",
    "ApiKeySlot",
    "ApiKeyStatus",
    "ConfigurationSource",
    "CredentialStoreUnavailableError",
    "InvalidApiKeyError",
    "validate_api_key",
]
