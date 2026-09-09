"""Tests for sidecar bootstrap: port fallback, handshake, log redaction."""

import json
import logging
import logging.handlers
import os
import socket
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn

from auto_scoring.adapters.ai.unconfigured_provider import UnconfiguredAIProvider
from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.ai_grading.vertex_gemini_provider import VertexGeminiAIProvider
from auto_scoring.adapters.data_root_lock import acquire_data_root_lock
from auto_scoring.api import sidecar
from auto_scoring.api.secret_redaction import configuration_secrets
from auto_scoring.api.sidecar import (
    ALREADY_RUNNING_EXIT_CODE,
    LOOPBACK,
    Handshake,
    default_app_data_dir,
    install_log_redaction,
    run,
)
from auto_scoring.db.engine import sqlite_url
from auto_scoring.db.migrator import upgrade
from auto_scoring.domain.ai_provider import ProviderUnavailable

from .test_ai_provider_contract import _VALID_REQUEST
from .test_ai_provider_vertex_gemini_contract import _FakeCredentials


@pytest.fixture(autouse=True)
def _pinned_ai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """`run()` resolves the AI-grading provider from this host's own
    environment (Issue #97). Pin the answer for every test in this file, so
    none of them probes the machine for a `codex` binary or a `gcloud`
    login -- the difference between a developer box and a CI runner that
    docs/quality-gates.md records as "ホストを見る判定はテストへ注入する".

    The one test that cares which provider arrives installs its own
    (`test_run_starts_and_serves_on_a_host_with_no_ai_credentials`).
    """
    # `**_` absorbs the injection keywords `run()` passes (since Issue #105
    # it hands both builders a shared ADC token source). A double that
    # spelled them out would have to be edited every time the composition
    # root wires something new, for a value it does not look at.
    monkeypatch.setattr(
        sidecar,
        "build_ai_provider",
        lambda _env, **_: UnconfiguredAIProvider("pinned by the test suite"),
    )


def test_bind_socket_zero_returns_an_open_socket_on_a_free_loopback_port() -> None:
    sock = sidecar._bind_socket(0)
    try:
        port = sock.getsockname()[1]
        assert port != 0
        # Still held by us: nothing else can have grabbed it in the meantime,
        # which is the entire point (see _bind_socket's docstring).
        with (
            pytest.raises(OSError),
            socket.socket(socket.AF_INET, socket.SOCK_STREAM) as other,
        ):
            other.bind((LOOPBACK, port))
    finally:
        sock.close()


def test_bind_socket_keeps_a_free_requested_port() -> None:
    probe = sidecar._bind_socket(0)
    free = probe.getsockname()[1]
    probe.close()

    sock = sidecar._bind_socket(free)
    try:
        assert sock.getsockname()[1] == free
    finally:
        sock.close()


def test_bind_socket_falls_back_when_requested_port_is_taken() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind((LOOPBACK, 0))
        held.listen()
        taken = held.getsockname()[1]

        sock = sidecar._bind_socket(taken)
        try:
            fallback = sock.getsockname()[1]
            assert fallback != taken
        finally:
            sock.close()


def test_install_log_redaction_scrubs_the_token(capsys: pytest.CaptureFixture[str]) -> None:
    root = logging.getLogger()
    saved = root.handlers[:]
    try:
        install_log_redaction("s3cr3t-token")
        logging.getLogger("uvicorn.access").warning("client sent token s3cr3t-token in header")
    finally:
        root.handlers = saved

    err = capsys.readouterr().err
    assert "s3cr3t-token" not in err
    assert "***" in err


def test_install_log_redaction_also_writes_a_rotating_file_log(tmp_path: Path) -> None:
    """The installed app has nowhere for stderr to go (the Flutter supervisor
    drains it), so the file log is the only durable record of §28's AI/OCR/PDF
    outcomes -- and it has to be scrubbed just like stderr."""
    root = logging.getLogger()
    saved = root.handlers[:]
    log_directory = tmp_path / "logs"
    try:
        install_log_redaction("s3cr3t-token", log_directory)
        # An `auto_scoring.*` logger, not one of uvicorn's: these are the
        # loggers §28's records actually come from, and they reach the
        # handlers only by propagating to root.
        logging.getLogger("auto_scoring.jobs.queue").warning("token s3cr3t-token leaked")
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = saved

    written = (log_directory / sidecar.LOG_FILENAME).read_text(encoding="utf-8")
    assert "s3cr3t-token" not in written
    assert "***" in written


def test_install_log_redaction_without_a_directory_stays_on_stderr_only(
    tmp_path: Path,
) -> None:
    root = logging.getLogger()
    saved = root.handlers[:]
    try:
        install_log_redaction("token")
        assert all(
            not isinstance(handler, logging.handlers.RotatingFileHandler)
            for handler in root.handlers
        )
    finally:
        root.handlers = saved


def test_startup_migrations_do_not_dismantle_the_log_configuration(
    tmp_path: Path,
) -> None:
    """Running migrations must leave `install_log_redaction`'s handlers -- and
    the app's own loggers -- exactly as they were.

    The regression this exists for (Issue #24): `migrations/env.py` called
    `fileConfig(alembic.ini)` unconditionally, including on the programmatic
    path the sidecar takes at startup. That replaced the root handlers with
    alembic.ini's console handler -- dropping the rotating file log *and the
    token-redaction filter* -- and, via `disable_existing_loggers`'s default,
    silenced every `auto_scoring.*` logger for the rest of the process. The
    sidecar kept running and simply stopped recording anything.
    """
    root = logging.getLogger()
    saved = root.handlers[:]
    log_directory = tmp_path / "logs"
    application_logger = logging.getLogger("auto_scoring.jobs.queue")
    try:
        install_log_redaction("s3cr3t-token", log_directory)
        upgrade(sqlite_url(tmp_path / "database.sqlite"), "head")

        assert not application_logger.disabled
        application_logger.info("token s3cr3t-token in a job record")
        for handler in root.handlers:
            handler.flush()
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = saved

    written = (log_directory / sidecar.LOG_FILENAME).read_text(encoding="utf-8")
    assert "in a job record" in written, "app logging stopped working after migrations"
    assert "s3cr3t-token" not in written, "redaction filter was lost during migrations"


def test_a_provider_request_url_never_reaches_the_file_log(tmp_path: Path) -> None:
    """Review rounds 2 and 3, the leak this app's logging policy exists for.

    The Vertex adapter builds ``AUTO_SCORING_VERTEX_LOCATION`` (and project,
    and model) into the request URL, and httpx logs that URL at INFO into a
    file log that outlives the session -- so a key pasted into any of those
    variables was written to disk by a code path that never touches one of
    this project's own log calls. A 4xx is enough to see it.

    The location here contains **uppercase characters on purpose**: round 2
    was fixed by masking the value out of the line, and round 3 showed that
    httpx lowercases the host, so the masked-for string no longer matched
    what was printed. This test therefore looks for both spellings, and the
    fix it holds in place is not a better mask -- it is that httpx does not
    log at INFO here at all (`sidecar._VERBOSE_LOGGERS`).

    End to end (real adapter, real httpx client over `MockTransport`, real
    handlers, assertions on the bytes on disk) because what these rounds
    showed is that reasoning about which strings reach the log is exactly
    what goes wrong.
    """
    location = "sk-Secret-Accidentally-Pasted"
    environment = {
        "AUTO_SCORING_VERTEX_LOCATION": location,
        "AUTO_SCORING_VERTEX_PROJECT": "sk-also-pasted-into-project",
        "AUTO_SCORING_GEMINI_MODEL": "gemini-2.5-flash",
    }
    log_directory = tmp_path / "logs"
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    try:
        install_log_redaction(
            "session-token",
            log_directory,
            secrets=configuration_secrets(environment),
        )
        provider = VertexGeminiAIProvider(
            model=environment["AUTO_SCORING_GEMINI_MODEL"],
            prompt_version="v1",
            location=location,
            tokens=AdcTokenSource(
                credentials=_FakeCredentials(),
                project_id=environment["AUTO_SCORING_VERTEX_PROJECT"],
            ),
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(404, json={"error": "no such model"})
                )
            ),
        )
        with pytest.raises(ProviderUnavailable):
            provider.grade(_VALID_REQUEST)
        # Proves the log is not simply dead: this app's own records still
        # reach the file at INFO, so the absences below mean "httpx was
        # refused", not "nothing is being written at all".
        logging.getLogger("auto_scoring.jobs.queue").info("job finished")
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = saved_handlers
        root.setLevel(saved_level)

    written = (log_directory / sidecar.LOG_FILENAME).read_text(encoding="utf-8")
    assert "job finished" in written
    assert "HTTP Request" not in written
    assert "aiplatform.googleapis.com" not in written
    assert location not in written
    assert location.lower() not in written
    assert environment["AUTO_SCORING_VERTEX_PROJECT"] not in written


def test_a_library_may_not_log_at_info_but_this_app_may(tmp_path: Path) -> None:
    """The policy itself, stated once without any adapter in the way: INFO is
    allowed for this app, uvicorn and alembic, and refused for everything
    else (`sidecar._VERBOSE_LOGGERS`).

    Deny by default is what makes it hold for the *next* library too -- the
    one nobody has added yet, whose INFO line nobody has read.
    """
    log_directory = tmp_path / "logs"
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    try:
        install_log_redaction("session-token", log_directory)
        logging.getLogger("httpx").info("HTTP Request: POST https://host/secret-path")
        logging.getLogger("some.future.dependency").info("chatty startup banner")
        logging.getLogger("auto_scoring.jobs.queue").info("job finished")
        logging.getLogger("uvicorn.access").info("127.0.0.1 - GET /healthz 200")
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = saved_handlers
        root.setLevel(saved_level)

    written = (log_directory / sidecar.LOG_FILENAME).read_text(encoding="utf-8")
    assert "secret-path" not in written
    assert "chatty startup banner" not in written
    assert "job finished" in written
    assert "GET /healthz" in written


def test_emit_handshake_writes_one_json_line(tmp_path: Path) -> None:
    target = tmp_path / "handshake.json"
    sidecar._emit_handshake(Handshake(host=LOOPBACK, port=51234, token="abc"), target)

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {"host": LOOPBACK, "port": 51234, "token": "abc"}


def test_run_binds_loopback_and_hands_off_matching_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sidecar, "generate_token", lambda: "generated-test-token")
    monkeypatch.setattr(sidecar, "install_log_redaction", lambda *_args, **_kwargs: None)

    captured: dict[str, Any] = {}

    def fake_server_run(self: uvicorn.Server, sockets: list[socket.socket] | None = None) -> None:
        captured["config"] = self.config
        captured["sockets"] = sockets

    monkeypatch.setattr(uvicorn.Server, "run", fake_server_run)

    handshake_file = tmp_path / "handshake.json"
    exit_code = run(
        [
            "--handshake-file",
            str(handshake_file),
            "--app-data-dir",
            str(tmp_path / "app-data"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(handshake_file.read_text(encoding="utf-8"))
    assert payload["host"] == LOOPBACK
    assert payload["token"] == "generated-test-token"

    config = captured["config"]
    assert config.host == LOOPBACK
    assert config.port == payload["port"]
    assert config.app.state.api_token == "generated-test-token"
    # The DB was created and migrated to head under --app-data-dir (Issue #26).
    assert (tmp_path / "app-data" / "database.sqlite").is_file()

    # The exact socket handed to Server.run() is bound to the same port the
    # handshake already promised, and it is *still open* here -- proving
    # run() never let go of it (and so never let anything else claim that
    # port) between binding it and handing it to uvicorn. This is the
    # regression this test exists for: the previous resolve_port()-returns-
    # a-bare-int design closed its probe socket in that gap, and on Windows
    # asyncio's own event loop could (and did) claim the just-freed port for
    # itself before uvicorn's real listen socket got there.
    sockets = captured["sockets"]
    assert sockets is not None
    assert len(sockets) == 1
    assert sockets[0].getsockname()[1] == payload["port"]
    assert sockets[0].fileno() != -1
    sockets[0].close()


def test_run_starts_and_serves_on_a_host_with_no_ai_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #97's acceptance criterion for an unconfigured machine: the app
    still starts. Answer intake, review and PDF export do not need a grading
    provider, and refusing to start without one would take all three away to
    punish a missing API key.

    Also pins *where* that decision is taken: `run()` reads this process's
    environment and hands the result to `create_app`, rather than
    `create_app` reaching for `os.environ` itself -- which would make every
    test that builds an app inherit whatever the machine it runs on happens
    to have configured.
    """
    monkeypatch.setattr(sidecar, "generate_token", lambda: "generated-test-token")
    monkeypatch.setattr(sidecar, "install_log_redaction", lambda *_args, **_kwargs: None)

    seen: dict[str, Mapping[str, str]] = {}
    provider = UnconfiguredAIProvider("no transport configured on this host")

    def fake_build(env: Mapping[str, str], **_: Any) -> UnconfiguredAIProvider:
        seen["env"] = env
        return provider

    monkeypatch.setattr(sidecar, "build_ai_provider", fake_build)

    captured: dict[str, Any] = {}

    def fake_server_run(self: uvicorn.Server, sockets: list[socket.socket] | None = None) -> None:
        captured["config"] = self.config
        if sockets is not None:
            for sock in sockets:
                sock.close()

    monkeypatch.setattr(uvicorn.Server, "run", fake_server_run)

    handshake_file = tmp_path / "handshake.json"
    exit_code = run(
        [
            "--handshake-file",
            str(handshake_file),
            "--app-data-dir",
            str(tmp_path / "app-data"),
        ]
    )

    assert exit_code == 0
    assert handshake_file.is_file()
    assert seen["env"] is os.environ
    assert captured["config"].app.state.ai_provider is provider


def test_self_test_imports_native_backed_modules_without_a_handshake_file() -> None:
    """`--self-test` is the packaging build's proof that the frozen bundle is
    complete (docs/windows-distribution.md §7), so it has to work with none of
    a real run's arguments and without touching app-data."""
    assert run(["--self-test"]) == 0


def test_self_test_covers_every_lazily_imported_native_dependency() -> None:
    """Guards the list itself, not the import: the modules named there are the
    only ones that load OpenCV, pdfium and reportlab, and they are reached
    lazily (first answer PDF), long after `/healthz` starts answering. Dropping
    one silently narrows what the packaging smoke test can catch."""
    assert set(sidecar._NATIVE_BACKED_MODULES) == {
        "auto_scoring.adapters.image.opencv_preprocessor",
        "auto_scoring.adapters.pdf.pdfium_pypdf_engine",
    }


def test_run_without_handshake_file_is_rejected() -> None:
    with pytest.raises(SystemExit) as exit_info:
        run([])
    assert exit_info.value.code == 2  # argparse's usage-error exit code


def test_run_reports_a_data_root_another_process_owns_and_writes_no_handshake(
    tmp_path: Path,
) -> None:
    """A second instance against a live instance's app-data root must fail
    with its own exit code -- and must not leave a handshake file behind, or
    the supervisor that spawned it would read a host:port nothing ever serves
    (Issue #24: 二重起動でport/processが残らない)."""
    data_root = tmp_path / "app-data"
    handshake_file = tmp_path / "handshake.json"

    held = acquire_data_root_lock(data_root)
    try:
        exit_code = run(
            [
                "--handshake-file",
                str(handshake_file),
                "--app-data-dir",
                str(data_root),
            ]
        )
    finally:
        held.close()

    assert exit_code == ALREADY_RUNNING_EXIT_CODE
    assert not handshake_file.exists()


def test_run_records_an_unexpected_startup_failure_and_writes_no_handshake(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every *other* startup failure (a failed migration, a corrupt database):

    * the traceback lands in `sidecar.log`, with the token scrubbed,
    * the exit code is distinct from "already running",
    * and no handshake file is left behind -- it is the promise "this port is
      served", so it is only ever written once that promise can be kept.

    The regression (Issue #24 review round 2): only `DataRootLockedError` was
    caught, so anything else propagated out of `run` and Python's default
    excepthook printed it to stderr *without going through logging*. It never
    reached the rotating file log, and the Flutter supervisor drains the
    sidecar's stderr -- so the error screen told the user to read a log that
    did not contain the reason.
    """
    monkeypatch.setattr(sidecar, "generate_token", lambda: "s3cr3t-token")

    def _boom(**_kwargs: object) -> object:
        raise RuntimeError("database is corrupt: s3cr3t-token")

    monkeypatch.setattr(sidecar, "create_app", _boom)
    handshake_file = tmp_path / "handshake.json"
    data_root = tmp_path / "app-data"

    root = logging.getLogger()
    saved = root.handlers[:]
    try:
        exit_code = run(
            [
                "--handshake-file",
                str(handshake_file),
                "--app-data-dir",
                str(data_root),
            ]
        )
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = saved

    assert exit_code == sidecar.STARTUP_FAILED_EXIT_CODE
    assert exit_code != ALREADY_RUNNING_EXIT_CODE
    assert not handshake_file.exists()

    written = (data_root / sidecar.LOG_DIRECTORY_NAME / sidecar.LOG_FILENAME).read_text(
        encoding="utf-8"
    )
    assert "Traceback (most recent call last)" in written
    assert "RuntimeError: database is corrupt" in written
    # The exception's own message carried the token; the filter has to reach
    # into the traceback, not just the formatted message.
    assert "s3cr3t-token" not in written
    assert "***" in written


def test_install_log_redaction_falls_back_to_stderr_when_the_file_log_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An app-data directory that cannot be written must not stop the sidecar
    starting -- and must not raise from *here*.

    `install_log_redaction` runs before `run`'s own exception handler is in
    place, so an error escaping it would surface as exactly the unlogged
    traceback that handler exists to prevent (Issue #24 review round 2).
    """

    def _deny(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("read-only volume")

    monkeypatch.setattr(Path, "mkdir", _deny)

    root = logging.getLogger()
    saved = root.handlers[:]
    try:
        install_log_redaction("token", tmp_path / "logs")  # must not raise
        assert all(
            not isinstance(handler, logging.handlers.RotatingFileHandler)
            for handler in root.handlers
        )
    finally:
        root.handlers = saved

    assert "logging to stderr only" in capsys.readouterr().err


def test_install_log_redaction_scrubs_the_token_from_a_traceback(
    tmp_path: Path,
) -> None:
    """`logger.exception` writes text that never passes through
    `record.getMessage()`, so the filter has to scrub the traceback too."""
    root = logging.getLogger()
    saved = root.handlers[:]
    log_directory = tmp_path / "logs"
    try:
        install_log_redaction("s3cr3t-token", log_directory)
        try:
            raise RuntimeError("upstream said s3cr3t-token")
        except RuntimeError:
            logging.getLogger("auto_scoring.jobs.queue").exception("job failed")
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = saved

    written = (log_directory / sidecar.LOG_FILENAME).read_text(encoding="utf-8")
    assert "Traceback (most recent call last)" in written
    assert "s3cr3t-token" not in written
    assert "***" in written


class TestDefaultAppDataDir:
    """The final production app-data location (Issue #24). Resolved from an
    explicit environment/platform pair so every OS's layout is verifiable from
    any host -- these run on a Linux CI runner too."""

    def test_windows_uses_localappdata(self) -> None:
        resolved = default_app_data_dir(
            {"LOCALAPPDATA": r"C:\Users\teacher\AppData\Local"}, platform="win32"
        )
        assert resolved == Path(r"C:\Users\teacher\AppData\Local") / "Auto-Scoring" / "app-data"

    def test_windows_falls_back_to_the_home_directory_layout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: Path("/home/t")))
        assert default_app_data_dir({}, platform="win32") == Path(
            "/home/t/AppData/Local/Auto-Scoring/app-data"
        )

    def test_macos_uses_application_support(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: Path("/Users/t")))
        assert default_app_data_dir({}, platform="darwin") == Path(
            "/Users/t/Library/Application Support/Auto-Scoring/app-data"
        )

    def test_posix_honours_xdg_data_home(self) -> None:
        assert default_app_data_dir({"XDG_DATA_HOME": "/tmp/xdg"}, platform="linux") == Path(
            "/tmp/xdg/auto-scoring/app-data"
        )

    def test_posix_falls_back_to_local_share(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: Path("/home/t")))
        assert default_app_data_dir({}, platform="linux") == Path(
            "/home/t/.local/share/auto-scoring/app-data"
        )

    def test_the_default_is_never_relative_to_the_working_directory(self) -> None:
        """The regression this location replaces: a `cwd()`-relative default
        made an installed app find a different database depending on how it
        was launched."""
        assert default_app_data_dir().is_absolute()


def test_adc_is_resolved_once_and_shared_by_every_consumer() -> None:
    """Grading and answer-area detection want the *same* Vertex credentials.

    Resolving ADC costs ~300ms on a host with a `gcloud` login, and Issue #105
    added the second consumer -- so without sharing, sidecar startup paid that
    twice for nothing. The sidecar's handshake is timing-sensitive, which is
    how the regression showed up.
    """
    calls: list[str | None] = []

    def build(project_id: str | None) -> AdcTokenSource:
        calls.append(project_id)
        return AdcTokenSource(credentials=_FakeCredentials(), project_id=project_id or "p")

    factory = sidecar.shared_adc_token_source(build)
    first = factory(None)
    second = factory(None)

    assert first is second
    assert calls == [None]


def test_a_different_vertex_project_gets_its_own_credentials() -> None:
    """Keyed by project id, not shared blindly: two callers pointed at
    different projects must not be handed each other's credentials.
    """
    built: list[str | None] = []

    def build(project_id: str | None) -> AdcTokenSource:
        built.append(project_id)
        return AdcTokenSource(credentials=_FakeCredentials(), project_id=project_id or "p")

    factory = sidecar.shared_adc_token_source(build)
    assert factory("project-a") is not factory("project-b")
    assert built == ["project-a", "project-b"]


def test_a_missing_login_is_raised_afresh_for_every_caller() -> None:
    """Failures are not cached: each factory has to classify a missing login
    itself, exactly as it would with a token source of its own.
    """
    attempts = 0

    def build(project_id: str | None) -> AdcTokenSource:
        nonlocal attempts
        attempts += 1
        raise AdcCredentialsError("no application default credentials on this host")

    factory = sidecar.shared_adc_token_source(build)
    for _ in range(2):
        with pytest.raises(AdcCredentialsError):
            factory(None)
    assert attempts == 2
