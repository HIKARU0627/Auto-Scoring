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
"""

from __future__ import annotations

from typing import NoReturn

import httpx

from auto_scoring.domain.ai_provider import (
    ProviderRateLimitedError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailable,
)

_TOO_MANY_REQUESTS = 429


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
        if status == _TOO_MANY_REQUESTS:
            raise ProviderRateLimitedError(detail) from None
        if status >= 500:
            raise ProviderServerError(detail) from None
        raise ProviderUnavailable(detail) from None
    raise ProviderUnavailable(f"{label} request failed: {type(exc).__name__}") from None
