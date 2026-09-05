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


class MaxBodySizeMiddleware:
    """Rejects any request whose body exceeds ``max_bytes`` with ``413``.

    Fast path: a well-formed ``Content-Length`` header is checked before a
    single byte of the body is read. Slow path (no header, or one that
    understates the true size -- e.g. chunked transfer-encoding): this
    middleware itself drains and buffers ``http.request`` messages up to
    ``max_bytes`` + 1, deciding *before* the wrapped app is ever invoked --
    not by raising once the app is already mid-parse.

    That "decide first, then either reject or replay" shape is deliberate:
    an earlier version wrapped ``receive`` and raised once the running total
    went over the limit, from *inside* the wrapped app's own body-reading
    call. For a multipart request that call is FastAPI's
    ``await request.form()``, which wraps its own body-parsing step in a
    blanket ``except Exception: raise HTTPException(400, ...)`` -- so the
    413 this middleware meant to send never reached the client; FastAPI's
    own handler swallowed it into a generic 400 first
    (``docs/answer-intake-and-preprocessing.md`` documents the 413). Nothing
    can distinguish "raised by us" from "raised by anything else" once it is
    the *wrapped app* that is doing the raising, so the only reliable fix is
    to never let the wrapped app start until the size is known good.
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

        buffered: list[Message] = []
        total = 0
        while True:
            message = await receive()
            buffered.append(message)
            if message["type"] != "http.request":
                # e.g. the client disconnected mid-body; nothing more to read.
                break
            total += len(message.get("body") or b"")
            if total > self._max_bytes:
                await _send_413(send)
                return
            if not message.get("more_body", False):
                break

        buffered_iter = iter(buffered)

        async def replay_receive() -> Message:
            try:
                return next(buffered_iter)
            except StopIteration:
                return await receive()

        await self._app(scope, replay_receive, send)


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
