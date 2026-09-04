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
    TOKEN_ENV_VAR,
    Handshake,
    install_log_redaction,
    resolve_port,
    run,
)


def _is_bindable(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((LOOPBACK, port))
        except OSError:
            return False
    return True


def test_resolve_port_zero_returns_free_loopback_port() -> None:
    port = resolve_port(0)
    assert port != 0
    assert _is_bindable(port)


def test_resolve_port_keeps_a_free_requested_port() -> None:
    free = resolve_port(0)
    assert resolve_port(free) == free


def test_resolve_port_falls_back_when_requested_port_is_taken() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind((LOOPBACK, 0))
        held.listen()
        taken = held.getsockname()[1]

        fallback = resolve_port(taken)

    assert fallback != taken
    assert _is_bindable(fallback)


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
    monkeypatch.setenv(TOKEN_ENV_VAR, "env-provided-token")
    monkeypatch.setattr(sidecar, "install_log_redaction", lambda _token: None)

    captured: dict[str, Any] = {}

    def fake_uvicorn_run(app: Any, **kwargs: Any) -> None:
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr(uvicorn, "run", fake_uvicorn_run)

    handshake_file = tmp_path / "handshake.json"
    exit_code = run(["--handshake-file", str(handshake_file)])

    assert exit_code == 0
    payload = json.loads(handshake_file.read_text(encoding="utf-8"))
    assert payload["host"] == LOOPBACK
    assert payload["token"] == "env-provided-token"
    assert captured["kwargs"]["host"] == LOOPBACK
    assert captured["kwargs"]["port"] == payload["port"]
    assert captured["app"].state.api_token == "env-provided-token"
