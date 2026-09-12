"""The credential store, and the layering that puts a stored key in front of
the environment (Issue #96).

**Nothing here touches this machine's real credential store.** Every test
injects either a fake ``keyring`` module or an in-memory store, for the
reason ``docs/quality-gates.md`` records: the development machines are Linux
and CI has no credential backend at all, so a test that inherited the host's
would be green here and mean nothing about the platform this ships to --
or, worse, would start writing real entries into a developer's Credential
Manager. The "no backend" case is *also* injected rather than relied on, so
it stays under test on a machine that does have one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_scoring.adapters.credentials.api_keys import (
    API_KEY_SLOTS,
    DEFAULT_PROMPT_VERSION,
    MAX_API_KEY_LENGTH,
    NO_API_KEY_REASON,
    PROMPT_VERSION_VARIABLE,
    TRANSPORT_VARIABLE,
    ApiKeySettings,
    ConfigurationSource,
    InvalidApiKeyError,
    InvalidSettingError,
    InvalidTransportOrderError,
    validate_api_key,
    validate_setting_value,
    validate_transport_order,
)
from auto_scoring.adapters.credentials.store import (
    CredentialStoreUnavailableError,
    InMemoryCredentialStore,
    KeyringCredentialStore,
    UnavailableCredentialStore,
)

#: Obviously fake, and the exact string every "no secret escaped" assertion
#: searches for. Never a real key shape anyone could mistake for one.
_FAKE_KEY = "fake-openrouter-key-DO-NOT-USE-4c1f9a"

_OPENROUTER = API_KEY_SLOTS[0]
#: The slot's key variable as a `str` -- `ApiKeySlot.key_variable` is optional
#: because Vertex AI and Codex hold no key, and the tests below are all about
#: the OpenRouter one.
_OPENROUTER_KEY_VARIABLE = "AUTO_SCORING_OPENROUTER_API_KEY"


class _FakeKeyring:
    """A ``keyring`` module that works, remembering nothing beyond a dict."""

    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], str] = {}

    def get_password(self, service_name: str, username: str) -> str | None:
        return self.entries.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self.entries[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
        del self.entries[(service_name, username)]


class _NoBackendKeyring:
    """A ``keyring`` module on a host with nothing behind it.

    ``keyring.errors.NoKeyringError`` is what the real package raises when
    its backend chain comes up empty -- on this project's Linux development
    machines, and on CI. Raised from a fake so the behaviour is pinned
    everywhere, including on a machine that *does* have a backend.
    """

    def __init__(self) -> None:
        import keyring.errors

        self._error = keyring.errors.NoKeyringError

    def get_password(self, service_name: str, username: str) -> str | None:
        raise self._error("No recommended backend was available")

    def set_password(self, service_name: str, username: str, password: str) -> None:
        raise self._error("No recommended backend was available")

    def delete_password(self, service_name: str, username: str) -> None:
        raise self._error("No recommended backend was available")


class _EchoingKeyring(_FakeKeyring):
    """A backend whose failure message quotes what it was handed.

    Not hypothetical: an error string that includes the value it choked on
    is the exact accident `api.secret_redaction` exists for, and a
    credential backend is the last place it may happen.
    """

    def set_password(self, service_name: str, username: str, password: str) -> None:
        raise RuntimeError(f"could not store {password!r} for {username}")


def test_keyring_store_round_trips_a_value() -> None:
    store = KeyringCredentialStore(_FakeKeyring())

    store.set("AUTO_SCORING_OPENROUTER_API_KEY", _FAKE_KEY)

    assert store.unavailable_reason() is None
    assert store.get("AUTO_SCORING_OPENROUTER_API_KEY") == _FAKE_KEY


def test_keyring_store_survives_a_host_with_no_backend() -> None:
    """The Linux development machines and CI. Reading degrades to "nothing
    is stored here" rather than raising -- the sidecar must still start."""
    store = KeyringCredentialStore(_NoBackendKeyring())

    assert store.unavailable_reason() is not None
    assert store.get("AUTO_SCORING_OPENROUTER_API_KEY") is None
    # Deleting what cannot be there is not a failure either.
    store.delete("AUTO_SCORING_OPENROUTER_API_KEY")


def test_saving_to_a_host_with_no_backend_fails_loudly() -> None:
    """The one operation that must *not* degrade quietly. A user told their
    key was kept, who finds it gone next launch, has been lied to about the
    only thing this screen does."""
    store = KeyringCredentialStore(_NoBackendKeyring())

    with pytest.raises(CredentialStoreUnavailableError):
        store.set("AUTO_SCORING_OPENROUTER_API_KEY", _FAKE_KEY)


def test_a_backend_failure_never_quotes_the_value() -> None:
    store = KeyringCredentialStore(_EchoingKeyring())

    with pytest.raises(CredentialStoreUnavailableError) as raised:
        store.set("AUTO_SCORING_OPENROUTER_API_KEY", _FAKE_KEY)

    assert _FAKE_KEY not in str(raised.value)
    # And not through the chained cause either, which Python renders too.
    assert raised.value.__cause__ is None
    assert _FAKE_KEY not in repr(raised.value)


def test_unavailable_store_reports_its_reason_and_stores_nothing() -> None:
    store = UnavailableCredentialStore("no credential store was supplied")

    assert store.unavailable_reason() == "no credential store was supplied"
    assert store.get("AUTO_SCORING_OPENROUTER_API_KEY") is None
    with pytest.raises(CredentialStoreUnavailableError):
        store.set("AUTO_SCORING_OPENROUTER_API_KEY", _FAKE_KEY)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "sk-with-a-\nnewline",
        "sk-with-a-\ttab",
        "キー",
        "x" * (MAX_API_KEY_LENGTH + 1),
    ],
)
def test_validate_api_key_refuses_what_must_not_be_stored(value: str) -> None:
    """A newline in particular: the key is sent as an ``Authorization``
    header, where a line break is a request-splitting primitive."""
    with pytest.raises(InvalidApiKeyError):
        validate_api_key(value)


def test_validate_api_key_trims_a_pasted_value() -> None:
    assert validate_api_key(f"  {_FAKE_KEY}\n") == _FAKE_KEY


def test_a_stored_key_beats_the_environment() -> None:
    """Issue #96: the sidecar looks at the credential store first and falls
    back to environment variables. A key typed into the screen is the one
    that gets used, even on a machine that also has a ``.env.local``."""
    settings = ApiKeySettings(
        InMemoryCredentialStore({_OPENROUTER_KEY_VARIABLE: _FAKE_KEY}),
        {_OPENROUTER_KEY_VARIABLE: "from-the-environment"},
    )

    resolved = settings.key(_OPENROUTER)

    assert resolved == (_FAKE_KEY, ConfigurationSource.CREDENTIAL_STORE)
    assert settings.effective_environment()[_OPENROUTER_KEY_VARIABLE] == _FAKE_KEY


def test_the_environment_is_the_fallback_when_nothing_is_stored() -> None:
    settings = ApiKeySettings(
        InMemoryCredentialStore(),
        {_OPENROUTER_KEY_VARIABLE: "from-the-environment"},
    )

    assert settings.key(_OPENROUTER) == (
        "from-the-environment",
        ConfigurationSource.ENVIRONMENT,
    )


def test_a_stored_key_survives_a_restart() -> None:
    """ "Saved" has to mean "still there next launch" -- the whole point of
    using the OS credential store rather than process memory. A second
    `ApiKeySettings` over the same backend is what a restart looks like."""
    keyring_module = _FakeKeyring()
    first = ApiKeySettings(KeyringCredentialStore(keyring_module), {})
    first.save(_OPENROUTER, _FAKE_KEY)

    after_restart = ApiKeySettings(KeyringCredentialStore(keyring_module), {})

    assert after_restart.status(_OPENROUTER).configured
    assert after_restart.key(_OPENROUTER) == (_FAKE_KEY, ConfigurationSource.CREDENTIAL_STORE)
    # And a fresh process has nothing pending: the chain it built is the
    # one the stored configuration describes.
    assert not after_restart.changed_since_start


def test_deleting_a_key_leaves_the_slot_unconfigured() -> None:
    settings = ApiKeySettings(InMemoryCredentialStore({_OPENROUTER_KEY_VARIABLE: _FAKE_KEY}), {})

    settings.delete(_OPENROUTER)

    assert not settings.status(_OPENROUTER).configured
    assert settings.changed_since_start


def test_a_stored_key_supplies_the_transport_order_only_when_the_environment_does_not() -> None:
    """Issue #96's decision: the distributed default is OpenRouter, and the
    development machines' Vertex-first order does not move."""
    stored = InMemoryCredentialStore({_OPENROUTER_KEY_VARIABLE: _FAKE_KEY})

    distributed = ApiKeySettings(stored, {}).effective_environment()
    assert distributed[TRANSPORT_VARIABLE] == "openrouter"
    assert distributed[_OPENROUTER.model_variable] == _OPENROUTER.default_model
    assert distributed[PROMPT_VERSION_VARIABLE] == DEFAULT_PROMPT_VERSION

    developer_order = "gemini,codex_app_server,openrouter,openai"
    developer = ApiKeySettings(
        stored,
        {
            TRANSPORT_VARIABLE: developer_order,
            _OPENROUTER.model_variable: "vendor/other-model",
            PROMPT_VERSION_VARIABLE: "v9",
        },
    )
    assert developer.effective_environment()[TRANSPORT_VARIABLE] == developer_order
    assert developer.effective_environment()[_OPENROUTER.model_variable] == "vendor/other-model"
    assert developer.effective_environment()[PROMPT_VERSION_VARIABLE] == "v9"
    assert developer.transport_order() == (developer_order, ConfigurationSource.ENVIRONMENT)


def test_the_layered_environment_is_a_copy() -> None:
    """`os.environ` is never written to, so nothing this process spawns
    inherits a key it was not handed -- the codex app-server child above
    all (`adapters.ai_grading.codex_app_server_provider`)."""
    source = {"AUTO_SCORING_EXISTING": "kept"}
    settings = ApiKeySettings(
        InMemoryCredentialStore({_OPENROUTER_KEY_VARIABLE: _FAKE_KEY}), source
    )

    layered = settings.effective_environment()

    assert layered["AUTO_SCORING_EXISTING"] == "kept"
    assert _OPENROUTER_KEY_VARIABLE not in source


def test_no_configuration_at_all_gets_a_reason_a_person_can_act_on() -> None:
    settings = ApiKeySettings(InMemoryCredentialStore(), {})

    assert settings.missing_api_key_reason() == NO_API_KEY_REASON
    assert "設定" in NO_API_KEY_REASON


@pytest.mark.parametrize(
    "environment, store",
    [
        ({TRANSPORT_VARIABLE: "gemini"}, InMemoryCredentialStore()),
        ({}, InMemoryCredentialStore({_OPENROUTER_KEY_VARIABLE: _FAKE_KEY})),
    ],
)
def test_a_host_with_some_configuration_keeps_the_specific_message(
    environment: dict[str, str], store: InMemoryCredentialStore
) -> None:
    """A developer machine that named a transport and got the credentials
    wrong needs the factory's message, which names the variable. Replacing
    it with "enter a key on the settings screen" would throw that away."""
    assert ApiKeySettings(store, environment).missing_api_key_reason() is None


def test_source_description_carries_no_value() -> None:
    settings = ApiKeySettings(InMemoryCredentialStore({_OPENROUTER_KEY_VARIABLE: _FAKE_KEY}), {})

    described = settings.describe_sources()

    assert _FAKE_KEY not in described
    assert "credential_store" in described


def test_the_status_of_a_configured_slot_never_carries_the_key() -> None:
    settings = ApiKeySettings(InMemoryCredentialStore({_OPENROUTER_KEY_VARIABLE: _FAKE_KEY}), {})

    status = settings.status(_OPENROUTER)

    assert status.configured
    assert _FAKE_KEY not in repr(status)


def test_the_distributed_defaults_match_env_example() -> None:
    """Guards the one hazard of defaulting configuration in code: the tag in
    `.env.example` is bumped alongside the prompt template, and a stale copy
    here would silently pool results from two different templates under one
    name -- or, for the model, grade with something nobody chose."""
    text = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    values = dict(
        line.split("=", 1)
        for line in text.splitlines()
        if line and not line.startswith("#") and "=" in line
    )

    assert values[PROMPT_VERSION_VARIABLE] == DEFAULT_PROMPT_VERSION
    assert values[_OPENROUTER.model_variable] == _OPENROUTER.default_model


# --- Issue #386: the other providers, their readable settings, and the order ---

_OPENAI = next(slot for slot in API_KEY_SLOTS if slot.id == "openai")
_GEMINI = next(slot for slot in API_KEY_SLOTS if slot.id == "gemini")
_CODEX = next(slot for slot in API_KEY_SLOTS if slot.id == "codex_app_server")


def test_every_provider_the_owner_asked_for_has_a_slot() -> None:
    assert [slot.transport for slot in API_KEY_SLOTS] == [
        "openrouter",
        "openai",
        "gemini",
        "codex_app_server",
    ]
    # Vertex and Codex hold no key on this screen at all: the first is ADC,
    # the second the operator's own `codex login`.
    assert _GEMINI.key_variable is None
    assert _CODEX.key_variable is None


def test_a_keyless_provider_refuses_to_store_a_key() -> None:
    settings = ApiKeySettings(InMemoryCredentialStore(), {})

    assert settings.key(_GEMINI) is None
    with pytest.raises(InvalidSettingError):
        settings.save(_GEMINI, _FAKE_KEY)


def test_a_text_setting_is_read_back_with_its_source() -> None:
    """The whole difference from a key: model / project / region are not
    secrets, so the screen *must* show the current value to be usable."""
    settings = ApiKeySettings(
        InMemoryCredentialStore({_GEMINI.model_variable: "gemini-2.5-pro"}), {}
    )

    status = settings.status(_GEMINI)

    assert status.model == "gemini-2.5-pro"
    assert status.model_source is ConfigurationSource.CREDENTIAL_STORE
    project = next(
        item
        for item in status.text_settings
        if item.setting.variable == "AUTO_SCORING_VERTEX_PROJECT"
    )
    assert project.source is ConfigurationSource.NONE
    location = next(
        item
        for item in status.text_settings
        if item.setting.variable == "AUTO_SCORING_VERTEX_LOCATION"
    )
    assert location.value == "global"
    assert location.source is ConfigurationSource.DEFAULT


def test_a_stored_text_setting_beats_the_environment() -> None:
    settings = ApiKeySettings(
        InMemoryCredentialStore({_OPENAI.model_variable: "gpt-4.1"}),
        {_OPENAI.model_variable: "from-env"},
    )

    assert settings.status(_OPENAI).model == "gpt-4.1"
    assert settings.effective_environment()[_OPENAI.model_variable] == "gpt-4.1"


@pytest.mark.parametrize(
    "value",
    ["with a\nnewline", "全角", "x" * 257],
)
def test_validate_setting_value_refuses_what_must_not_be_stored(value: str) -> None:
    with pytest.raises(InvalidSettingError):
        validate_setting_value(value)


def test_validate_setting_value_trims_a_pasted_value() -> None:
    assert validate_setting_value("  gemini-2.5-flash\n") == "gemini-2.5-flash"


def test_save_settings_clears_a_blank_value() -> None:
    store = InMemoryCredentialStore(
        {_GEMINI.model_variable: "gemini-2.5-pro", "AUTO_SCORING_VERTEX_PROJECT": "old"}
    )
    settings = ApiKeySettings(store, {})

    settings.save_settings(
        _GEMINI, {_GEMINI.model_variable: "  ", "AUTO_SCORING_VERTEX_PROJECT": None}
    )

    assert store.get(_GEMINI.model_variable) is None
    assert store.get("AUTO_SCORING_VERTEX_PROJECT") is None
    assert settings.status(_GEMINI).model == _GEMINI.default_model


def test_save_settings_refuses_a_variable_that_is_not_on_the_slot() -> None:
    settings = ApiKeySettings(InMemoryCredentialStore(), {})

    with pytest.raises(InvalidSettingError):
        settings.save_settings(_OPENAI, {"AUTO_SCORING_VERTEX_PROJECT": "x"})


def test_saving_settings_returns_the_secret_for_log_redaction() -> None:
    settings = ApiKeySettings(InMemoryCredentialStore(), {})

    stored_secrets = settings.save_settings(
        _OPENROUTER, {_OPENROUTER_KEY_VARIABLE: _FAKE_KEY, _OPENROUTER.model_variable: "m"}
    )

    assert stored_secrets == (_FAKE_KEY,)


def test_a_saved_order_beats_the_environment() -> None:
    """Issue #386 reverses Issue #96's "the environment always wins" for the
    order only, because the owner asked to reorder from the screen and an
    order the chain ignores is worse than no control at all."""
    settings = ApiKeySettings(
        InMemoryCredentialStore(),
        {TRANSPORT_VARIABLE: "gemini,openrouter"},
    )

    settings.save_transport_order(["openai", "openrouter"])

    assert settings.transport_order() == (
        "openai,openrouter",
        ConfigurationSource.CREDENTIAL_STORE,
    )
    assert settings.transport_order_stored() is True
    assert settings.effective_environment()[TRANSPORT_VARIABLE] == "openai,openrouter"


def test_clearing_the_saved_order_reverts_to_the_environment() -> None:
    settings = ApiKeySettings(
        InMemoryCredentialStore(),
        {TRANSPORT_VARIABLE: "gemini,openrouter"},
    )
    settings.save_transport_order(["openai"])

    settings.clear_transport_order()

    assert settings.transport_order() == (
        "gemini,openrouter",
        ConfigurationSource.ENVIRONMENT,
    )
    assert settings.transport_order_stored() is False
    assert settings.effective_environment()[TRANSPORT_VARIABLE] == "gemini,openrouter"


def test_a_derived_order_never_claims_a_provider_the_host_did_not_confirm() -> None:
    """With no host probe, Vertex and Codex are "unknown", not "usable": a
    derived default that named them would claim a check nobody made."""
    settings = ApiKeySettings(InMemoryCredentialStore(), {})

    assert settings.transport_order() == ("", ConfigurationSource.NONE)

    with_key = ApiKeySettings(InMemoryCredentialStore({_OPENROUTER_KEY_VARIABLE: _FAKE_KEY}), {})
    assert with_key.transport_order() == ("openrouter", ConfigurationSource.DEFAULT)


@pytest.mark.parametrize(
    "order",
    [(), ("bogus",), ("openrouter", "openrouter"), ("openrouter", "codex_app_server", "bogus")],
)
def test_validate_transport_order_rejects_a_bad_list(order: tuple[str, ...]) -> None:
    with pytest.raises(InvalidTransportOrderError):
        validate_transport_order(order)


def test_validate_transport_order_keeps_a_valid_list_in_order() -> None:
    assert validate_transport_order(["openai", "gemini"]) == ("openai", "gemini")


def test_the_host_probe_decides_a_keyless_providers_status() -> None:
    settings = ApiKeySettings(
        InMemoryCredentialStore(),
        {},
        vertex_auth_available=lambda project_id: False,
        codex_available=lambda: True,
    )

    assert settings.status(_GEMINI).host_available is False
    assert settings.status(_CODEX).host_available is True
    # But a host probe does *not* put a keyless provider into a derived order:
    # that would auto-select a subscription-backed CLI nobody chose.
    assert settings.transport_order() == ("", ConfigurationSource.NONE)


def test_saving_settings_marks_the_chain_as_out_of_date() -> None:
    settings = ApiKeySettings(InMemoryCredentialStore(), {})

    settings.save_settings(_OPENAI, {_OPENAI.model_variable: "gpt-4.1"})

    assert settings.changed_since_start
