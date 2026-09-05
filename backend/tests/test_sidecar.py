"""Tests for sidecar bootstrap: port fallback, handshake, log redaction."""

import json
import logging
import socket
from pathlib import Path
from typing import Any

import pytest
import uvicorn

from auto_scoring.api import sidecar
from auto_scoring.api.sidecar import (
    LOOPBACK,
    Handshake,
    install_log_redaction,
    run,
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
    monkeypatch.setattr(sidecar, "install_log_redaction", lambda _token: None)

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
