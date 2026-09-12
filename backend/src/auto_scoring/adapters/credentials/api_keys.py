"""What the settings screen edits, and how it reaches the provider chain
(Issues #96, #386).

**The key never travels through `os.environ`.** The provider factories
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
the *user's* answer to "what key is mine"; the environment is a *developer's*
answer to "how is this machine set up". They are not competing statements
about the same thing, so:

* an API **key** from the credential store wins over the environment -- Issue
  #96 requires the sidecar to look at the store first and fall back to
  environment variables, so that a key typed into the screen is the one that
  gets used even on a machine that also has a ``.env.local``;
* the transport **priority order** follows the same shape (Issue #386): a
  saved order wins over the environment, and the environment wins over the
  order derived from which slots have usable configuration. Issue #96 kept the
  environment on top so the development machines' Vertex-first order would not
  move; Issue #386's owner asked to reorder from the screen, and an order the
  screen accepts but the chain ignores is worse than no control at all. The
  #96 guarantee is not lost: the screen has a "revert to the environment"
  action, and a machine that never saves an order behaves exactly as before
  (no stored order means the environment still decides).

Both of those are reported per-variable (`ProviderStatus.sources`) so the
screen can say which layer each value came from rather than leaving the user
to guess why the value they entered does or does not appear to be in use.

**Providers, and the two kinds of value they hold (Issue #386).** A provider
either holds an API **key** (OpenRouter, OpenAI) or reaches its vendor with
credentials that are *not* a key and cannot be typed into this screen:
Gemini is reached through Vertex AI, authenticated with Application Default
Credentials, because the project's Google Cloud organization policy forbids
Gemini API keys (`_google_adc`); Codex app-server reuses the operator's own
``codex login`` session. So a slot has, at most, one secret key (never read
back) plus any number of *text* settings (model, GCP project, region) that
**are** read back -- there is nothing secret about them and hiding them would
only make the screen useless. This is why the old one-slot table became a
table of slots: Issue #96 shipped OpenRouter alone so a distributed user had
exactly one account to create, and the owner asked on 2026-09-12 for the other
providers and for the use order (Issue #386).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from auto_scoring.adapters.credentials.store import (
    CredentialStore,
    CredentialStoreUnavailableError,
)

TRANSPORT_VARIABLE: Final = "AUTO_SCORING_AI_GRADING_TRANSPORT"
PROMPT_VERSION_VARIABLE: Final = "AUTO_SCORING_AI_GRADING_PROMPT_VERSION"

#: Transport ids in the priority order Issue #81 adopted. Used for validation
#: messages and as the canonical set the screen offers when reordering --
#: `API_KEY_SLOTS` carries the same four, but in screen order, not priority
#: order.
KNOWN_TRANSPORTS: Final[tuple[str, ...]] = (
    "gemini",
    "codex_app_server",
    "openrouter",
    "openai",
)

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

#: Longest non-secret setting (a model id, a GCP project id, a region). Also a
#: trust-boundary bound, and generous enough for any of the three.
MAX_SETTING_LENGTH: Final = 256


class InvalidApiKeyError(ValueError):
    """The submitted key is not something this app will store.

    Says what is wrong with the *shape* and never echoes the value.
    """


class InvalidSettingError(ValueError):
    """A non-secret setting is not something this app will store.

    Same rule as :class:`InvalidApiKeyError`: shape only, never the value.
    """


class InvalidTransportOrderError(ValueError):
    """A submitted use order is not a priority list this app will accept.

    Names the supported transport ids -- which are public -- and never quotes
    what the caller sent, the same discipline the factory applies to its own
    configuration errors.
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
class TextSetting:
    """One non-secret, readable-back value belonging to a provider slot."""

    variable: str
    label: str
    default: str = ""
    placeholder: str = ""
    help_text: str = ""


@dataclass(frozen=True)
class ApiKeySlot:
    """One provider the user can configure."""

    id: str
    label: str
    #: The environment variable the provider factories read this key from, and
    #: the entry name it is filed under in the credential store, so what
    #: Windows Credential Manager shows matches what the factories and the
    #: documentation call it. ``None`` for a provider that holds no key here
    #: at all (Vertex AI/ADC, Codex app-server).
    key_variable: str | None
    #: The transport id `AUTO_SCORING_AI_GRADING_TRANSPORT` uses.
    transport: str
    model_variable: str
    #: The model used when the environment names none. OpenRouter's own
    #: routing id, not a vendor SDK model name.
    default_model: str
    #: Where the user goes to create the key. Shown on the settings screen;
    #: an empty string when there is no key to create (Vertex, Codex).
    console_url: str
    #: Non-secret settings beyond the model (a GCP project id, a region),
    #: each readable back.
    text_settings: tuple[TextSetting, ...] = ()
    #: One fixed sentence about how this provider authenticates, with no
    #: configuration value in it. Rendered next to the slot.
    auth_note: str = ""

    @property
    def has_key(self) -> bool:
        return self.key_variable is not None

    def text_setting(self, variable: str) -> TextSetting | None:
        return next((item for item in self.text_settings if item.variable == variable), None)


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
    ApiKeySlot(
        id="openai",
        label="OpenAI",
        key_variable="AUTO_SCORING_OPENAI_API_KEY",
        transport="openai",
        model_variable="AUTO_SCORING_OPENAI_MODEL",
        default_model="gpt-4o-mini",
        console_url="https://platform.openai.com/api-keys",
    ),
    ApiKeySlot(
        id="gemini",
        label="Gemini（Vertex AI）",
        key_variable=None,
        transport="gemini",
        model_variable="AUTO_SCORING_GEMINI_MODEL",
        default_model="gemini-2.5-flash",
        console_url="https://console.cloud.google.com/vertex-ai",
        text_settings=(
            TextSetting(
                variable="AUTO_SCORING_VERTEX_PROJECT",
                label="GCP プロジェクト ID",
                placeholder="my-gcp-project",
                help_text="省略可。ADC が解決する課金先と分けたいときだけ入力します。",
            ),
            TextSetting(
                variable="AUTO_SCORING_VERTEX_LOCATION",
                label="リージョン",
                default="global",
                placeholder="global",
                help_text="省略時は global。リージョンを指定するとそのホスト名になります。",
            ),
        ),
        auth_note=(
            "認証は API キーではなく Application Default Credentials（ADC）です。"
            "`gcloud auth application-default login` を先に実行してください。"
        ),
    ),
    ApiKeySlot(
        id="codex_app_server",
        label="Codex App Server",
        key_variable=None,
        transport="codex_app_server",
        model_variable="AUTO_SCORING_CODEX_MODEL",
        #: Empty: Codex falls back to its own default model, and the factory
        #: treats a blank value as "not set".
        default_model="",
        console_url="",
        auth_note=("この PC の Codex CLI のログインセッションを使います。API キーは保存しません。"),
    ),
)


@dataclass(frozen=True)
class ModelStatus:
    """What the screen may know about the model setting. **Never a key.**"""

    value: str
    source: ConfigurationSource


@dataclass(frozen=True)
class TextSettingStatus:
    """One readable-back setting: its effective value and where it came from."""

    setting: TextSetting
    value: str
    source: ConfigurationSource


@dataclass(frozen=True)
class ApiKeyStatus:
    """What the screen may know about one slot. **Never the key's value.**"""

    slot: ApiKeySlot
    #: Whether this provider can be built here at all. For a key slot that is
    #: "a key is in force"; for Vertex/Codex, where the credential is a host
    #: fact, it is the host probe when one was injected and True (unknown but
    #: attemptable) otherwise.
    configured: bool
    source: ConfigurationSource
    model: str
    model_source: ConfigurationSource
    #: The non-model readable settings (GCP project id, region).
    text_settings: tuple[TextSettingStatus, ...] = ()
    #: `None` when no host probe was injected, so the screen says "verify to
    #: find out" rather than guessing. `True`/`False` for Vertex (ADC) and
    #: Codex (the CLI on this host) once a probe is wired in.
    host_available: bool | None = None


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


def validate_setting_value(value: str) -> str:
    """A non-secret setting, stripped, or raise :class:`InvalidSettingError`.

    Same shape rules as :func:`validate_api_key` minus the credential
    specific wording: model ids, project ids and regions are all printable
    ASCII, and the same newline argument applies (a value here can reach an
    HTTP URL or a subprocess argument).
    """
    stripped = value.strip()
    if len(stripped) > MAX_SETTING_LENGTH:
        raise InvalidSettingError(f"設定値が長すぎます（{MAX_SETTING_LENGTH} 文字まで）。")
    if any(not (" " <= character <= "~") for character in stripped):
        raise InvalidSettingError(
            "設定値に使えない文字が含まれています。改行や全角文字が混ざっていないか確認してください。"
        )
    return stripped


def validate_transport_order(transports: Sequence[str]) -> tuple[str, ...]:
    """A submitted use order as a validated tuple, or raise.

    A transport that is not one of :data:`KNOWN_TRANSPORTS` is rejected by
    count, not by quoting the entry (the factory's own discipline: a value is
    never published). A repeat is rejected because a silently de-duplicated
    list would leave the user believing a provider they named twice is tried
    twice.
    """
    cleaned = tuple(item.strip() for item in transports if item.strip())
    if not cleaned:
        raise InvalidTransportOrderError(
            f"使用順序が空です。対応する transport は {list(KNOWN_TRANSPORTS)} です。"
        )
    unknown = [item for item in cleaned if item not in KNOWN_TRANSPORTS]
    if unknown:
        raise InvalidTransportOrderError(
            f"使用順序に未対応の transport が {len(unknown)} 件あります。"
            f"対応する値は {list(KNOWN_TRANSPORTS)} です。"
        )
    if len(set(cleaned)) != len(cleaned):
        raise InvalidTransportOrderError("使用順序に同じ transport が2回入っています。")
    return cleaned


class ApiKeySettings:
    """The credential store and this process's environment, read together.

    Built once in the composition root and shared by the settings endpoints
    and the startup wiring, so "what the screen reports" and "what the
    provider chain was actually built from" cannot drift apart.

    ``vertex_auth_available`` and ``codex_available`` are the two host probes
    this class makes (ADC resolvable for the configured project; the Codex CLI
    installed). Both are injected for the reason every boundary is: a test
    states which world it is in rather than inheriting the machine's, and the
    schema export passes neither and gets ``None`` -- "unknown" -- instead of
    touching a real ``gcloud`` or ``codex``.
    """

    def __init__(
        self,
        store: CredentialStore,
        environment: Mapping[str, str],
        *,
        slots: Iterable[ApiKeySlot] = API_KEY_SLOTS,
        vertex_auth_available: Callable[[str | None], bool] | None = None,
        codex_available: Callable[[], bool] | None = None,
    ) -> None:
        self._store = store
        self._environment = dict(environment)
        self._slots = tuple(slots)
        self._vertex_auth_available = vertex_auth_available
        self._codex_available = codex_available
        self._changed_since_start = False

    @property
    def slots(self) -> tuple[ApiKeySlot, ...]:
        return self._slots

    @property
    def store_unavailable_reason(self) -> str | None:
        return self._store.unavailable_reason()

    @property
    def changed_since_start(self) -> bool:
        """Whether a value was saved or removed since this process started.

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
        gets used even on a machine that also has a ``.env.local``. A slot
        that holds no key (Vertex, Codex) always answers ``None``.
        """
        if slot.key_variable is None:
            return None
        candidates = (
            (self._store.get(slot.key_variable), ConfigurationSource.CREDENTIAL_STORE),
            (self._environment.get(slot.key_variable), ConfigurationSource.ENVIRONMENT),
        )
        for value, source in candidates:
            if not _blank(value):
                return str(value).strip(), source
        return None

    def setting(self, slot: ApiKeySlot, setting: TextSetting) -> TextSettingStatus:
        """The effective value of one readable setting and its source."""
        candidates = (
            (self._store.get(setting.variable), ConfigurationSource.CREDENTIAL_STORE),
            (self._environment.get(setting.variable), ConfigurationSource.ENVIRONMENT),
        )
        for value, source in candidates:
            if not _blank(value):
                return TextSettingStatus(setting, str(value).strip(), source)
        if not _blank(setting.default):
            return TextSettingStatus(setting, setting.default, ConfigurationSource.DEFAULT)
        return TextSettingStatus(setting, "", ConfigurationSource.NONE)

    def _model(self, slot: ApiKeySlot) -> TextSettingStatus:
        return self.setting(
            slot,
            TextSetting(
                variable=slot.model_variable,
                label="モデル",
                default=slot.default_model,
            ),
        )

    def _readable_statuses(self, slot: ApiKeySlot) -> Iterable[TextSettingStatus]:
        yield self._model(slot)
        for item in slot.text_settings:
            yield self.setting(slot, item)

    def _host_available(self, slot: ApiKeySlot) -> bool | None:
        if slot.transport == "gemini" and self._vertex_auth_available is not None:
            project = self.setting(
                slot,
                next(
                    item
                    for item in slot.text_settings
                    if item.variable == "AUTO_SCORING_VERTEX_PROJECT"
                ),
            ).value
            return self._vertex_auth_available(project or None)
        if slot.transport == "codex_app_server" and self._codex_available is not None:
            return self._codex_available()
        return None

    def status(self, slot: ApiKeySlot) -> ApiKeyStatus:
        resolved = self.key(slot)
        model = self._model(slot)
        host_available = self._host_available(slot)
        if slot.key_variable is None:
            configured = host_available is not False
        else:
            configured = resolved is not None
        return ApiKeyStatus(
            slot=slot,
            configured=configured,
            source=ConfigurationSource.NONE if resolved is None else resolved[1],
            model=model.value,
            model_source=model.source,
            text_settings=tuple(self.setting(slot, item) for item in slot.text_settings),
            host_available=host_available,
        )

    def statuses(self) -> tuple[ApiKeyStatus, ...]:
        return tuple(self.status(slot) for slot in self._slots)

    def resolved_settings(self, slot: ApiKeySlot) -> dict[str, str]:
        """Every value in force for ``slot``, for the verifier only.

        Includes the key when there is one. Never returned to a client; the
        settings response model never carries a secret (see
        `api.settings_router`).
        """
        values: dict[str, str] = {}
        resolved = self.key(slot)
        if resolved is not None:
            values[slot.key_variable or ""] = resolved[0]
        model = self._model(slot)
        if model.value:
            values[slot.model_variable] = model.value
        for item in slot.text_settings:
            status = self.setting(slot, item)
            if status.value:
                values[item.variable] = status.value
        return values

    def save(self, slot: ApiKeySlot, value: str) -> str:
        """Store ``value`` as ``slot``'s key; returns the stored form.

        Raises :class:`InvalidApiKeyError` for a value this app will not
        store, :class:`InvalidSettingError` for a slot with no key, and
        `store.CredentialStoreUnavailableError` when this host has nowhere to
        keep it. It never reports success for a save that did not happen -- a
        user who is told their key is kept and finds it gone at the next
        launch has been lied to about the one thing this screen is for.
        """
        if slot.key_variable is None:
            raise InvalidSettingError("この提供元には API キーの項目がありません。")
        validated = validate_api_key(value)
        self._store.set(slot.key_variable, validated)
        self._changed_since_start = True
        return validated

    def delete(self, slot: ApiKeySlot) -> None:
        if slot.key_variable is None:
            return
        self._store.delete(slot.key_variable)
        self._changed_since_start = True

    def save_settings(self, slot: ApiKeySlot, values: Mapping[str, str | None]) -> tuple[str, ...]:
        """Store the submitted values for ``slot``; return the secret ones.

        ``values`` may name the slot's key (validated as a credential) and any
        of its readable settings (validated as text). A blank or ``None``
        value clears what was stored, so the environment -- or the built-in
        default -- takes over again, rather than storing an empty string. An
        unknown variable is refused as a shape error.

        The returned secret values are what the caller registers with
        `api.secret_redaction.SecretRegistry`; they are never returned to a
        client.
        """
        secret_variables = {slot.key_variable} if slot.key_variable is not None else set()
        allowed = {slot.model_variable, *(item.variable for item in slot.text_settings)}
        stored_secrets: list[str] = []
        for variable, raw in values.items():
            if variable not in allowed and variable not in secret_variables:
                raise InvalidSettingError("この提供元に無い設定項目です。")
            if _blank(raw):
                self._store.delete(variable)
            else:
                if variable in secret_variables:
                    validated = validate_api_key(str(raw))
                    stored_secrets.append(validated)
                else:
                    validated = validate_setting_value(str(raw))
                self._store.set(variable, validated)
            self._changed_since_start = True
        return tuple(stored_secrets)

    def clear_settings(self, slot: ApiKeySlot) -> None:
        """Remove every stored value for ``slot`` (key and readable ones)."""
        if slot.key_variable is not None:
            self._store.delete(slot.key_variable)
        self._store.delete(slot.model_variable)
        for item in slot.text_settings:
            self._store.delete(item.variable)
        self._changed_since_start = True

    def transport_order(self) -> tuple[str, ConfigurationSource]:
        """The provider priority list in force, and where it came from.

        Stored order first, then the environment, then the transports of the
        slots that are usable here -- in the order the slots are declared.
        """
        stored = self._store.get(TRANSPORT_VARIABLE)
        if not _blank(stored):
            return str(stored).strip(), ConfigurationSource.CREDENTIAL_STORE
        configured = self._environment.get(TRANSPORT_VARIABLE)
        if not _blank(configured):
            return str(configured).strip(), ConfigurationSource.ENVIRONMENT
        usable = ",".join(slot.transport for slot in self._slots if self._usable(slot))
        if usable:
            return usable, ConfigurationSource.DEFAULT
        return "", ConfigurationSource.NONE

    def transport_order_stored(self) -> bool:
        return not _blank(self._store.get(TRANSPORT_VARIABLE))

    def save_transport_order(self, transports: Sequence[str]) -> tuple[str, ...]:
        """Store a validated use order, overriding the environment."""
        validated = validate_transport_order(transports)
        self._store.set(TRANSPORT_VARIABLE, ",".join(validated))
        self._changed_since_start = True
        return validated

    def clear_transport_order(self) -> None:
        """Remove the stored order so the environment (or the derived default)
        decides again -- Issue #96's guarantee, as an explicit action."""
        self._store.delete(TRANSPORT_VARIABLE)
        self._changed_since_start = True

    def _usable(self, slot: ApiKeySlot) -> bool:
        """Whether this slot contributes to a *derived* use order.

        Only a key counts. A keyless provider (Vertex AI/ADC, Codex) is
        deliberately left out of the derived order: being present on a host
        whose ADC happens to resolve, or which happens to have the Codex CLI
        installed, is not the same as the user choosing to grade through it,
        and auto-selecting a subscription-backed CLI would be a surprise. The
        screen can add them to the order explicitly, and the environment can
        name them, both of which this respects.
        """
        return self.key(slot) is not None

    def effective_environment(self) -> dict[str, str]:
        """A copy of this process's environment with the stored values layered
        over it -- what the provider factories are built from.

        A copy, never `os.environ` itself: see the module docstring for what
        mutating the real environment would give away.
        """
        values = dict(self._environment)
        transport, source = self.transport_order()
        selected = {item for item in transport.split(",") if item} if transport else set()
        for slot in self._slots:
            resolved = self.key(slot)
            if resolved is not None:
                assert slot.key_variable is not None  # implied by `resolved`
                values[slot.key_variable] = resolved[0]
            for status in self._readable_statuses(slot):
                if status.source is ConfigurationSource.CREDENTIAL_STORE:
                    # The user typed it here; it wins over the environment.
                    values[status.setting.variable] = status.value
                elif (
                    status.source is ConfigurationSource.DEFAULT
                    and slot.transport in selected
                    and _blank(values.get(status.setting.variable))
                ):
                    # A built-in default only fills a hole for a provider the
                    # chain is actually going to try. Injecting, say, Gemini's
                    # default model onto an OpenRouter-only host would change
                    # the environment every other factory reads for no reason.
                    values[status.setting.variable] = status.value
        if transport and source in (
            ConfigurationSource.CREDENTIAL_STORE,
            ConfigurationSource.DEFAULT,
        ):
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

        A built-in *default* (a model id) does not count as configuration:
        it exists precisely so a user who entered a key is not told grading
        is unconfigured, not so an empty install looks configured.
        """
        if not _blank(self._environment.get(TRANSPORT_VARIABLE)):
            return None
        if self.transport_order_stored():
            return None
        for slot in self._slots:
            if self.key(slot) is not None:
                return None
            for status in self._readable_statuses(slot):
                if status.source in (
                    ConfigurationSource.CREDENTIAL_STORE,
                    ConfigurationSource.ENVIRONMENT,
                ):
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
    "KNOWN_TRANSPORTS",
    "MAX_API_KEY_LENGTH",
    "MAX_SETTING_LENGTH",
    "NO_API_KEY_REASON",
    "PROMPT_VERSION_VARIABLE",
    "TRANSPORT_VARIABLE",
    "ApiKeySettings",
    "ApiKeySlot",
    "ApiKeyStatus",
    "ConfigurationSource",
    "CredentialStoreUnavailableError",
    "InvalidApiKeyError",
    "InvalidSettingError",
    "InvalidTransportOrderError",
    "TextSetting",
    "TextSettingStatus",
    "validate_api_key",
    "validate_setting_value",
    "validate_transport_order",
]
