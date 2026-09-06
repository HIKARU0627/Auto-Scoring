"""``AIProvider`` adapter over Codex CLI's app-server JSON-RPC protocol (Issue #44).

``codex app-server`` (see ``docs/poc-2-ai-grading.md`` section 7.1 "Codex
app-server 経路") speaks newline-delimited JSON-RPC 2.0 over stdio: one
``initialize`` request, then ``thread/start`` to create a conversation, then
``turn/start`` to submit one turn (text + image input, plus an ``outputSchema``
that constrains the model's final message to our JSON shape). The result
arrives asynchronously as a ``turn/completed`` notification carrying the
turn's ``items`` (including an ``agentMessage`` item with the final text),
not as the ``turn/start`` response itself.

This module was written against the protocol surface ``codex app-server
generate-json-schema`` emits for the locally installed CLI (Codex CLI
0.153.2). The protocol is marked ``[experimental]`` by Codex CLI itself and
has no independent public specification beyond that generated schema and
``codex app-server --help`` -- see ``docs/poc-2-ai-grading.md`` section 7.1
for the recorded research notes and open questions (protocol/version
stability across Codex CLI releases has not been verified).

Never logs the request (answer image / OCR text / rubric text) or the raw
response text (AGENTS.md "Security"): exceptions here carry only method
names, status enums, and JSON-RPC error codes.
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import warnings
from collections.abc import Callable
from typing import Protocol

from pydantic import ValidationError

from auto_scoring.adapters.ai_grading._prompt import (
    GRADING_SYSTEM_INSTRUCTIONS,
    build_grading_user_content,
    sniff_image_format,
)
from auto_scoring.adapters.ai_grading._schema import strict_ai_grading_result_schema
from auto_scoring.domain.ai_grading import parse_ai_grading_result
from auto_scoring.domain.ai_provider import (
    GradingRequest,
    GradingResponse,
    ProviderDescriptor,
    ProviderUnavailable,
    SchemaViolation,
    grading_response_from_result,
)

_DEFAULT_TURN_TIMEOUT_SECONDS = 120.0

#: Codex app-server's `thread/start`/`turn/start` params (per the JSON Schema
#: this module was written against -- ``ThreadStartParams``/`TurnStartParams`)
#: expose no sampling-temperature knob, unlike the direct-API/OpenRouter
#: paths. Recording a caller-supplied value here would misrepresent it as an
#: applied configuration when Codex never received or honoured it
#: (docs/poc-2-ai-grading.md section 7.1 "共通"; code review finding).
#: ``ProviderDescriptor.temperature`` is nonetheless a required
#: field shared by every ``AIProvider`` (needed so ``descriptor_key`` -- the
#: cross-provider reproducibility bucket key, section 3.3 -- has a value at
#: all), so this fixed constant fills it without exposing a temperature
#: parameter that would silently do nothing.
_UNCONFIGURABLE_TEMPERATURE = 0.0

#: Names (matched case-insensitively) forwarded from this process's own
#: environment into the `codex app-server` child. `Popen(..., env=None)`
#: (the default) inherits the ENTIRE parent environment -- including this
#: sidecar's DB connection string and other providers' API keys (AGENTS.md
#: "Security"). Codex's `sandbox: "read-only"` still permits running
#: read-only shell commands, and a turn's prompt/rubric/OCR text is
#: student-controlled: a prompt-injected turn could otherwise run something
#: like `env`/`printenv` and echo an inherited secret back through its own
#: agent message (code review finding). Only variables Codex itself needs
#: to locate its config/auth and run as a normal OS process are forwarded.
_ALLOWED_ENV_VAR_NAMES = frozenset(
    {
        "PATH",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "TEMP",
        "TMP",
        "TMPDIR",
        "SYSTEMROOT",
        "PATHEXT",
        "CODEX_HOME",
    }
)


def _minimal_environment() -> dict[str, str]:
    return {
        name: value for name, value in os.environ.items() if name.upper() in _ALLOWED_ENV_VAR_NAMES
    }


class _AppServerTransport(Protocol):
    """JSON-RPC transport the provider drives. Swapped for a fake in tests
    (``AIProviderContract`` must never spawn a real ``codex`` process or
    require a live Codex login -- Issue #44 "オフラインのfake/recorded
    providerによる単体テスト")."""

    def request(
        self, method: str, params: dict[str, object], *, timeout_seconds: float
    ) -> dict[str, object]: ...

    def wait_for_notification(
        self,
        method: str,
        matches: Callable[[dict[str, object]], bool],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]: ...

    def discard_thread(self, thread_id: str) -> None: ...

    def close(self) -> None: ...


def _message_belongs_to_thread(message: dict[str, object], thread_id: str) -> bool:
    params = message.get("params")
    return isinstance(params, dict) and params.get("threadId") == thread_id


def _resolve_command(executable: str) -> list[str]:
    resolved = shutil.which(executable)
    if resolved is None:
        raise ProviderUnavailable(f"codex executable not found on PATH: {executable!r}")
    # Windows' CreateProcess cannot exec a `.cmd`/`.bat` shim directly; route
    # it through `cmd.exe` instead of falling back to `shell=True` (which
    # would otherwise leave a shell process this adapter cannot cleanly
    # terminate alongside the real `codex` child -- see the leaked-process
    # cleanup this module's own development probe needed).
    if os.name == "nt" and resolved.lower().endswith((".cmd", ".bat")):
        return ["cmd.exe", "/c", resolved]
    return [resolved]


class _SubprocessAppServerTransport:
    """Speaks newline-delimited JSON-RPC 2.0 to a ``codex app-server`` child
    process over stdio (the default transport per ``codex app-server
    --help``)."""

    def __init__(self, *, executable: str = "codex") -> None:
        command = [*_resolve_command(executable), "app-server"]
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
                env=_minimal_environment(),
            )
        except OSError as exc:
            raise ProviderUnavailable(f"failed to start codex app-server: {exc}") from exc

        self._next_id_value = 0
        self._notification_buffer: list[dict[str, object]] = []
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    def _read_loop(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _next_id(self) -> int:
        self._next_id_value += 1
        return self._next_id_value

    def _write(self, message: dict[str, object]) -> None:
        assert self._process.stdin is not None
        try:
            self._process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise ProviderUnavailable("codex app-server is not accepting input") from exc

    def _read_message(self, deadline: float) -> dict[str, object]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        try:
            raw = self._lines.get(timeout=remaining)
        except queue.Empty:
            raise TimeoutError from None
        if raw is None:
            raise ProviderUnavailable("codex app-server process exited unexpectedly")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderUnavailable("codex app-server sent a non-JSON line") from exc
        if not isinstance(parsed, dict):
            raise ProviderUnavailable("codex app-server sent a non-object JSON-RPC message")
        return parsed

    def request(
        self, method: str, params: dict[str, object], *, timeout_seconds: float
    ) -> dict[str, object]:
        request_id = self._next_id()
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout_seconds
        while True:
            message = self._read_message(deadline)
            if message.get("id") == request_id and ("result" in message or "error" in message):
                error = message.get("error")
                if error is not None:
                    code = error.get("code") if isinstance(error, dict) else None
                    raise ProviderUnavailable(f"codex app-server rejected {method} (code {code})")
                result = message.get("result")
                return result if isinstance(result, dict) else {}
            if "method" in message:
                self._notification_buffer.append(message)
            # Any other shape (a stale/unmatched response) is ignored.

    def wait_for_notification(
        self,
        method: str,
        matches: Callable[[dict[str, object]], bool],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        for index, buffered in enumerate(self._notification_buffer):
            params = buffered.get("params")
            params_dict = params if isinstance(params, dict) else {}
            if buffered.get("method") == method and matches(params_dict):
                del self._notification_buffer[index]
                return params_dict

        deadline = time.monotonic() + timeout_seconds
        while True:
            message = self._read_message(deadline)
            if message.get("method") == method:
                params = message.get("params")
                params_dict = params if isinstance(params, dict) else {}
                if matches(params_dict):
                    return params_dict
                continue
            if "method" in message:
                self._notification_buffer.append(message)
            # Responses with no pending request (e.g. a stray late reply) are ignored.

    def discard_thread(self, thread_id: str) -> None:
        """Drop buffered notifications belonging to an already-finished
        thread. Codex app-server emits many per-turn notifications besides
        the single one (``turn/completed``) this adapter waits for (item
        started/completed, reasoning deltas, ...); since the subprocess is
        reused across ``grade()`` calls but each call's ephemeral thread is
        never revisited, anything still buffered under that thread's id
        after its turn completes is permanently irrelevant and would
        otherwise accumulate for the lifetime of the process, making every
        later call scan a growing backlog (code review finding)."""
        self._notification_buffer = [
            message
            for message in self._notification_buffer
            if not _message_belongs_to_thread(message, thread_id)
        ]

    def close(self) -> None:
        with contextlib.suppress(OSError):
            if self._process.stdin is not None:
                self._process.stdin.close()
        if sys.platform == "win32":
            # `_resolve_command` routes a `.cmd`/`.bat` npm shim through
            # `cmd.exe /c <shim>`, so `self._process` is that cmd.exe
            # wrapper, not the real `codex app-server` process running
            # underneath it. `terminate()`/`kill()` below only signal the
            # direct child (cmd.exe), orphaning its descendants -- which
            # then keep running as a leaked worker instead of exiting (code
            # review finding; this is exactly what this module's own
            # development probe needed manual `taskkill /T` to clean up).
            # `taskkill /T` ends the whole process tree regardless of how
            # many process hops the shim itself introduces.
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(self._process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                )
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()


def _extract_thread_id(thread_start_result: dict[str, object]) -> str:
    thread = thread_start_result.get("thread")
    thread_id = thread.get("id") if isinstance(thread, dict) else None
    if not isinstance(thread_id, str) or not thread_id:
        raise ProviderUnavailable("codex app-server thread/start response had no thread id")
    return thread_id


def _extract_configured_model(thread_start_result: dict[str, object]) -> str:
    """The model this turn will actually run against.

    When the caller omits ``AUTO_SCORING_CODEX_MODEL``, ``thread/start``'s
    ``model`` request field is ``null`` and Codex substitutes its own
    configured default -- but ``ThreadStartResponse.model`` (a required
    response field) always reports which model was actually selected. Using
    a placeholder like ``"default"`` for the *response* descriptor instead
    would let two calls that silently ran against different actual Codex
    defaults (e.g. after a Codex CLI upgrade changes its default model) pool
    into the same reproducibility bucket (``descriptor_key``,
    docs/poc-2-ai-grading.md section 3.3; code review finding).
    """
    model = thread_start_result.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ProviderUnavailable("codex app-server thread/start response had no model")
    return model


def _extract_final_agent_message(turn_completed_params: dict[str, object]) -> str:
    turn = turn_completed_params.get("turn")
    if not isinstance(turn, dict):
        raise ProviderUnavailable("codex app-server turn/completed had no turn payload")
    if turn.get("status") != "completed":
        raise ProviderUnavailable(f"codex app-server turn ended with status {turn.get('status')!r}")
    items = turn.get("items")
    if not isinstance(items, list):
        raise SchemaViolation("codex app-server turn had no items")
    for item in reversed(items):
        if isinstance(item, dict) and item.get("type") == "agentMessage":
            text = item.get("text")
            if isinstance(text, str):
                return text
    raise SchemaViolation("codex app-server turn produced no agent message")


def _cleanup_workspace(
    workspace_dir: str,
    *,
    retry_delays: tuple[float, ...] = (0.1, 0.3, 0.9),
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Removes the private per-call workspace directory -- and the
    student's cropped answer image inside it -- retrying briefly first.

    A transient Windows failure (an antivirus scanner or another process
    momentarily holding the file open, a permissions hiccup) is the common
    case this guards against. Silently discarding a *persistent* failure
    (``shutil.rmtree(..., ignore_errors=True)``) would let an
    otherwise-successful ``grade()`` call return normally while leaving the
    student's answer image on disk indefinitely, violating the no-local-
    retention requirement for this cloud-payload material (code review
    finding). A cleanup failure must not fail an otherwise-successful
    grading call either, so a still-failing cleanup is surfaced as a
    warning (not an exception) instead of passing silently.
    """
    for delay in (0.0, *retry_delays):
        if delay:
            sleep(delay)
        try:
            shutil.rmtree(workspace_dir)
            return
        except FileNotFoundError:
            return
        except OSError:
            continue
    warnings.warn(
        f"codex app-server: failed to remove temporary workspace directory "
        f"after {len(retry_delays) + 1} attempts: {workspace_dir}",
        ResourceWarning,
        stacklevel=2,
    )


class CodexAppServerProvider:
    """Grades one question per ``turn/start`` on a fresh, ephemeral thread.

    A fresh thread per call (never reused across ``grade()`` calls) is
    deliberate: reusing one thread would carry prior questions' answer text
    forward as conversation history, violating the per-question minimal
    payload boundary every other adapter honours (decision record section 2
    (2), ``docs/poc-2-ai-grading.md`` section 2.1). The underlying
    subprocess *is* reused across calls to avoid a process spawn (and a
    fresh Codex login handshake) per question.
    """

    name = "codex-app-server"

    def __init__(
        self,
        *,
        model: str | None = None,
        prompt_version: str,
        executable: str = "codex",
        turn_timeout_seconds: float = _DEFAULT_TURN_TIMEOUT_SECONDS,
        transport: _AppServerTransport | None = None,
    ) -> None:
        self._model = model
        self._prompt_version = prompt_version
        self._executable = executable
        self._turn_timeout_seconds = turn_timeout_seconds
        self._transport = transport
        self._initialized = False
        #: Populated from the first successful `thread/start`/`initialize`
        #: response and reused by both `describe()` and every later
        #: response descriptor, so a failed call recorded via `describe()`
        #: and a later successful call are never split into different
        #: reproducibility buckets by an inconsistent placeholder value
        #: (code review finding).
        self._resolved_model: str | None = None
        self._codex_user_agent: str | None = None

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider=self.name,
            model=self._resolved_model or self._model or "default",
            version=self._codex_user_agent,
            prompt_version=self._prompt_version,
            temperature=_UNCONFIGURABLE_TEMPERATURE,
            structured_output_mode="json_schema",
        )

    def _ensure_transport(self) -> _AppServerTransport:
        if self._transport is None:
            self._transport = _SubprocessAppServerTransport(executable=self._executable)
        if not self._initialized:
            try:
                initialize_result = self._transport.request(
                    "initialize",
                    {"clientInfo": {"name": "auto-scoring-backend", "version": "0.1.0"}},
                    timeout_seconds=self._turn_timeout_seconds,
                )
            except TimeoutError as exc:
                raise ProviderUnavailable(
                    "codex app-server did not respond to initialize in time"
                ) from exc
            # `userAgent` is the CLI's own version string (confirmed via a
            # real `initialize` call -- docs/poc-2-ai-grading.md section
            # 7.1.2). Recording it means an upgraded, differently-behaving
            # Codex CLI no longer pools with older runs under the same
            # `version=None` (code review finding).
            user_agent = initialize_result.get("userAgent")
            if isinstance(user_agent, str) and user_agent.strip():
                self._codex_user_agent = user_agent
            self._initialized = True
        return self._transport

    def _reset_transport(self) -> None:
        """Drop a possibly-dead transport so the next call starts a fresh
        `codex app-server` process instead of retrying against the same
        broken pipe / already-exited process forever (code review
        finding)."""
        if self._transport is not None:
            with contextlib.suppress(Exception):
                self._transport.close()
        self._transport = None
        self._initialized = False

    def grade(self, request: GradingRequest) -> GradingResponse:
        try:
            return self._grade(request)
        except ProviderUnavailable:
            self._reset_transport()
            raise

    def _grade(self, request: GradingRequest) -> GradingResponse:
        transport = self._ensure_transport()
        started_at = time.monotonic()

        workspace_dir, image_path = self._write_temp_workspace(request.answer_image)
        thread_id: str | None = None
        try:
            try:
                thread_result = transport.request(
                    "thread/start",
                    {
                        # A private, per-call directory -- never the shared
                        # global temp root -- so a prompt-injected turn's
                        # still-permitted file reads (see class docstring)
                        # are confined to this call's own answer image, not
                        # every other process's or submission's temp files
                        # (code review finding; decision record section 2
                        # (2) per-question minimal payload boundary).
                        "cwd": workspace_dir,
                        # Grading needs no filesystem/command access; read-only +
                        # never-approve keeps a misbehaving turn from blocking on
                        # (or acting on) anything beyond the model call itself.
                        "sandbox": "read-only",
                        "approvalPolicy": "never",
                        "model": self._model,
                        "ephemeral": True,
                        # Fixed grading rules go through this trusted
                        # instruction channel, never mixed into the same
                        # message as the student-controlled OCR text/answer
                        # image the turn's `input` carries (code review
                        # finding; see _prompt.py's module docstring).
                        "developerInstructions": GRADING_SYSTEM_INSTRUCTIONS,
                        # Defense in depth alongside the already-minimal
                        # child-process environment (_minimal_environment):
                        # tell Codex's own shell tool not to forward any of
                        # it into commands it runs (mirrors the
                        # `shell_environment_policy.inherit` config key
                        # `codex --help` documents; not exercised against a
                        # live app-server call -- recorded as an open
                        # question in docs/poc-2-ai-grading.md section
                        # 7.1.2).
                        "config": {"shell_environment_policy": {"inherit": "none"}},
                    },
                    timeout_seconds=self._turn_timeout_seconds,
                )
                resolved_model = _extract_configured_model(thread_result)
                self._resolved_model = resolved_model
                thread_id = _extract_thread_id(thread_result)

                transport.request(
                    "turn/start",
                    {
                        "threadId": thread_id,
                        "input": [
                            {"type": "text", "text": build_grading_user_content(request)},
                            {"type": "localImage", "path": image_path},
                        ],
                        "outputSchema": strict_ai_grading_result_schema(),
                        # Belt-and-braces on top of the thread-level
                        # `sandbox: "read-only"`: an explicit per-turn
                        # policy object that also disables network access,
                        # so a prompt-injected shell command cannot exfiltrate
                        # anything it does manage to read (code review
                        # finding).
                        "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
                    },
                    timeout_seconds=self._turn_timeout_seconds,
                )

                completed_params = transport.wait_for_notification(
                    "turn/completed",
                    lambda params: params.get("threadId") == thread_id,
                    timeout_seconds=self._turn_timeout_seconds,
                )
            except TimeoutError as exc:
                # Covers every stage above (initialize already handled in
                # _ensure_transport): a hung thread/start or turn/start must
                # not leak the builtin TimeoutError past this port's
                # documented ProviderUnavailable/SchemaViolation contract
                # (code review finding).
                raise ProviderUnavailable("codex app-server did not respond in time") from exc
        finally:
            _cleanup_workspace(workspace_dir)
            if thread_id is not None:
                transport.discard_thread(thread_id)

        latency_seconds = time.monotonic() - started_at
        text = _extract_final_agent_message(completed_params)

        try:
            parsed_result = parse_ai_grading_result(text)
        except ValidationError:
            # `from None`: see the matching comment in openrouter_provider.py
            # -- do not chain the raw ValidationError (AGENTS.md "Security").
            raise SchemaViolation(
                "codex app-server response failed AIGradingResult schema validation"
            ) from None

        descriptor = ProviderDescriptor(
            provider=self.name,
            model=resolved_model,
            version=self._codex_user_agent,
            prompt_version=self._prompt_version,
            temperature=_UNCONFIGURABLE_TEMPERATURE,
            structured_output_mode="json_schema",
        )
        return grading_response_from_result(
            parsed_result, descriptor=descriptor, latency_seconds=latency_seconds
        )

    def _write_temp_workspace(self, data: bytes) -> tuple[str, str]:
        workspace_dir = tempfile.mkdtemp(prefix="auto-scoring-codex-turn-")
        image_path = os.path.join(workspace_dir, f"answer.{sniff_image_format(data)}")
        try:
            with open(image_path, "wb") as handle:
                handle.write(data)
        except BaseException:
            _cleanup_workspace(workspace_dir)
            raise
        return workspace_dir, image_path

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
