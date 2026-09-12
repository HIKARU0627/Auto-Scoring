"""One real call with the saved configuration, and the answers it can give
(Issues #96, #386).

**No test here reaches a real provider.** Every one drives an
`httpx.MockTransport` or injects a fake host probe, because the alternative is
a suite that is flaky when the network is and, over a CI run, somebody's
invoice. What each real endpoint is and why it is free is argued in
`adapters.credentials.verification`'s own docstring.
"""

from __future__ import annotations

import httpx
import pytest

from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError
from auto_scoring.adapters.credentials.api_keys import API_KEY_SLOTS, ApiKeySlot
from auto_scoring.adapters.credentials.verification import (
    VerificationResult,
    verify_api_key,
)

#: Obviously fake, and the exact string every "no secret escaped" assertion
#: searches for. Never a real key shape anyone could mistake for one.
_FAKE_KEY = "fake-openrouter-key-DO-NOT-USE-4c1f9a"

_OPENROUTER_KEY = "AUTO_SCORING_OPENROUTER_API_KEY"
_OPENAI_KEY = "AUTO_SCORING_OPENAI_API_KEY"


def _slot(slot_id: str) -> ApiKeySlot:
    return next(slot for slot in API_KEY_SLOTS if slot.id == slot_id)


_OPENROUTER = _slot("openrouter")
_OPENAI = _slot("openai")
_GEMINI = _slot("gemini")
_CODEX = _slot("codex_app_server")


def _verification_client(handler: object, base_url: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
    )


def test_verify_reports_success_and_sends_the_key_as_a_bearer_token() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        seen["path"] = request.url.path
        return httpx.Response(200, json={"data": {"usage": 0.5, "limit": None}})

    with _verification_client(handler, "https://openrouter.test/api/v1") as client:
        outcome = verify_api_key(_OPENROUTER, {_OPENROUTER_KEY: _FAKE_KEY}, client=client)

    assert outcome.result is VerificationResult.OK
    assert seen["auth"] == f"Bearer {_FAKE_KEY}"
    # `GET /key`, never a completion: the button must not cost the user
    # money every time they press it while unsure.
    assert seen["path"].endswith("/key")


@pytest.mark.parametrize("status_code", [401, 403])
def test_verify_tells_a_rejected_key_apart(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": _FAKE_KEY}})

    with _verification_client(handler, "https://openrouter.test/api/v1") as client:
        outcome = verify_api_key(_OPENROUTER, {_OPENROUTER_KEY: _FAKE_KEY}, client=client)

    assert outcome.result is VerificationResult.UNAUTHORIZED
    assert outcome.status_code == status_code
    # The body echoed the credential back. It goes no further.
    assert _FAKE_KEY not in outcome.detail


def test_verify_tells_an_unreachable_network_apart() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    with _verification_client(handler, "https://openrouter.test/api/v1") as client:
        outcome = verify_api_key(_OPENROUTER, {_OPENROUTER_KEY: _FAKE_KEY}, client=client)

    assert outcome.result is VerificationResult.UNREACHABLE
    assert outcome.status_code is None
    # This branch assembles a free-text message, so it is exactly the kind of
    # place a configuration value can be interpolated into. No key may reach
    # it, whatever the transport does to the request.
    assert _FAKE_KEY not in outcome.detail


def test_verify_tells_a_provider_side_failure_apart() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream on fire")

    with _verification_client(handler, "https://openrouter.test/api/v1") as client:
        outcome = verify_api_key(_OPENROUTER, {_OPENROUTER_KEY: _FAKE_KEY}, client=client)

    assert outcome.result is VerificationResult.PROVIDER_ERROR
    assert outcome.status_code == 500
    # Same reason as the unreachable branch above: PROVIDER_ERROR is the one
    # place `_http_error_outcome` interpolates a label into the message (the
    # 401/403 branch returns a fixed sentence), so it must be leak-checked too.
    assert _FAKE_KEY not in outcome.detail


def test_openai_verify_tells_a_provider_side_failure_apart() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream on fire")

    with _verification_client(handler, "https://openai.test/v1") as client:
        outcome = verify_api_key(_OPENAI, {_OPENAI_KEY: _FAKE_KEY}, openai_client=client)

    assert outcome.result is VerificationResult.PROVIDER_ERROR
    assert _FAKE_KEY not in outcome.detail


def test_openai_verify_tells_an_unreachable_network_apart() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    with _verification_client(handler, "https://openai.test/v1") as client:
        outcome = verify_api_key(_OPENAI, {_OPENAI_KEY: _FAKE_KEY}, openai_client=client)

    assert outcome.result is VerificationResult.UNREACHABLE
    assert _FAKE_KEY not in outcome.detail


def test_verify_reports_a_spent_key_rather_than_a_clean_success() -> None:
    """A live key with no credit authenticates perfectly and grades nothing.
    A green tick the first grading job contradicts is worse than no button."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"usage": 5.0, "limit": 5.0}})

    with _verification_client(handler, "https://openrouter.test/api/v1") as client:
        outcome = verify_api_key(_OPENROUTER, {_OPENROUTER_KEY: _FAKE_KEY}, client=client)

    assert outcome.result is VerificationResult.NO_CREDIT


def test_verify_accepts_a_body_it_cannot_read() -> None:
    """The key answered, which is what was asked. A response shape this app
    does not recognise is not an authentication problem."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json at all")

    with _verification_client(handler, "https://openrouter.test/api/v1") as client:
        outcome = verify_api_key(_OPENROUTER, {_OPENROUTER_KEY: _FAKE_KEY}, client=client)

    assert outcome.result is VerificationResult.OK


def test_openai_verify_uses_the_free_models_endpoint() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        seen["path"] = request.url.path
        return httpx.Response(200, json={"data": [{"id": "gpt-4o-mini"}]})

    with _verification_client(handler, "https://openai.test/v1") as client:
        outcome = verify_api_key(_OPENAI, {_OPENAI_KEY: _FAKE_KEY}, openai_client=client)

    assert outcome.result is VerificationResult.OK
    assert seen["auth"] == f"Bearer {_FAKE_KEY}"
    # No completion: this button runs no model and costs nothing.
    assert seen["path"].endswith("/models")


def test_openai_verify_tells_a_rejected_key_apart() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": _FAKE_KEY}})

    with _verification_client(handler, "https://openai.test/v1") as client:
        outcome = verify_api_key(_OPENAI, {_OPENAI_KEY: _FAKE_KEY}, openai_client=client)

    assert outcome.result is VerificationResult.UNAUTHORIZED
    assert _FAKE_KEY not in outcome.detail


def test_vertex_verify_reports_adc_available_without_a_key() -> None:
    """There is no key for Vertex AI; the credential is the host's ADC. A
    successful token resolution is the whole answer."""

    class _Tokens:
        project_id = "test-project"

        def bearer_token(self) -> str:  # pragma: no cover - never called
            return "fake"

    outcome = verify_api_key(
        _GEMINI,
        {},
        token_source_factory=lambda project_id: _Tokens(),  # type: ignore[arg-type,return-value]
    )

    assert outcome.result is VerificationResult.OK
    assert outcome.status_code is None


def test_vertex_verify_tells_a_missing_adc_apart() -> None:
    def no_adc(project_id: str | None) -> object:
        raise AdcCredentialsError("no ADC on this host")

    outcome = verify_api_key(
        _GEMINI,
        {},
        token_source_factory=no_adc,  # type: ignore[arg-type]
    )

    assert outcome.result is VerificationResult.MISSING_HOST_AUTH
    assert "gcloud" in outcome.detail


def test_codex_verify_reports_a_missing_cli() -> None:
    outcome = verify_api_key(_CODEX, {}, executable_available=lambda name: False)

    assert outcome.result is VerificationResult.MISSING_HOST_AUTH


def test_codex_verify_reports_an_installed_cli() -> None:
    outcome = verify_api_key(_CODEX, {}, executable_available=lambda name: True)

    assert outcome.result is VerificationResult.OK
