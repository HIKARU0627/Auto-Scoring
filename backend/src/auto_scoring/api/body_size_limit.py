"""ASGI middleware that rejects an over-limit request body before FastAPI's
multipart parser (and ``UploadFile``'s ``SpooledTemporaryFile``) ever buffers
it.

``_read_upload_within_limit`` in ``api/app.py`` only bounds how much of an
upload the *handler* materializes into one ``bytes`` object -- by the time
that code runs, Starlette has already fully parsed and spooled the multipart
body (to memory, then to a temp file past its spool threshold) to build the
``UploadFile`` the handler receives. An authenticated caller sending a body
far larger than ``IntakeLimits.max_size_bytes`` could exhaust memory/disk
during that parse step alone, before any application-level check runs
(``AGENTS.md`` "Validate every input that crosses a trust boundary").

This middleware enforces the same ceiling at the ASGI ``receive`` boundary,
so an over-limit body is rejected while it is still streaming in.
"""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _BodyTooLarge(Exception):
    """Internal signal: the request body exceeded the configured limit."""


class MaxBodySizeMiddleware:
    """Rejects any request whose body exceeds ``max_bytes`` with ``413``.

    Fast path: a well-formed ``Content-Length`` header is checked before a
    single byte of the body is read. Slow path (no header, or one that
    understates the true size -- e.g. chunked transfer-encoding): bytes are
    counted as ``http.request`` messages arrive, aborting as soon as the
    running total exceeds ``max_bytes``, before the wrapped app (and its
    multipart parser) ever sees them.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        declared = _declared_content_length(scope)
        if declared is not None and declared > self._max_bytes:
            await _send_413(send)
            return

        total = 0

        async def guarded_receive() -> Message:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body") or b"")
                if total > self._max_bytes:
                    raise _BodyTooLarge
            return message

        try:
            await self._app(scope, guarded_receive, send)
        except _BodyTooLarge:
            await _send_413(send)


def _declared_content_length(scope: Scope) -> int | None:
    headers = Headers(scope=scope)
    declared = headers.get("content-length")
    if declared is None:
        return None
    try:
        return int(declared)
    except ValueError:
        return None


async def _send_413(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": b'{"detail":"request body exceeds size limit"}',
        }
    )
