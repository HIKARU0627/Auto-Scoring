"""Turning a failed HTTP call into the ``ProviderUnavailable`` subclass the
fallback chain and the job queue both classify on (Issue #35).

``docs/ai-grading-pipeline.md`` "どの失敗で次へ落とすか" (Issue #81) keys both
the fallback decision and ``domain.models.ErrorCategory`` on the *specific*
exception type -- 429 is a rate limit, 5xx is a provider-side outage, a
timeout is a timeout. An adapter that raised a bare
:class:`~auto_scoring.domain.ai_provider.ProviderUnavailable` for all three
(what ``openrouter_provider.py`` did before this module existed) collapses
that distinction, and ``GradingJobProcessor`` then has to fall back to
``ErrorCategory.UNKNOWN`` for a failure it could have classified exactly.

Never renders a response body: a body can echo the request (the answer-image
crop, the OCR text, the rubric) and, for an auth failure, part of the
credential. Only the numeric status code and the exception type name cross
into a raised message (AGENTS.md "Security").

**What the adapters must hand to this function.** ``FallbackAIProvider``
moves to the next provider on exactly the two exceptions the port declares,
so an httpx failure that no ``except`` clause matches stops the whole chain.
Listing the interesting subclasses by hand was not enough -- an adapter
catching ``TransportError``/``HTTPStatusError``/``TimeoutException`` let
``httpx.DecodingError`` (a corrupt gzip body, say) straight through, because
it descends from ``RequestError`` and not from ``TransportError`` (code
review finding). Every adapter therefore catches :data:`CONVERTIBLE_HTTP_ERRORS`
rather than an enumeration:

* ``httpx.HTTPError`` is httpx's own root for everything a request can
  raise -- ``RequestError`` (and so ``TransportError``, ``TimeoutException``,
  ``ProtocolError``, ``DecodingError``, ``TooManyRedirects``) plus
  ``HTTPStatusError``. A future httpx release adding another subclass is
  covered without another review round.
* ``json.JSONDecodeError`` / ``UnicodeDecodeError`` come from
  ``Response.json()``, not from the request, so they sit outside that tree.

The three httpx exceptions deliberately left out -- ``InvalidURL``,
``CookieConflict``, ``StreamError`` -- are not remote failures: they mean a
malformed base URL, a misused cookie API, or a misused streaming API, i.e.
this repository's own bug. Converting those into "this provider is
unavailable, try the next one" would hide a configuration error behind a
silent fallback.
"""

from __future__ import annotations

import json
from typing import NoReturn

import httpx

from auto_scoring.domain.ai_provider import (
    ProviderRateLimitedError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailable,
)

_TOO_MANY_REQUESTS = 429

#: The exception tuple every adapter's ``grade()`` catches around its HTTP
#: call -- see the module docstring for why it is a root class and not a
#: list of interesting subclasses.
CONVERTIBLE_HTTP_ERRORS = (httpx.HTTPError, json.JSONDecodeError, UnicodeDecodeError)


def raise_classified_unavailable(exc: Exception, *, label: str) -> NoReturn:
    """Re-raise a failed HTTP call as the most specific
    :class:`ProviderUnavailable` subclass that fits it.

    ``label`` names the transport in the message (e.g. ``"OpenRouter"``) --
    a fixed string from the adapter itself, never anything derived from the
    request or the response.

    Anything that is not a recognized timeout / 429 / 5xx (a 4xx
    auth/config error, a transport error, a body that is not decodable
    JSON) stays a bare ``ProviderUnavailable``: the pipeline's table has no
    "fall through faster" entry for those, and inventing a more specific
    category would make the queue retry a permanent misconfiguration
    (docs/ai-grading-pipeline.md).

    Raised with ``from None`` throughout: Python renders a chained cause's
    own ``str()``, and ``httpx.HTTPStatusError``'s includes the response
    body (code review finding, mirrored from ``openrouter_provider.py``).
    """
    if isinstance(exc, httpx.TimeoutException):
        raise ProviderTimeoutError(f"{label} request timed out") from None
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail = f"{label} request failed with status {status}"
        # The number travels as data as well as in the text: it is what
        # `ProviderAttempt` records and what tells an operator apart a
        # revoked login (401), a project without the API enabled (403) and
        # a misspelled model (404) once the chain has failed (Issue #97
        # review round 4). A number cannot carry configuration.
        if status == _TOO_MANY_REQUESTS:
            raise ProviderRateLimitedError(detail, status_code=status) from None
        if status >= 500:
            raise ProviderServerError(detail, status_code=status) from None
        raise ProviderUnavailable(detail, status_code=status) from None
    raise ProviderUnavailable(f"{label} request failed: {type(exc).__name__}") from None
