"""Cleanup after a provider call (Issue #54 residual item 1).

Issue #54's 2026-09-11 棚卸し comment leaves exactly one unmeasured acceptance
item: cleanup. The live-run evidence (#6) proved authentication, the
one-question request shape, and ``AIGradingResult`` conformance, but neither
its report nor its ``out/`` directory recorded that a call leaves nothing
behind. This module pins that, offline, so it runs in ordinary CI.

Three facts, matching the two halves the comment names:

* the adopted providers (Vertex AI for grading, Google Document AI for OCR)
  are synchronous inline POSTs -- the grading crop travels as ``inlineData``
  and Document AI is sent as a ``rawDocument`` with ``skipHumanReview`` on,
  so neither opens a remote batch job or leaves a review copy;
* neither call writes an ``auto-scoring-*`` temporary directory;
* the one adopted path that *does* write a temporary file -- the Codex
  app-server fallback link -- removes its workspace (and the answer image in
  it) before ``grade()`` returns.

No network and no credentials: the HTTP providers get a recorded
``httpx.MockTransport`` and a fake ADC token, and the Codex link gets the
scripted app-server transport the contract tests already use. The same seam
makes the "cleanup was not called" mutation reachable without a live login
(see the PR body).

The ``auto-scoring-*`` snapshot is scoped to the test's own directory: the
``isolated_temp_root`` fixture points ``tempfile.gettempdir()`` at
``tmp_path`` so the provider writes there and the assertion observes only
that directory. Globbing the machine-wide ``/tmp`` (Issue #340) made these
tests fail whenever an unrelated concurrent process created or removed a
matching directory.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from google.auth.credentials import Credentials

from auto_scoring.adapters.ai_grading._google_adc import AdcTokenSource
from auto_scoring.adapters.ai_grading.codex_app_server_provider import CodexAppServerProvider
from auto_scoring.adapters.ai_grading.vertex_gemini_provider import VertexGeminiAIProvider
from auto_scoring.adapters.ocr.document_ai_provider import DocumentAiOCRProvider
from auto_scoring.domain.ai_provider import GradingRequest

from .test_ai_provider_codex_app_server_contract import _FakeAppServerTransport
from .test_ocr_provider_contract import document_ai_body

_CROP = b"\x89PNG\r\n\x1a\ncleanup-probe-crop"
_PROCESSOR = "projects/test-project/locations/us/processors/testprocessor"

_CLEANUP_REQUEST = GradingRequest(
    question_id="q-cleanup",
    prompt_text="設問",
    answer_image=_CROP,
    ocr_text="答案テキスト",
    model_answer="模範解答",
    rubric_text="1. 採点基準(配点5点)",
    criterion_ids=("c1",),
    max_score=5,
)


class _FakeAdcCredentials(Credentials):
    """ADC credentials that are always valid and never hit the network."""

    def __init__(self) -> None:
        super().__init__()  # type: ignore[no-untyped-call]
        self.token = "fake-access-token"

    def refresh(self, request: object) -> None:
        self.token = "fake-access-token"


def _fake_tokens() -> AdcTokenSource:
    return AdcTokenSource(credentials=_FakeAdcCredentials(), project_id="test-project")


class _RecordingTransport(httpx.BaseTransport):
    """Records every request body, then delegates to the wrapped transport."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self._inner = inner
        self.payloads: list[dict[str, Any]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        payload = _json_object(request.content)
        if payload is not None:
            self.payloads.append(payload)
        return self._inner.handle_request(request)


def _json_object(body: bytes) -> dict[str, Any] | None:
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _mock(body: dict[str, Any]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handle)


@pytest.fixture
def isolated_temp_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Confines ``tempfile`` writes to this test's own ``tmp_path``.

    The provider module calls ``tempfile.mkdtemp`` with no explicit ``dir``, so
    it lands wherever ``tempfile.gettempdir()`` points. Redirecting that at
    ``tmp_path`` means both the provider's writes *and* this module's
    observation stay inside the test's own directory, so a concurrent process
    creating or removing a machine-wide ``/tmp/auto-scoring-*`` cannot flip
    the assertion (Issue #340).
    """
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return tmp_path


def _auto_scoring_temp_dirs(root: Path) -> set[str]:
    return {str(path) for path in root.glob("auto-scoring-*")}


def _ai_ok_body() -> dict[str, Any]:
    content = json.dumps(
        {
            "recognition": {"text": "答案テキスト", "confidence": 0.9},
            "grading": {"score": 4, "maxScore": 5, "confidence": 0.8},
            "criteria": [{"index": 1, "result": "pass", "confidence": 0.9, "rationale": "根拠"}],
            "comment": "コメント",
            "rationale": "根拠",
            "annotations": [],
            "answerImage": None,
        }
    )
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": content}]}}]}


def test_adopted_providers_write_no_temporary_file_and_upload_no_remote_resource(
    isolated_temp_root: Path,
) -> None:
    """A grading and an OCR call leave the disk and the far end clean.

    What is checked is the *shape* of the request that actually crossed the
    HTTP boundary: an inline crop is not an upload, and ``skipHumanReview``
    means Document AI keeps no copy in its own review queue. The
    ``auto-scoring-*`` snapshot -- scoped to this test's own temp root -- then
    confirms neither call created a local temporary directory either.
    """
    before = _auto_scoring_temp_dirs(isolated_temp_root)

    ai_transport = _RecordingTransport(_mock(_ai_ok_body()))
    VertexGeminiAIProvider(
        model="gemini-cleanup-probe",
        prompt_version="cleanup",
        tokens=_fake_tokens(),
        client=httpx.Client(transport=ai_transport),
    ).grade(_CLEANUP_REQUEST)

    ocr_transport = _RecordingTransport(_mock(document_ai_body("光合成", ((0, 3, 0.97),))))
    DocumentAiOCRProvider(
        processor=_PROCESSOR,
        tokens=_fake_tokens(),
        client=httpx.Client(transport=ocr_transport),
    ).recognize(_CROP)

    assert _auto_scoring_temp_dirs(isolated_temp_root) == before, (
        "a provider left a temporary directory behind"
    )

    assert ai_transport.payloads, "the grading provider sent no payload to inspect"
    for payload in ai_transport.payloads:
        parts = payload.get("contents", [{}])[0].get("parts", [])
        assert any(isinstance(part, dict) and "inlineData" in part for part in parts), (
            "the grading crop must travel inline, not as an uploaded resource"
        )

    assert ocr_transport.payloads, "the OCR provider sent no payload to inspect"
    for payload in ocr_transport.payloads:
        assert payload.get("skipHumanReview") is True, (
            "Document AI must not keep a copy in its own human-review queue"
        )
        assert "rawDocument" in payload


def test_codex_provider_removes_its_temporary_workspace(isolated_temp_root: Path) -> None:
    """The answer image does not survive the grading call.

    The Codex app-server link is the one adopted path that writes the crop to
    a per-call temporary workspace (``_write_temp_workspace``). ``grade()``
    must remove it in its ``finally`` block, even though this test uses the
    scripted app-server transport -- so the assertion is reachable without a
    live Codex login. The workspace is created under the isolated root, so the
    snapshot cannot see unrelated machine-wide temp directories.
    """
    before = _auto_scoring_temp_dirs(isolated_temp_root)

    transport = _FakeAppServerTransport()
    provider = CodexAppServerProvider(prompt_version="cleanup", transport=transport)
    written: list[str] = []
    original_request = transport.request

    def _spying_request(
        method: str, params: dict[str, object], *, timeout_seconds: float
    ) -> dict[str, object]:
        if method == "turn/start":
            input_items = params["input"]
            assert isinstance(input_items, list)
            written.append(str(input_items[1]["path"]))
        return original_request(method, params, timeout_seconds=timeout_seconds)

    transport.request = _spying_request  # type: ignore[method-assign]
    provider.grade(_CLEANUP_REQUEST)

    assert written, "the Codex call wrote no temporary workspace"
    assert not os.path.exists(written[0]), "the answer image was left on disk"
    assert _auto_scoring_temp_dirs(isolated_temp_root) == before, (
        "the temporary workspace was left behind"
    )
