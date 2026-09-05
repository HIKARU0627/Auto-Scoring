"""Unit tests for the ASGI-level submission-upload gate (Issue #17 review
round 8).

Drives `SubmissionUploadGateMiddleware` directly against synthetic ASGI
scope/receive/send callables, the same style as `test_body_size_limit.py`,
so a rejection can be shown to happen *before* the wrapped app -- and hence
before FastAPI's routing/dependency resolution and multipart parsing -- is
ever invoked.
"""

from __future__ import annotations

import threading

from starlette.types import Message, Receive, Scope, Send

from auto_scoring.api.submission_upload_gate import SubmissionUploadGateMiddleware

_TOKEN = "s3cr3t-token"


class _RecordingApp:
    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.called = True
        await send({"type": "http.response.start", "status": 201, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def _upload_scope(*, authorization: str | None = None) -> Scope:
    headers: list[tuple[bytes, bytes]] = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    return {
        "type": "http",
        "method": "POST",
        "path": "/tests/test-1/submissions",
        "headers": headers,
    }


async def _run(app: SubmissionUploadGateMiddleware, scope: Scope) -> list[Message]:
    sent: list[Message] = []

    async def receive() -> Message:
        raise AssertionError("receive must not be called once the gate rejects a request")

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


async def test_rejects_a_request_with_no_bearer_token_before_touching_the_body() -> None:
    recording = _RecordingApp()
    middleware = SubmissionUploadGateMiddleware(
        recording, api_token=_TOKEN, capacity=threading.Semaphore(1)
    )

    sent = await _run(middleware, _upload_scope())

    assert recording.called is False
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 401


async def test_rejects_a_request_with_the_wrong_bearer_token_before_touching_the_body() -> None:
    recording = _RecordingApp()
    middleware = SubmissionUploadGateMiddleware(
        recording, api_token=_TOKEN, capacity=threading.Semaphore(1)
    )

    sent = await _run(middleware, _upload_scope(authorization="Bearer wrong-token"))

    assert recording.called is False
    assert sent[0]["status"] == 401


async def test_rejects_when_capacity_is_exhausted_before_touching_the_body() -> None:
    recording = _RecordingApp()
    capacity = threading.Semaphore(1)
    capacity.acquire()  # simulate one in-flight upload already holding the slot
    middleware = SubmissionUploadGateMiddleware(recording, api_token=_TOKEN, capacity=capacity)

    sent = await _run(middleware, _upload_scope(authorization=f"Bearer {_TOKEN}"))

    assert recording.called is False
    assert sent[0]["status"] == 503


async def test_allows_an_authenticated_request_within_capacity_and_releases_it_after() -> None:
    recording = _RecordingApp()
    capacity = threading.Semaphore(1)
    middleware = SubmissionUploadGateMiddleware(recording, api_token=_TOKEN, capacity=capacity)

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    await middleware(_upload_scope(authorization=f"Bearer {_TOKEN}"), receive, send)

    assert recording.called is True
    assert sent[0]["status"] == 201
    # Released after the wrapped app finished, not held forever.
    assert capacity.acquire(blocking=False)


async def test_ignores_requests_outside_the_submission_upload_route() -> None:
    """No auth header, no capacity check -- other protected routes keep going
    through the ordinary `require_token` dependency instead.
    """
    recording = _RecordingApp()
    middleware = SubmissionUploadGateMiddleware(
        recording, api_token=_TOKEN, capacity=threading.Semaphore(0)
    )

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {"type": "http", "method": "GET", "path": "/tests", "headers": []}
    await middleware(scope, receive, send)

    assert recording.called is True
    assert sent[0]["status"] == 201
