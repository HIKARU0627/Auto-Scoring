"""The API-key settings endpoints, and what they refuse to say (Issue #96).

Two rules are load-bearing here and each has a test whose whole job is to
fail when the rule is broken:

* **the key is never read back** -- not by the endpoint that just stored it,
  not by the one that lists what is held. A value the app will not display
  cannot leak through a screenshot or a support conversation, and there is
  nothing a user can do with a key they already own that re-reading it here
  would help with;
* **the key never reaches the log** -- including a key entered *after*
  logging was configured, which is every key this screen accepts. That is
  what `api.secret_redaction.SecretRegistry` exists for, and
  `test_a_saved_key_is_scrubbed_from_the_log` fails if the registration is
  removed.

Nothing here makes a live call: `create_app` takes the verifier, so a fake
answers every 疎通 request (``AGENTS.md``: a real provider costs money).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from auto_scoring.adapters.ai.unconfigured_provider import UnconfiguredAIProvider
from auto_scoring.adapters.credentials.api_keys import (
    API_KEY_SLOTS,
    NO_API_KEY_REASON,
    ApiKeySettings,
    ApiKeySlot,
)
from auto_scoring.adapters.credentials.store import (
    InMemoryCredentialStore,
    UnavailableCredentialStore,
)
from auto_scoring.adapters.credentials.verification import (
    VerificationOutcome,
    VerificationResult,
)
from auto_scoring.api.app import create_app
from auto_scoring.api.secret_redaction import SecretRegistry
from auto_scoring.api.sidecar import LOG_FILENAME, install_log_redaction

_TOKEN = "test-token"
_FAKE_KEY = "fake-openrouter-key-DO-NOT-USE-4c1f9a"
_OPENROUTER = API_KEY_SLOTS[0]
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


def _always(outcome: VerificationOutcome) -> Callable[[ApiKeySlot, str], VerificationOutcome]:
    def verify(slot: ApiKeySlot, api_key: str) -> VerificationOutcome:
        return outcome

    return verify


def _client(
    settings: ApiKeySettings,
    *,
    registry: SecretRegistry | None = None,
    outcome: VerificationOutcome | None = None,
    ai_provider: UnconfiguredAIProvider | None = None,
) -> TestClient:
    return TestClient(
        create_app(
            api_token=_TOKEN,
            credential_settings=settings,
            secret_registry=registry or SecretRegistry(),
            credential_verifier=_always(outcome) if outcome is not None else None,
            ai_provider=ai_provider,
        )
    )


def _stored(**environment: str) -> ApiKeySettings:
    return ApiKeySettings(
        InMemoryCredentialStore({_OPENROUTER.key_variable: _FAKE_KEY}), environment
    )


def test_the_screen_learns_that_a_key_is_held_and_where_it_came_from() -> None:
    with _client(_stored()) as client:
        body = client.get("/settings/api-keys", headers=_AUTH).json()

    (slot,) = body["keys"]
    assert slot["id"] == "openrouter"
    assert slot["configured"] is True
    assert slot["key_source"] == "credential_store"
    assert body["store_unavailable_reason"] is None


def test_an_environment_key_is_reported_as_coming_from_the_environment() -> None:
    """A developer machine with both must be able to tell which one is in
    use -- "there is a key" would not answer that (Issue #96)."""
    settings = ApiKeySettings(
        InMemoryCredentialStore(), {_OPENROUTER.key_variable: "from-the-environment"}
    )

    with _client(settings) as client:
        body = client.get("/settings/api-keys", headers=_AUTH).json()

    assert body["keys"][0]["key_source"] == "environment"


def test_the_transport_order_says_where_it_came_from_too() -> None:
    developer = "gemini,codex_app_server,openrouter,openai"

    with _client(_stored(AUTO_SCORING_AI_GRADING_TRANSPORT=developer)) as client:
        developer_body = client.get("/settings/api-keys", headers=_AUTH).json()
    with _client(_stored()) as client:
        installed_body = client.get("/settings/api-keys", headers=_AUTH).json()

    assert developer_body["transport_order"] == developer
    assert developer_body["transport_source"] == "environment"
    assert installed_body["transport_order"] == "openrouter"
    assert installed_body["transport_source"] == "builtin_default"


def test_saving_a_key_keeps_it_and_never_reads_it_back() -> None:
    store = InMemoryCredentialStore()
    settings = ApiKeySettings(store, {})

    with _client(settings) as client:
        response = client.put(
            f"/settings/api-keys/{_OPENROUTER.id}", json={"value": _FAKE_KEY}, headers=_AUTH
        )
        listed = client.get("/settings/api-keys", headers=_AUTH)

    assert response.status_code == 200
    assert store.get(_OPENROUTER.key_variable) == _FAKE_KEY
    assert response.json()["keys"][0]["configured"] is True
    # The response body is the entire channel back to the screen. If the key
    # is not in it, the screen cannot display it however it is written.
    assert _FAKE_KEY not in response.text
    assert _FAKE_KEY not in listed.text


def test_saving_a_key_marks_the_running_sidecar_as_out_of_date() -> None:
    """The provider chain is built once at startup. Until the sidecar is
    restarted, what is stored and what is running disagree -- and the screen
    has to say so rather than let the user find out at the next grading job.
    """
    with _client(ApiKeySettings(InMemoryCredentialStore(), {})) as client:
        assert client.get("/settings/api-keys", headers=_AUTH).json()["restart_required"] is False
        saved = client.put(
            f"/settings/api-keys/{_OPENROUTER.id}", json={"value": _FAKE_KEY}, headers=_AUTH
        )

    assert saved.json()["restart_required"] is True


def test_deleting_a_key_removes_it() -> None:
    store = InMemoryCredentialStore({_OPENROUTER.key_variable: _FAKE_KEY})

    with _client(ApiKeySettings(store, {})) as client:
        response = client.delete(f"/settings/api-keys/{_OPENROUTER.id}", headers=_AUTH)

    assert response.status_code == 200
    assert response.json()["keys"][0]["configured"] is False
    assert store.get(_OPENROUTER.key_variable) is None


def test_a_host_with_no_credential_store_says_so_and_refuses_to_pretend() -> None:
    """Every Linux development machine here, and CI. The app runs; only
    saving is unavailable, and the screen gets a reason rather than a 500."""
    settings = ApiKeySettings(UnavailableCredentialStore("no backend here"), {})

    with _client(settings) as client:
        listed = client.get("/settings/api-keys", headers=_AUTH).json()
        save = client.put(
            f"/settings/api-keys/{_OPENROUTER.id}", json={"value": _FAKE_KEY}, headers=_AUTH
        )

    assert listed["store_unavailable_reason"] == "no backend here"
    assert save.status_code == 503
    assert save.json()["detail"] == "no backend here"


def test_a_malformed_key_is_refused_at_the_boundary() -> None:
    with _client(ApiKeySettings(InMemoryCredentialStore(), {})) as client:
        response = client.put(
            f"/settings/api-keys/{_OPENROUTER.id}",
            json={"value": "sk-with-a\nnewline"},
            headers=_AUTH,
        )

    assert response.status_code == 422


def test_an_unknown_slot_is_a_404() -> None:
    with _client(ApiKeySettings(InMemoryCredentialStore(), {})) as client:
        for request in (
            client.put("/settings/api-keys/nope", json={"value": _FAKE_KEY}, headers=_AUTH),
            client.delete("/settings/api-keys/nope", headers=_AUTH),
            client.post("/settings/api-keys/nope/verify", headers=_AUTH),
        ):
            assert request.status_code == 404


@pytest.mark.parametrize(
    "outcome, expected",
    [
        (VerificationOutcome(VerificationResult.OK, "疎通しました。", 200), "ok"),
        (
            VerificationOutcome(VerificationResult.UNAUTHORIZED, "受け付けられません。", 401),
            "unauthorized",
        ),
        (VerificationOutcome(VerificationResult.UNREACHABLE, "つながりません。"), "unreachable"),
    ],
)
def test_verify_renders_each_outcome_distinctly(
    outcome: VerificationOutcome, expected: str
) -> None:
    """Issue #96 requires success, an authentication failure and an
    unreachable network to be three different things on screen: they call
    for three different actions."""
    with _client(_stored(), outcome=outcome) as client:
        body = client.post(f"/settings/api-keys/{_OPENROUTER.id}/verify", headers=_AUTH).json()

    assert body["result"] == expected
    assert body["detail"] == outcome.detail
    assert body["status_code"] == outcome.status_code
    assert body["key_source"] == "credential_store"


def test_verify_without_a_key_says_so_instead_of_calling_anything() -> None:
    def never(slot: ApiKeySlot, api_key: str) -> VerificationOutcome:
        raise AssertionError("nothing to verify, so nothing may be called")

    app = create_app(
        api_token=_TOKEN,
        credential_settings=ApiKeySettings(InMemoryCredentialStore(), {}),
        secret_registry=SecretRegistry(),
        credential_verifier=never,
    )
    with TestClient(app) as client:
        body = client.post(f"/settings/api-keys/{_OPENROUTER.id}/verify", headers=_AUTH).json()

    assert body["result"] == "not_configured"
    assert body["key_source"] == "none"


def test_verify_never_echoes_the_key_even_when_the_provider_does() -> None:
    leaky = VerificationOutcome(VerificationResult.UNAUTHORIZED, "invalid key", 401)

    with _client(_stored(), outcome=leaky) as client:
        response = client.post(f"/settings/api-keys/{_OPENROUTER.id}/verify", headers=_AUTH)

    assert _FAKE_KEY not in response.text


@pytest.fixture
def restored_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    try:
        yield
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers, root.level = handlers, level


def _log_text(directory: Path) -> str:
    """What actually landed in ``sidecar.log``.

    Read from the file rather than from `caplog`: pytest's capture handler
    is attached to the root *logger* and never passes through the handler
    filters `install_log_redaction` installs, so it would report the
    unredacted record and prove nothing about what ships.
    """
    for handler in logging.getLogger().handlers:
        handler.flush()
    return (directory / LOG_FILENAME).read_text(encoding="utf-8")


def test_a_saved_key_is_scrubbed_from_the_log(restored_logging: None, tmp_path: Path) -> None:
    """The mutation this guards: drop ``secret_registry.add(stored)`` from
    `api.settings_router.save_api_key` and this test goes red.

    It is not a hypothetical route. Logging is configured once, at startup,
    from the configuration that existed *then* -- so a key the user types in
    afterwards is, to that filter, an unknown string. The next thing that
    happens to it is a live HTTP call whose failures are logged.
    """
    registry = SecretRegistry()
    install_log_redaction("session-token", tmp_path, registry=registry)
    logger = logging.getLogger("auto_scoring.test_api_key_settings")

    with _client(ApiKeySettings(InMemoryCredentialStore(), {}), registry=registry) as client:
        client.put(f"/settings/api-keys/{_OPENROUTER.id}", json={"value": _FAKE_KEY}, headers=_AUTH)
        logger.warning("a library logged the request: Authorization: Bearer %s", _FAKE_KEY)

    written = _log_text(tmp_path)
    assert _FAKE_KEY not in written
    assert "Bearer ***" in written


def test_an_environment_key_is_scrubbed_from_the_log_too(
    restored_logging: None, tmp_path: Path
) -> None:
    """The verify endpoint registers whichever key it is about to send, not
    only the ones this app stored: a key from ``.env.local`` reaches the
    same live call and the same log."""
    registry = SecretRegistry()
    install_log_redaction("session-token", tmp_path, registry=registry)
    logger = logging.getLogger("auto_scoring.test_api_key_settings")
    settings = ApiKeySettings(InMemoryCredentialStore(), {_OPENROUTER.key_variable: _FAKE_KEY})

    with _client(
        settings, registry=registry, outcome=VerificationOutcome(VerificationResult.OK, "ok", 200)
    ) as client:
        client.post(f"/settings/api-keys/{_OPENROUTER.id}/verify", headers=_AUTH)
        logger.warning("upstream said: %s", _FAKE_KEY)

    assert _FAKE_KEY not in _log_text(tmp_path)


def test_an_unconfigured_host_still_serves_everything_except_grading() -> None:
    """Issue #96 acceptance: the app starts with no key, and only grading
    stops -- with a reason a person who has just installed this can act on,
    rather than the name of an environment variable they have never set."""
    settings = ApiKeySettings(InMemoryCredentialStore(), {})
    assert settings.missing_api_key_reason() == NO_API_KEY_REASON

    with _client(settings, ai_provider=UnconfiguredAIProvider(NO_API_KEY_REASON)) as client:
        availability = client.get("/grading/availability", headers=_AUTH).json()
        # Intake, review and export all hang off these; none of them needs a
        # grading provider, and none of them may be lost to a missing key.
        assert client.get("/tests", headers=_AUTH).status_code == 200
        assert client.get("/intake-templates", headers=_AUTH).status_code == 200
        assert client.get("/settings/api-keys", headers=_AUTH).status_code == 200

    assert availability["available"] is False
    assert availability["reason"] == NO_API_KEY_REASON
