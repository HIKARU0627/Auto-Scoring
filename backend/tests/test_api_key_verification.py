"""One real call with the saved key, and the five answers it can give
(Issue #96).

**No test here reaches OpenRouter.** Every one drives an `httpx.MockTransport`,
because the alternative is a suite that is flaky when the network is and, over
a CI run, somebody's invoice. What the real endpoint is and why it is free is
argued in `adapters.credentials.verification`'s own docstring.
"""

from __future__ import annotations

import httpx
import pytest

from auto_scoring.adapters.credentials.api_keys import API_KEY_SLOTS
from auto_scoring.adapters.credentials.verification import (
    VerificationResult,
    verify_api_key,
)

#: Obviously fake, and the exact string every "no secret escaped" assertion
#: searches for. Never a real key shape anyone could mistake for one.
_FAKE_KEY = "fake-openrouter-key-DO-NOT-USE-4c1f9a"

_OPENROUTER = API_KEY_SLOTS[0]


def _verification_client(handler: object) -> httpx.Client:
    return httpx.Client(
        base_url="https://openrouter.test/api/v1",
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
    )


def test_verify_reports_success_and_sends_the_key_as_a_bearer_token() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        seen["path"] = request.url.path
        return httpx.Response(200, json={"data": {"usage": 0.5, "limit": None}})

    with _verification_client(handler) as client:
        outcome = verify_api_key(_OPENROUTER, _FAKE_KEY, client=client)

    assert outcome.result is VerificationResult.OK
    assert seen["auth"] == f"Bearer {_FAKE_KEY}"
    # `GET /key`, never a completion: the button must not cost the user
    # money every time they press it while unsure.
    assert seen["path"].endswith("/key")


@pytest.mark.parametrize("status_code", [401, 403])
def test_verify_tells_a_rejected_key_apart(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": _FAKE_KEY}})

    with _verification_client(handler) as client:
        outcome = verify_api_key(_OPENROUTER, _FAKE_KEY, client=client)

    assert outcome.result is VerificationResult.UNAUTHORIZED
    assert outcome.status_code == status_code
    # The body echoed the credential back. It goes no further.
    assert _FAKE_KEY not in outcome.detail


def test_verify_tells_an_unreachable_network_apart() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    with _verification_client(handler) as client:
        outcome = verify_api_key(_OPENROUTER, _FAKE_KEY, client=client)

    assert outcome.result is VerificationResult.UNREACHABLE
    assert outcome.status_code is None


def test_verify_tells_a_provider_side_failure_apart() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream on fire")

    with _verification_client(handler) as client:
        outcome = verify_api_key(_OPENROUTER, _FAKE_KEY, client=client)

    assert outcome.result is VerificationResult.PROVIDER_ERROR
    assert outcome.status_code == 500


def test_verify_reports_a_spent_key_rather_than_a_clean_success() -> None:
    """A live key with no credit authenticates perfectly and grades nothing.
    A green tick the first grading job contradicts is worse than no button."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"usage": 5.0, "limit": 5.0}})

    with _verification_client(handler) as client:
        outcome = verify_api_key(_OPENROUTER, _FAKE_KEY, client=client)

    assert outcome.result is VerificationResult.NO_CREDIT


def test_verify_accepts_a_body_it_cannot_read() -> None:
    """The key answered, which is what was asked. A response shape this app
    does not recognise is not an authentication problem."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json at all")

    with _verification_client(handler) as client:
        outcome = verify_api_key(_OPENROUTER, _FAKE_KEY, client=client)

    assert outcome.result is VerificationResult.OK
