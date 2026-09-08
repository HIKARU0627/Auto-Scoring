"""Tests for wiring the real ``AIProvider`` chain into the sidecar, and for
what a host with no usable credentials gets instead (Issue #97).

Nothing here reaches a network or reads this machine's own configuration.
Both host probes ``create_ai_provider`` makes -- is ``codex`` runnable, is
ADC set up -- are injected, for the reason ``docs/quality-gates.md`` records
after Issue #35 broke CI with exactly that: a test that inherits them is
green on a developer machine and red on a runner, or the other way round.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial

from fastapi.testclient import TestClient

from auto_scoring.adapters.ai.unconfigured_provider import UnconfiguredAIProvider
from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.ai_grading.factory import create_ai_provider
from auto_scoring.adapters.ai_grading.fallback_provider import FallbackAIProvider
from auto_scoring.api.app import build_ai_provider, create_app
from auto_scoring.domain.ai_provider import (
    AIProvider,
    GradingRequest,
    GradingResponse,
    ProviderDescriptor,
)

_TOKEN = "test-token"

#: Obviously fake, and the exact string every "no secret escaped" assertion
#: below searches for. Never a real key shape anyone could mistake for one.
_FAKE_KEY = "fake-api-key-DO-NOT-USE-90bd1f"

_ALL_FOUR_TRANSPORTS = {
    "AUTO_SCORING_AI_GRADING_TRANSPORT": "gemini,codex_app_server,openrouter,openai",
    "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
}


def _no_executables(name: str) -> bool:
    """This host has no ``codex`` binary, whatever the machine really has."""
    return False


def _no_adc(project_id: str | None) -> AdcTokenSource:
    """This host has no ADC login, whatever the machine really has."""
    raise AdcCredentialsError("Google Application Default Credentials are not available")


#: ``create_ai_provider`` bound to a host with neither Codex nor ADC. The two
#: key-based transports are unaffected -- they are pure configuration.
_on_a_host_with_no_local_credentials = partial(
    create_ai_provider,
    executable_available=_no_executables,
    token_source_factory=_no_adc,
)


class _StubAIProvider:
    """Stands in for a configured chain. Never called by these tests -- only
    its presence is under test."""

    name = "stub"

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider="stub",
            model="stub-model",
            version=None,
            prompt_version="v1",
            temperature=0.0,
            structured_output_mode="json_schema",
        )

    def grade(self, request: GradingRequest) -> GradingResponse:
        raise AssertionError("these tests never grade")


def _client(ai_provider: AIProvider | None) -> TestClient:
    return TestClient(create_app(api_token=_TOKEN, ai_provider=ai_provider))


def _availability(client: TestClient) -> dict[str, object]:
    response = client.get("/grading/availability", headers={"Authorization": f"Bearer {_TOKEN}"})
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    return body


def test_build_ai_provider_names_the_variable_an_unconfigured_host_is_missing() -> None:
    provider = build_ai_provider({}, factory=_on_a_host_with_no_local_credentials)

    assert isinstance(provider, UnconfiguredAIProvider)
    assert "AUTO_SCORING_AI_GRADING_TRANSPORT" in provider.reason


def test_build_ai_provider_returns_the_configured_chain() -> None:
    """The point of the whole Issue: a host that *is* configured gets the
    real priority chain (Issue #81 判断B), not a placeholder."""
    provider = build_ai_provider(
        {
            **_ALL_FOUR_TRANSPORTS,
            "AUTO_SCORING_GEMINI_MODEL": "gemini-2.5-flash",
            "AUTO_SCORING_OPENROUTER_API_KEY": _FAKE_KEY,
            "AUTO_SCORING_OPENROUTER_MODEL": "vendor/model",
            "AUTO_SCORING_OPENAI_API_KEY": _FAKE_KEY,
            "AUTO_SCORING_OPENAI_MODEL": "gpt-4o-mini",
        },
        factory=_on_a_host_with_no_local_credentials,
    )

    # Gemini and Codex are left out (no ADC, no binary on this "host"), which
    # is `create_ai_provider`'s own rule -- an unconfigured provider must not
    # consume one step of the chain.
    assert isinstance(provider, FallbackAIProvider)


def test_build_ai_provider_reason_never_carries_a_credential_value() -> None:
    """Issue #35's discipline, applied to the one string this Issue newly
    publishes: `UnconfiguredAIProvider.reason` reaches an HTTP response, the
    sidecar log, and a banner on screen. It may name variables; it may never
    quote their values."""
    provider = build_ai_provider(
        {
            **_ALL_FOUR_TRANSPORTS,
            "AUTO_SCORING_GEMINI_MODEL": "gemini-2.5-flash",
            # Set, but each is missing its partner, so every transport is
            # skipped and all four skip reasons end up in the message.
            "AUTO_SCORING_OPENROUTER_API_KEY": _FAKE_KEY,
            "AUTO_SCORING_OPENAI_API_KEY": _FAKE_KEY,
        },
        factory=_on_a_host_with_no_local_credentials,
    )

    assert isinstance(provider, UnconfiguredAIProvider)
    assert "AUTO_SCORING_OPENROUTER_MODEL" in provider.reason
    assert _FAKE_KEY not in provider.reason


def test_build_ai_provider_keeps_an_unexpected_failure_message_out_of_the_reason() -> None:
    """An adapter that fails to construct for a reason the factory does not
    classify is still not allowed to stop the sidecar -- and its message is
    not known to be secret-free (an httpx proxy URL can carry credentials),
    so only the exception type survives."""

    def _explode(env: Mapping[str, str]) -> AIProvider:
        raise RuntimeError(f"proxy https://user:{_FAKE_KEY}@proxy.invalid rejected us")

    provider = build_ai_provider({}, factory=_explode)

    assert isinstance(provider, UnconfiguredAIProvider)
    assert "RuntimeError" in provider.reason
    assert _FAKE_KEY not in provider.reason
    assert "proxy.invalid" not in provider.reason


def test_availability_reports_the_reason_when_grading_is_unconfigured() -> None:
    client = _client(UnconfiguredAIProvider("AUTO_SCORING_AI_GRADING_TRANSPORT is required"))

    body = _availability(client)

    assert body == {
        "available": False,
        "reason": "AUTO_SCORING_AI_GRADING_TRANSPORT is required",
    }


def test_availability_reports_available_with_a_configured_provider() -> None:
    client = _client(_StubAIProvider())

    assert _availability(client) == {"available": True, "reason": None}


def test_availability_is_unavailable_when_no_provider_was_injected() -> None:
    """`create_app` has no "grade with a placeholder" default any more: a
    caller that supplies nothing gets an app that says so, rather than one
    that quietly records fabricated grades (Issue #97)."""
    assert _availability(_client(None))["available"] is False


def test_availability_requires_the_bearer_token() -> None:
    """Unlike ``/healthz``: this reports on the installation's own
    configuration, and nothing needs it before the handshake is read."""
    response = _client(_StubAIProvider()).get("/grading/availability")

    assert response.status_code == 401
