"""Contract tests for :class:`CodexAppServerProvider` (Issue #44).

Exercises ``AIProviderContract`` against a fake in-memory JSON-RPC transport
-- never spawns a real ``codex`` process and never requires a live Codex
login/subscription. A real end-to-end call against ``codex app-server`` is a
separate, explicit live probe (``docs/poc-2-ai-grading.md`` section 7.3),
never part of this offline suite.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

from auto_scoring.adapters.ai_grading._prompt import GRADING_SYSTEM_INSTRUCTIONS
from auto_scoring.adapters.ai_grading.codex_app_server_provider import (
    CodexAppServerProvider,
    _cleanup_workspace,
    _minimal_environment,
    _SubprocessAppServerTransport,
)
from auto_scoring.domain.ai_provider import AIProvider, ProviderUnavailable, SchemaViolation

from .test_ai_provider_contract import _VALID_REQUEST, AIProviderContract

_OCR_TEXT = "答案テキスト"
_QUESTION_ID_MARKER = 'The questionId in your response must be exactly "'


def _canned_grading_json(question_id: str) -> str:
    if question_id == "malformed":
        return json.dumps({"questionId": question_id, "grading": {"score": 1}})
    return json.dumps(
        {
            "questionId": question_id,
            "recognition": {"text": _OCR_TEXT, "confidence": 0.9},
            "grading": {"score": 4, "maxScore": 5, "confidence": 0.8},
            "criteria": [{"id": "c1", "result": "pass", "confidence": 0.9, "rationale": "根拠"}],
            "comment": "コメント",
            "rationale": "根拠",
            "annotations": [],
        }
    )


class _FakeAppServerTransport:
    """Replays a canned ``turn/completed`` notification instead of speaking
    to a real ``codex app-server`` subprocess. Test-only scaffolding, mirrors
    ``test_ai_provider_contract._ReplayAIProvider``."""

    def __init__(self) -> None:
        self._thread_id = "thread-1"
        self._last_question_id: str | None = None
        self.closed = False

    def request(
        self, method: str, params: dict[str, object], *, timeout_seconds: float
    ) -> dict[str, object]:
        if method == "initialize":
            return {"userAgent": "codex-fake/9.9.9"}
        if method == "thread/start":
            assert params["sandbox"] == "read-only"
            assert params["approvalPolicy"] == "never"
            assert params["developerInstructions"] == GRADING_SYSTEM_INSTRUCTIONS
            return {"thread": {"id": self._thread_id}, "model": "codex-fake-model"}
        if method == "turn/start":
            assert params["threadId"] == self._thread_id
            assert "outputSchema" in params
            input_items = params["input"]
            assert isinstance(input_items, list)
            text = input_items[0]["text"]
            start = text.index(_QUESTION_ID_MARKER) + len(_QUESTION_ID_MARKER)
            end = text.index('"', start)
            self._last_question_id = text[start:end]
            image_path = input_items[1]["path"]
            assert input_items[1]["type"] == "localImage"
            assert os.path.exists(image_path)  # the adapter must write the image to disk
            return {}
        raise AssertionError(f"unexpected method: {method}")

    def wait_for_notification(
        self,
        method: str,
        matches: Callable[[dict[str, object]], bool],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        assert method == "turn/completed"
        assert self._last_question_id is not None
        params: dict[str, object] = {
            "threadId": self._thread_id,
            "turn": {
                "id": "turn-1",
                "status": "completed",
                "items": [
                    {
                        "id": "item-1",
                        "type": "agentMessage",
                        "text": _canned_grading_json(self._last_question_id),
                    }
                ],
            },
        }
        assert matches(params)
        return params

    def discard_thread(self, thread_id: str) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def _make_provider() -> CodexAppServerProvider:
    return CodexAppServerProvider(prompt_version="v1", transport=_FakeAppServerTransport())


class TestCodexAppServerProviderContract(AIProviderContract):
    @pytest.fixture
    def provider(self) -> AIProvider:
        return _make_provider()


def test_grade_cleans_up_the_temporary_image_file() -> None:
    """The cropped answer image (potentially student handwriting) must not
    linger on disk after the turn completes (AGENTS.md "Security")."""
    transport = _FakeAppServerTransport()
    provider = CodexAppServerProvider(prompt_version="v1", transport=transport)

    written_paths: list[str] = []
    original_request = transport.request

    def _spying_request(
        method: str, params: dict[str, object], *, timeout_seconds: float
    ) -> dict[str, object]:
        if method == "turn/start":
            written_paths.append(params["input"][1]["path"])  # type: ignore[index]
        return original_request(method, params, timeout_seconds=timeout_seconds)

    transport.request = _spying_request  # type: ignore[method-assign]
    provider.grade(_VALID_REQUEST)

    assert written_paths
    assert not os.path.exists(written_paths[0])


def test_schema_violation_when_turn_produces_no_agent_message() -> None:
    class _NoAgentMessageTransport(_FakeAppServerTransport):
        def wait_for_notification(
            self,
            method: str,
            matches: Callable[[dict[str, object]], bool],
            *,
            timeout_seconds: float,
        ) -> dict[str, object]:
            params: dict[str, object] = {
                "threadId": self._thread_id,
                "turn": {"id": "turn-1", "status": "completed", "items": []},
            }
            assert matches(params)
            return params

    provider = CodexAppServerProvider(prompt_version="v1", transport=_NoAgentMessageTransport())
    with pytest.raises(SchemaViolation):
        provider.grade(_VALID_REQUEST)


def test_provider_unavailable_when_turn_fails() -> None:
    class _FailedTurnTransport(_FakeAppServerTransport):
        def wait_for_notification(
            self,
            method: str,
            matches: Callable[[dict[str, object]], bool],
            *,
            timeout_seconds: float,
        ) -> dict[str, object]:
            params: dict[str, object] = {
                "threadId": self._thread_id,
                "turn": {"id": "turn-1", "status": "failed", "items": []},
            }
            assert matches(params)
            return params

    provider = CodexAppServerProvider(prompt_version="v1", transport=_FailedTurnTransport())
    with pytest.raises(ProviderUnavailable):
        provider.grade(_VALID_REQUEST)


def test_provider_unavailable_on_notification_timeout() -> None:
    class _TimingOutTransport(_FakeAppServerTransport):
        def wait_for_notification(
            self,
            method: str,
            matches: Callable[[dict[str, object]], bool],
            *,
            timeout_seconds: float,
        ) -> dict[str, object]:
            raise TimeoutError

    provider = CodexAppServerProvider(prompt_version="v1", transport=_TimingOutTransport())
    with pytest.raises(ProviderUnavailable):
        provider.grade(_VALID_REQUEST)


def test_provider_unavailable_on_thread_start_timeout() -> None:
    """A hung `thread/start` (not just a hung notification wait) must also
    surface as ProviderUnavailable, not the builtin TimeoutError (code
    review finding)."""

    class _TimingOutOnThreadStart(_FakeAppServerTransport):
        def request(
            self, method: str, params: dict[str, object], *, timeout_seconds: float
        ) -> dict[str, object]:
            if method == "thread/start":
                raise TimeoutError
            return super().request(method, params, timeout_seconds=timeout_seconds)

    provider = CodexAppServerProvider(prompt_version="v1", transport=_TimingOutOnThreadStart())
    with pytest.raises(ProviderUnavailable):
        provider.grade(_VALID_REQUEST)


def test_descriptor_records_the_thread_start_resolved_model() -> None:
    """When AUTO_SCORING_CODEX_MODEL is unset, Codex substitutes its own
    default; the response descriptor must record what `thread/start`
    actually resolved to, not a placeholder like "default" (code review
    finding: a changed Codex default would otherwise silently pool
    incompatible runs into the same descriptor_key)."""
    provider = CodexAppServerProvider(prompt_version="v1", transport=_FakeAppServerTransport())
    response = provider.grade(_VALID_REQUEST)
    assert response.descriptor.model == "codex-fake-model"


def test_describe_does_not_accept_a_temperature_parameter() -> None:
    """Codex app-server's protocol has no temperature knob; the constructor
    must not accept one that would silently do nothing (code review
    finding)."""
    with pytest.raises(TypeError):
        CodexAppServerProvider(prompt_version="v1", temperature=0.5)  # type: ignore[call-arg]


def test_grade_discards_the_thread_after_completion() -> None:
    transport = _FakeAppServerTransport()
    discarded: list[str] = []
    original_discard = transport.discard_thread

    def _spying_discard(thread_id: str) -> None:
        discarded.append(thread_id)
        original_discard(thread_id)

    transport.discard_thread = _spying_discard  # type: ignore[method-assign]
    provider = CodexAppServerProvider(prompt_version="v1", transport=transport)
    provider.grade(_VALID_REQUEST)

    assert discarded == [transport._thread_id]


def test_subprocess_transport_discard_thread_prunes_only_that_thread() -> None:
    """White-box check of the buffer-growth fix: notifications belonging to
    an already-finished thread are dropped, others are kept (code review
    finding: an unbounded buffer would otherwise make every later grade()
    call on the reused subprocess scan a growing backlog)."""
    transport = _SubprocessAppServerTransport.__new__(_SubprocessAppServerTransport)
    transport._notification_buffer = [
        {"method": "item/completed", "params": {"threadId": "t1"}},
        {"method": "item/completed", "params": {"threadId": "t2"}},
        {"method": "turn/completed", "params": {"threadId": "t1"}},
    ]

    transport.discard_thread("t1")

    assert transport._notification_buffer == [
        {"method": "item/completed", "params": {"threadId": "t2"}},
    ]


def test_descriptor_records_the_codex_cli_user_agent_as_version() -> None:
    """`initialize`'s `userAgent` is the CLI's own version identifier; an
    upgraded, differently-behaving Codex CLI must not silently pool with
    older runs under `version=None` (code review finding)."""
    provider = CodexAppServerProvider(prompt_version="v1", transport=_FakeAppServerTransport())
    response = provider.grade(_VALID_REQUEST)
    assert response.descriptor.version == "codex-fake/9.9.9"
    assert provider.describe().version == "codex-fake/9.9.9"


def test_grade_uses_a_private_workspace_directory_not_the_shared_temp_root() -> None:
    """`cwd` must be a fresh, private-per-call directory -- never the
    shared global temp root, which a prompt-injected turn's still-permitted
    file reads could otherwise enumerate for unrelated temp files from
    other processes or submissions (code review finding)."""
    transport = _FakeAppServerTransport()
    captured_cwd: list[str] = []
    original_request = transport.request

    def _spying_request(
        method: str, params: dict[str, object], *, timeout_seconds: float
    ) -> dict[str, object]:
        if method == "thread/start":
            captured_cwd.append(params["cwd"])  # type: ignore[arg-type]
        return original_request(method, params, timeout_seconds=timeout_seconds)

    transport.request = _spying_request  # type: ignore[method-assign]
    provider = CodexAppServerProvider(prompt_version="v1", transport=transport)
    provider.grade(_VALID_REQUEST)

    assert captured_cwd
    assert captured_cwd[0] != tempfile.gettempdir()
    assert not os.path.exists(captured_cwd[0])  # cleaned up once the turn completes


def test_grade_disables_the_codex_shell_environment_and_turn_network_access() -> None:
    """Defense in depth beyond the already-minimal child-process
    environment: Codex's own shell-tool env inheritance is turned off, and
    the turn's sandbox policy explicitly denies network access (code
    review finding)."""
    transport = _FakeAppServerTransport()
    captured: dict[str, object] = {}
    original_request = transport.request

    def _spying_request(
        method: str, params: dict[str, object], *, timeout_seconds: float
    ) -> dict[str, object]:
        if method == "thread/start":
            captured["config"] = params.get("config")
        if method == "turn/start":
            captured["sandboxPolicy"] = params.get("sandboxPolicy")
        return original_request(method, params, timeout_seconds=timeout_seconds)

    transport.request = _spying_request  # type: ignore[method-assign]
    provider = CodexAppServerProvider(prompt_version="v1", transport=transport)
    provider.grade(_VALID_REQUEST)

    assert captured["config"] == {"shell_environment_policy": {"inherit": "none"}}
    assert captured["sandboxPolicy"] == {"type": "readOnly", "networkAccess": False}


def test_grade_resets_the_transport_after_a_provider_unavailable_error() -> None:
    """A dead transport (exited process, broken pipe, ...) must not be
    retried forever; the next call should build a fresh one instead of
    reusing the same broken transport (code review finding)."""

    class _AlwaysUnavailableAtThreadStart(_FakeAppServerTransport):
        def request(
            self, method: str, params: dict[str, object], *, timeout_seconds: float
        ) -> dict[str, object]:
            if method == "thread/start":
                raise ProviderUnavailable("codex app-server process exited unexpectedly")
            return super().request(method, params, timeout_seconds=timeout_seconds)

    provider = CodexAppServerProvider(
        prompt_version="v1", transport=_AlwaysUnavailableAtThreadStart()
    )
    with pytest.raises(ProviderUnavailable):
        provider.grade(_VALID_REQUEST)

    assert provider._transport is None
    assert provider._initialized is False


def test_minimal_environment_only_forwards_allowlisted_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `codex app-server` child process must not inherit this
    sidecar's full environment (DB connection strings, other providers'
    API keys, ...) -- only what Codex itself needs to run (code review
    finding: a prompt-injected turn's still-permitted shell commands could
    otherwise read and echo back an inherited secret)."""
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("AUTO_SCORING_OPENROUTER_API_KEY", "super-secret")
    monkeypatch.setenv("DATABASE_URL", "postgres://secret")

    env = _minimal_environment()

    assert env.get("PATH") == "/usr/bin"
    assert "AUTO_SCORING_OPENROUTER_API_KEY" not in env
    assert "DATABASE_URL" not in env


def test_grading_instructions_go_through_developer_instructions() -> None:
    """Fixed grading rules must be sent over the trusted
    `developerInstructions` channel, not mixed into the same `turn/start`
    input text as the student-controlled OCR reading (code review finding:
    a JSON Schema alone only constrains response shape, not whether an
    injected instruction inside the OCR text changes the awarded score)."""
    transport = _FakeAppServerTransport()
    captured: dict[str, object] = {}
    original_request = transport.request

    def _spying_request(
        method: str, params: dict[str, object], *, timeout_seconds: float
    ) -> dict[str, object]:
        if method == "thread/start":
            captured["developerInstructions"] = params.get("developerInstructions")
        if method == "turn/start":
            captured["input_text"] = params["input"][0]["text"]  # type: ignore[index]
        return original_request(method, params, timeout_seconds=timeout_seconds)

    transport.request = _spying_request  # type: ignore[method-assign]
    provider = CodexAppServerProvider(prompt_version="v1", transport=transport)
    provider.grade(_VALID_REQUEST)

    assert captured["developerInstructions"] == GRADING_SYSTEM_INSTRUCTIONS
    assert "UNTRUSTED STUDENT OCR" in captured["input_text"]  # type: ignore[operator]


class _StubProcess:
    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid
        self.stdin = None
        self.terminate_called = False
        self.wait_called = False

    def terminate(self) -> None:
        self.terminate_called = True

    def wait(self, timeout: float | None = None) -> None:
        self.wait_called = True


def test_close_kills_the_whole_process_tree_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_resolve_command` can route a `.cmd`/`.bat` npm shim through
    `cmd.exe /c <shim>`, making `self._process` the cmd.exe wrapper rather
    than the real app-server process; `terminate()`/`kill()` alone would
    only end that wrapper and orphan its descendants (code review
    finding)."""
    monkeypatch.setattr(sys, "platform", "win32")
    taskkill_calls: list[list[str]] = []

    def _fake_run(args: list[str], **kwargs: object) -> None:
        taskkill_calls.append(args)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    transport = _SubprocessAppServerTransport.__new__(_SubprocessAppServerTransport)
    transport._process = _StubProcess(pid=4242)  # type: ignore[assignment]
    transport.close()

    assert taskkill_calls == [["taskkill", "/T", "/F", "/PID", "4242"]]
    assert transport._process.terminate_called  # type: ignore[attr-defined]


def test_close_does_not_taskkill_on_non_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    run_calls: list[object] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: run_calls.append(a))

    transport = _SubprocessAppServerTransport.__new__(_SubprocessAppServerTransport)
    transport._process = _StubProcess()  # type: ignore[assignment]
    transport.close()

    assert run_calls == []


def test_cleanup_workspace_succeeds_after_a_transient_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The common Windows failure mode (an antivirus scanner or another
    process briefly holding the file open) must not be treated as
    permanent on the first attempt (code review finding)."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "answer.png").write_bytes(b"data")

    attempts = {"count": 0}
    real_rmtree = shutil.rmtree

    def _flaky_rmtree(path: str, *args: object, **kwargs: object) -> None:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise OSError("simulated transient lock")
        real_rmtree(path)

    monkeypatch.setattr(shutil, "rmtree", _flaky_rmtree)
    _cleanup_workspace(str(workspace), retry_delays=(0.0,), sleep=lambda _: None)

    assert attempts["count"] == 2
    assert not workspace.exists()


def test_cleanup_workspace_warns_when_every_attempt_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cleanup failure must not pass silently: the student's cropped
    answer image would otherwise stay on disk indefinitely while `grade()`
    still reports success (code review finding; decision record's
    no-local-retention requirement)."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def _always_fails(path: str, *args: object, **kwargs: object) -> None:
        raise OSError("simulated persistent lock")

    monkeypatch.setattr(shutil, "rmtree", _always_fails)
    with pytest.warns(ResourceWarning, match="failed to remove"):
        _cleanup_workspace(str(workspace), retry_delays=(0.0, 0.0), sleep=lambda _: None)
