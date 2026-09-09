"""Tests for wiring the real ``OCRProvider`` into the sidecar, and for what a
host with no Document AI processor gets instead (Issue #114).

Nothing here reaches a network or reads this machine's own configuration.
The one host probe ``create_ocr_provider`` makes -- is ADC set up -- is
injected, for the reason ``docs/quality-gates.md`` records: a test that
inherits it is green on a developer machine and red on a runner, or the other
way round.

Mirrors ``test_grading_availability.py`` deliberately, including its leak
matrix. The reason string here reaches the same three places (the HTTP body,
the screen, the sidecar log), so it needs the same guarantee.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx
import pytest
from fastapi.testclient import TestClient

from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.ocr.document_ai_provider import DocumentAiOCRProvider
from auto_scoring.adapters.ocr.factory import OCRProviderConfigError, create_ocr_provider
from auto_scoring.adapters.ocr.unconfigured_provider import UnconfiguredOCRProvider
from auto_scoring.api.app import build_ocr_provider, create_app
from auto_scoring.domain.ocr import OCRProvider, OCRUnavailable
from tests.test_ocr_provider_contract import PROCESSOR, FakeAdcCredentials

_TOKEN = "test-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}

#: Obviously fake, and the exact string every "no secret escaped" assertion
#: below searches for. Never a real key shape anyone could mistake for one.
_FAKE_KEY = "fake-api-key-DO-NOT-USE-90bd1f"

#: Every variable `create_ocr_provider` reads. The matrix at the bottom puts
#: `_FAKE_KEY` into each in turn: an operator who pastes a credential into
#: the wrong variable must not have it read back from the screen, the HTTP
#: response, or the sidecar log. A list of *names*, not of known-bad
#: messages, so it also catches a future message that starts quoting a value.
_CONFIGURATION_VARIABLES = (
    "AUTO_SCORING_DOCUMENT_AI_PROCESSOR",
    "AUTO_SCORING_VERTEX_PROJECT",
)

_CONFIGURED = {"AUTO_SCORING_DOCUMENT_AI_PROCESSOR": PROCESSOR}


def _adc_available(project_id: str | None) -> AdcTokenSource:
    return AdcTokenSource(credentials=FakeAdcCredentials(), project_id=project_id or "test-project")


def _adc_missing(project_id: str | None) -> AdcTokenSource:
    raise AdcCredentialsError(
        "Google Application Default Credentials are not available (DefaultCredentialsError). "
        "Run `gcloud auth application-default login`"
    )


def _factory_with_adc(env: Mapping[str, str]) -> OCRProvider:
    return create_ocr_provider(env, token_source_factory=_adc_available)


def _factory_without_adc(env: Mapping[str, str]) -> OCRProvider:
    return create_ocr_provider(env, token_source_factory=_adc_missing)


def _client(provider: OCRProvider | None) -> TestClient:
    return TestClient(create_app(api_token=_TOKEN, ocr_provider=provider))


def _availability(client: TestClient) -> dict[str, object]:
    response = client.get("/ocr/availability", headers=_AUTH)
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


# --------------------------------------------------------------------------- #
# The factory
# --------------------------------------------------------------------------- #
def test_a_configured_host_gets_the_document_ai_adapter() -> None:
    provider = create_ocr_provider(_CONFIGURED, token_source_factory=_adc_available)

    assert isinstance(provider, DocumentAiOCRProvider)
    assert provider.name == "document_ai"


def test_an_unset_processor_names_the_variable() -> None:
    with pytest.raises(OCRProviderConfigError) as error:
        create_ocr_provider({}, token_source_factory=_adc_available)

    assert "AUTO_SCORING_DOCUMENT_AI_PROCESSOR" in str(error.value)


@pytest.mark.parametrize(
    "processor",
    [
        "just-an-id",
        "projects/p/locations/l",
        "projects/p/locations/l/processors/id/extra",
        "projects//locations/l/processors/id",
        "projects/p/locations/l/processorz/id",
    ],
)
def test_a_value_that_is_not_a_resource_name_is_refused_at_startup(processor: str) -> None:
    """Not at the first recognition call, hours later, on a queue nobody is
    watching -- a typo in this variable is something an operator can fix now,
    and `build_ocr_provider` turns this into a reason the app displays."""
    with pytest.raises(OCRProviderConfigError) as error:
        create_ocr_provider(
            {"AUTO_SCORING_DOCUMENT_AI_PROCESSOR": processor},
            token_source_factory=_adc_available,
        )

    assert "AUTO_SCORING_DOCUMENT_AI_PROCESSOR" in str(error.value)
    assert processor not in str(error.value)


def test_a_host_without_adc_is_refused_and_told_to_log_in() -> None:
    with pytest.raises(OCRProviderConfigError) as error:
        create_ocr_provider(_CONFIGURED, token_source_factory=_adc_missing)

    assert "gcloud auth application-default login" in str(error.value)


# --------------------------------------------------------------------------- #
# build_ocr_provider: degrade, never raise
# --------------------------------------------------------------------------- #
def test_build_ocr_provider_returns_the_configured_adapter() -> None:
    assert isinstance(
        build_ocr_provider(_CONFIGURED, factory=_factory_with_adc), DocumentAiOCRProvider
    )


def test_build_ocr_provider_never_raises_on_an_unconfigured_host() -> None:
    """The whole point of Issue #114's second acceptance criterion: a machine
    with no Document AI processor still starts, still grades, and says why
    OCR is off -- it does not fail to launch."""
    provider = build_ocr_provider({}, factory=_factory_with_adc)

    assert isinstance(provider, UnconfiguredOCRProvider)
    assert "AUTO_SCORING_DOCUMENT_AI_PROCESSOR" in provider.reason


def test_the_unconfigured_provider_raises_rather_than_inventing_a_reading() -> None:
    """It must not answer. `NullOCRProvider` did -- confidence 0.0 on an empty
    string -- and design section 8.1.4 forbids exactly that ("読めていない
    ものに数値を与えない")."""
    provider = build_ocr_provider({}, factory=_factory_with_adc)

    with pytest.raises(OCRUnavailable):
        provider.recognize(b"\x89PNG\r\n\x1a\n")


def test_build_ocr_provider_keeps_an_unexpected_failure_message_out_of_the_reason() -> None:
    def _explodes(env: Mapping[str, str]) -> OCRProvider:
        raise RuntimeError(f"connecting through http://user:{_FAKE_KEY}@proxy.invalid failed")

    provider = build_ocr_provider({**_CONFIGURED}, factory=_explodes)

    assert isinstance(provider, UnconfiguredOCRProvider)
    assert "RuntimeError" in provider.reason
    assert _FAKE_KEY not in provider.reason
    assert "proxy.invalid" not in provider.reason


# --------------------------------------------------------------------------- #
# GET /ocr/availability
# --------------------------------------------------------------------------- #
def test_availability_reports_the_reason_when_ocr_is_unconfigured() -> None:
    client = _client(UnconfiguredOCRProvider("AUTO_SCORING_DOCUMENT_AI_PROCESSOR is not set"))

    assert _availability(client) == {
        "available": False,
        "reason": "AUTO_SCORING_DOCUMENT_AI_PROCESSOR is not set",
    }


def test_availability_reports_available_with_a_configured_adapter() -> None:
    client = _client(create_ocr_provider(_CONFIGURED, token_source_factory=_adc_available))

    assert _availability(client) == {"available": True, "reason": None}


def test_availability_is_unavailable_when_no_provider_was_injected() -> None:
    """`create_app` has no "recognize with a placeholder" default any more:
    a caller that supplies nothing gets an app that says so, rather than one
    that quietly persists ``confidence=0.0`` readings (Issue #114)."""
    assert _availability(_client(None))["available"] is False


def test_availability_requires_the_bearer_token() -> None:
    response = _client(None).get("/ocr/availability")

    assert response.status_code == 401


def test_a_reason_that_quotes_a_configuration_value_is_scrubbed_anyway() -> None:
    """The gate, not the discipline. `factory.py` is forbidden from quoting a
    configuration value and the matrix below holds it to that; this asserts
    the other half -- a future message that quotes one anyway still does not
    reach the app, because `build_ocr_provider` redacts against this host's
    own configuration on the way out (`api.secret_redaction`)."""

    def _quotes_the_value(env: Mapping[str, str]) -> OCRProvider:
        raise OCRProviderConfigError(
            "AUTO_SCORING_DOCUMENT_AI_PROCESSOR is not usable: "
            f"{env['AUTO_SCORING_DOCUMENT_AI_PROCESSOR']}"
        )

    provider = build_ocr_provider(
        {"AUTO_SCORING_DOCUMENT_AI_PROCESSOR": _FAKE_KEY}, factory=_quotes_the_value
    )

    assert isinstance(provider, UnconfiguredOCRProvider)
    assert "AUTO_SCORING_DOCUMENT_AI_PROCESSOR" in provider.reason
    assert _FAKE_KEY not in provider.reason


@pytest.mark.parametrize("variable", _CONFIGURATION_VARIABLES)
def test_no_configuration_value_reaches_the_published_reason(variable: str) -> None:
    """The leak matrix: whatever an operator put in ``variable``, it is not
    in what this host tells the app -- checked at both ends, the provider's
    own ``reason`` (which the sidecar also logs) and the HTTP body."""
    provider = build_ocr_provider(
        {**_CONFIGURED, variable: _FAKE_KEY}, factory=_factory_without_adc
    )

    if isinstance(provider, UnconfiguredOCRProvider):
        assert _FAKE_KEY not in provider.reason
    assert _FAKE_KEY not in _client(provider).get("/ocr/availability", headers=_AUTH).text


def test_the_processor_resource_name_never_reaches_the_availability_body() -> None:
    """A configured host publishes ``available: true`` and nothing else. The
    resource name carries the real GCP project id, which is exactly the kind
    of value AGENTS.md "Security" keeps out of published channels."""
    client = _client(create_ocr_provider(_CONFIGURED, token_source_factory=_adc_available))

    assert PROCESSOR not in client.get("/ocr/availability", headers=_AUTH).text


def test_a_recognize_call_after_adc_expires_is_unavailable_not_a_failure() -> None:
    """A login that lapsed mid-session is still "this host cannot do OCR",
    not "this call failed": no amount of retrying installs credentials, and
    grading must carry on (design section 24)."""

    class _ExpiredTokens(AdcTokenSource):
        def bearer_token(self) -> str:
            raise AdcCredentialsError("Refreshing the ADC access token failed (RefreshError)")

    provider = DocumentAiOCRProvider(
        processor=PROCESSOR,
        tokens=_ExpiredTokens(credentials=FakeAdcCredentials(), project_id="test-project"),
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))),
    )

    with pytest.raises(OCRUnavailable):
        provider.recognize(b"\x89PNG\r\n\x1a\n")
