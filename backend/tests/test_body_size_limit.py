"""Unit tests for the ASGI-level upload size guard (Issue #17 review follow-up).

Drives `MaxBodySizeMiddleware` directly against synthetic ASGI scope/receive/
send callables rather than through `TestClient`, so both the Content-Length
fast path and the no-Content-Length streaming path can be exercised
precisely -- `TestClient`/httpx always sets a real Content-Length for a
`files=` upload, so it can't reach the streaming branch on its own.
"""

from __future__ import annotations

from starlette.types import Message, Receive, Scope, Send

from auto_scoring.api.body_size_limit import MaxBodySizeMiddleware


class _RecordingApp:
    """A minimal downstream ASGI app: drains the body, then replies 200."""

    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.called = True
        while True:
            message = await receive()
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def _http_scope(headers: dict[str, str] | None = None) -> Scope:
    return {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }


async def _run(app: MaxBodySizeMiddleware, scope: Scope, receive: Receive) -> list[Message]:
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


async def test_rejects_via_content_length_header_before_reading_body() -> None:
    recording = _RecordingApp()
    middleware = MaxBodySizeMiddleware(recording, max_bytes=10)

    async def receive() -> Message:
        raise AssertionError("receive must not be called once Content-Length exceeds the limit")

    sent = await _run(middleware, _http_scope({"content-length": "100"}), receive)

    assert recording.called is False
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413


async def test_rejects_a_streamed_body_with_no_content_length_header() -> None:
    """No Content-Length (or one that understates reality, e.g. chunked
    transfer-encoding) still gets caught, by counting bytes as they stream in.
    """
    recording = _RecordingApp()
    middleware = MaxBodySizeMiddleware(recording, max_bytes=10)

    chunks = [b"0123456789", b"one-more-chunk-past-the-limit"]

    async def receive() -> Message:
        chunk = chunks.pop(0)
        return {"type": "http.request", "body": chunk, "more_body": bool(chunks)}

    sent = await _run(middleware, _http_scope(), receive)

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413


async def test_allows_a_body_within_the_limit() -> None:
    recording = _RecordingApp()
    middleware = MaxBodySizeMiddleware(recording, max_bytes=100)

    async def receive() -> Message:
        return {"type": "http.request", "body": b"small body", "more_body": False}

    sent = await _run(middleware, _http_scope(), receive)

    assert recording.called is True
    assert sent[0]["status"] == 200


async def test_ignores_non_http_scopes() -> None:
    recording = _RecordingApp()
    middleware = MaxBodySizeMiddleware(recording, max_bytes=1)

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(_message: Message) -> None:
        pass

    await middleware({"type": "lifespan"}, receive, send)

    assert recording.called is True
