"""ASGI middleware that gates large-body routes before FastAPI ever parses
their body -- multipart file uploads and the one plain-JSON route whose body
can grow just as unboundedly.

FastAPI resolves a path operation's dependencies (auth) and its body
parameters (``File``/``Form`` via ``await request.form()``, or a Pydantic
model via ``await request.json()``) together, as part of routing into the
endpoint. Neither one runs strictly before the other -- in particular, an
unauthenticated caller's request body is already spooled/parsed before
``require_token`` (an ordinary ``Depends``) gets a chance to reject it. The
same is true of the capacity semaphore this module used to be: acquiring it
*inside* the async handler only ever ran after the body had already been
fully parsed.

That means, even with per-request body-size limits in place
(``body_size_limit.py``), N concurrent requests near that limit -- including
ones with no valid bearer token at all -- can each make FastAPI spool/parse
a full body before any of them is ever rejected, unboundedly piling up
parser memory/temp-disk usage (``AGENTS.md`` "Validate every input that
crosses a trust boundary"; "機能レベルのrate limiting").

This middleware checks both at the true ASGI ``receive`` boundary, before a
single byte of the body is read, and only for the routes named by
``_GATED_ROUTES`` below -- other protected routes (``/score``, ``GET
/tests``, ...) have no body worth gating and keep going through the
ordinary ``require_token`` dependency.
"""

from __future__ import annotations

import hmac
import re
import threading

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

#: (method, path pattern) pairs this middleware protects -- every route
#: whose body FastAPI would otherwise spool/parse before any auth/capacity
#: check runs: ``POST /tests/{test_id}/submissions`` (one answer PDF),
#: ``POST /tests`` (Issue #16 registration: two independently-limited PDFs
#: in one request, so it can carry just as much unauthenticated body as an
#: answer upload can), and ``PUT /tests/{test_id}/profile`` (an unbounded
#: JSON region array -- the same pre-auth body-parsing memory exhaustion
#: this middleware exists to prevent, just via `request.json()` instead of
#: a multipart parser; Issue #16 review round 8).
_GATED_ROUTES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("POST", re.compile(r"^/tests/[^/]+/submissions$")),
    ("POST", re.compile(r"^/tests$")),
    ("PUT", re.compile(r"^/tests/[^/]+/profile$")),
)


def _is_gated(method: str, path: str) -> bool:
    return any(
        method == gated_method and pattern.match(path) for gated_method, pattern in _GATED_ROUTES
    )


class SubmissionUploadGateMiddleware:
    """Rejects an unauthenticated or excess-concurrency upload request
    before it, or its body, ever reaches FastAPI's routing/dependency
    resolution.

    Any request not matching ``_GATED_ROUTES`` is passed through untouched.
    """

    def __init__(self, app: ASGIApp, *, api_token: str, capacity: threading.Semaphore) -> None:
        self._app = app
        self._api_token = api_token
        self._capacity = capacity

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _is_gated(scope["method"], scope["path"]):
            await self._app(scope, receive, send)
            return

        if not _has_valid_bearer_token(scope, self._api_token):
            await _send_401(send)
            return

        # Non-blocking: queuing here would just move the same unbounded
        # pile-up from "requests holding a full parsed body" to "requests
        # blocked in this middleware", without bounding memory any better.
        if not self._capacity.acquire(blocking=False):
            await _send_503(send)
            return
        try:
            await self._app(scope, receive, send)
        finally:
            self._capacity.release()


def _has_valid_bearer_token(scope: Scope, expected: str) -> bool:
    headers = Headers(scope=scope)
    scheme, _, param = headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(param, expected)


async def _send_401(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b"Bearer"),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": b'{"detail":"Missing or invalid bearer token"}',
        }
    )


async def _send_503(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 503,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": (
                b'{"detail":"too many submissions are being processed '
                b'right now; try again shortly"}'
            ),
        }
    )
