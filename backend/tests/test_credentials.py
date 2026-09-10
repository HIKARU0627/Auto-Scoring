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
    validate_api_key,
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
        InMemoryCredentialStore({_OPENROUTER.key_variable: _FAKE_KEY}),
        {_OPENROUTER.key_variable: "from-the-environment"},
    )

    resolved = settings.key(_OPENROUTER)

    assert resolved == (_FAKE_KEY, ConfigurationSource.CREDENTIAL_STORE)
    assert settings.effective_environment()[_OPENROUTER.key_variable] == _FAKE_KEY


def test_the_environment_is_the_fallback_when_nothing_is_stored() -> None:
    settings = ApiKeySettings(
        InMemoryCredentialStore(),
        {_OPENROUTER.key_variable: "from-the-environment"},
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
    settings = ApiKeySettings(InMemoryCredentialStore({_OPENROUTER.key_variable: _FAKE_KEY}), {})

    settings.delete(_OPENROUTER)

    assert not settings.status(_OPENROUTER).configured
    assert settings.changed_since_start


def test_a_stored_key_supplies_the_transport_order_only_when_the_environment_does_not() -> None:
    """Issue #96's decision: the distributed default is OpenRouter, and the
    development machines' Vertex-first order does not move."""
    stored = InMemoryCredentialStore({_OPENROUTER.key_variable: _FAKE_KEY})

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
        InMemoryCredentialStore({_OPENROUTER.key_variable: _FAKE_KEY}), source
    )

    layered = settings.effective_environment()

    assert layered["AUTO_SCORING_EXISTING"] == "kept"
    assert _OPENROUTER.key_variable not in source


def test_no_configuration_at_all_gets_a_reason_a_person_can_act_on() -> None:
    settings = ApiKeySettings(InMemoryCredentialStore(), {})

    assert settings.missing_api_key_reason() == NO_API_KEY_REASON
    assert "設定" in NO_API_KEY_REASON


@pytest.mark.parametrize(
    "environment, store",
    [
        ({TRANSPORT_VARIABLE: "gemini"}, InMemoryCredentialStore()),
        ({}, InMemoryCredentialStore({_OPENROUTER.key_variable: _FAKE_KEY})),
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
    settings = ApiKeySettings(InMemoryCredentialStore({_OPENROUTER.key_variable: _FAKE_KEY}), {})

    described = settings.describe_sources()

    assert _FAKE_KEY not in described
    assert "credential_store" in described


def test_the_status_of_a_configured_slot_never_carries_the_key() -> None:
    settings = ApiKeySettings(InMemoryCredentialStore({_OPENROUTER.key_variable: _FAKE_KEY}), {})

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
