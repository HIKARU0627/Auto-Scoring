"""`adapters.ai_grading._http` -- classification and ``Retry-After`` parsing
(Issue #35, Issue #153).

No network: `raise_classified_unavailable` takes a bare exception, so this
builds an `httpx.HTTPStatusError` by hand rather than going through a real
provider adapter's `MockTransport`. Every provider adapter (Vertex, OpenAI,
OpenRouter, Codex App Server) funnels its own failed calls through this one
function, so pinning behaviour here covers all of them without duplicating
the same parametrized test four times.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from auto_scoring.adapters.ai_grading._http import (
    parse_retry_after_seconds,
    raise_classified_unavailable,
)
from auto_scoring.domain.ai_provider import (
    ProviderRateLimitedError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailable,
)

_URL = "https://example.invalid/v1"
_SENSITIVE = "SENSITIVE-RESPONSE-BODY-MARKER"


def _status_error(status: int, *, headers: dict[str, str] | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", _URL)
    response = httpx.Response(status, request=request, headers=headers, text=_SENSITIVE)
    return httpx.HTTPStatusError(f"status {status}", request=request, response=response)


# --------------------------------------------------------------------------- #
# parse_retry_after_seconds -- pure given an injected `now`
# --------------------------------------------------------------------------- #
def test_parse_retry_after_seconds_delay_seconds_form() -> None:
    assert parse_retry_after_seconds("30", now=datetime.now(UTC)) == 30.0


def test_parse_retry_after_seconds_http_date_form() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    future = now + timedelta(seconds=45)
    http_date = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert parse_retry_after_seconds(http_date, now=now) == 45.0


def test_parse_retry_after_seconds_missing_header_is_none() -> None:
    assert parse_retry_after_seconds(None, now=datetime.now(UTC)) is None


@pytest.mark.parametrize("value", ["", "   ", "not-a-number", "-30", "Not, A Date"])
def test_parse_retry_after_seconds_malformed_or_negative_is_none(value: str) -> None:
    assert parse_retry_after_seconds(value, now=datetime.now(UTC)) is None


def test_parse_retry_after_seconds_past_http_date_is_none() -> None:
    """An HTTP-date already in the past resolves to a negative delta --
    treated the same as invalid, never a negative wait."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    past = now - timedelta(seconds=10)
    http_date = past.strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert parse_retry_after_seconds(http_date, now=now) is None


# --------------------------------------------------------------------------- #
# raise_classified_unavailable -- end to end from an HTTPStatusError
# --------------------------------------------------------------------------- #
def test_429_carries_the_parsed_retry_after_onto_the_exception() -> None:
    with pytest.raises(ProviderRateLimitedError) as error:
        raise_classified_unavailable(_status_error(429, headers={"Retry-After": "30"}), label="X")

    assert error.value.retry_after_seconds == 30.0
    assert error.value.status_code == 429
    assert _SENSITIVE not in str(error.value)


def test_429_with_no_retry_after_header_carries_none() -> None:
    with pytest.raises(ProviderRateLimitedError) as error:
        raise_classified_unavailable(_status_error(429), label="X")

    assert error.value.retry_after_seconds is None


def test_5xx_never_carries_a_retry_after() -> None:
    """A 5xx is not a rate limit -- `Retry-After` (even if a server sent one)
    must not leak into `ProviderServerError`, which has no such field to
    misuse it through, and TIMEOUT/SERVER_ERROR must stay on the ordinary
    exponential schedule."""
    with pytest.raises(ProviderServerError) as error:
        raise_classified_unavailable(_status_error(503, headers={"Retry-After": "30"}), label="X")

    assert error.value.retry_after_seconds is None


def test_timeout_is_a_timeout() -> None:
    with pytest.raises(ProviderTimeoutError):
        raise_classified_unavailable(httpx.ReadTimeout("timed out"), label="X")


def test_other_4xx_is_bare_unavailable_not_rate_limited() -> None:
    with pytest.raises(ProviderUnavailable) as error:
        raise_classified_unavailable(_status_error(401), label="X")

    assert not isinstance(error.value, ProviderRateLimitedError)
