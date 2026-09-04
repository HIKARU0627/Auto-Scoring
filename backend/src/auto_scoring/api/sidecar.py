"""Runnable entry point for the local sidecar.

Binds FastAPI to the loopback interface on a dynamic port, mints a per-session
bearer token, and hands the ``{host, port, token}`` tuple to its parent process
over an explicit handshake file.

Design decisions live in ``docs/technology-stack.md`` §1.1-§1.2 and
``docs/sidecar-api.md``:

* The listen address is hard-wired to ``127.0.0.1`` so the API is never exposed
  on a LAN interface.
* If the requested port is taken the sidecar falls back to any free port, so a
  second instance (or an unrelated process holding the port) does not block
  startup.
* The token is written only to the handshake channel. A logging filter redacts
  it from anything that reaches the application log.
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

import uvicorn

from auto_scoring.api.app import create_app
from auto_scoring.api.auth import generate_token

LOOPBACK = "127.0.0.1"
"""The only interface the sidecar ever binds. Keeps the API off the LAN."""


class Handshake(TypedDict):
    """The single JSON line the parent process reads to reach the sidecar."""

    host: str
    port: int
    token: str


def _find_free_port(host: str = LOOPBACK) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        return int(probe.getsockname()[1])


def resolve_port(requested: int, host: str = LOOPBACK) -> int:
    """Return a bindable port on ``host``.

    ``0`` means "any free port". A non-zero port that cannot be bound (already
    in use) falls back to a free port rather than failing startup.
    """
    if requested == 0:
        return _find_free_port(host)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, requested))
        except OSError:
            return _find_free_port(host)
    return requested


class _RedactingFilter(logging.Filter):
    """Replaces the bearer token with ``***`` in every log record."""

    def __init__(self, secret: str) -> None:
        super().__init__()
        self._secret = secret

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if self._secret in message:
            record.msg = message.replace(self._secret, "***")
            record.args = ()
        return True


def install_log_redaction(token: str) -> None:
    """Route logging through a single handler that scrubs ``token``."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    handler.addFilter(_RedactingFilter(token))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


def _emit_handshake(handshake: Handshake, destination: Path) -> None:
    line = json.dumps(handshake) + "\n"
    destination.write_text(line, encoding="utf-8")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="auto-scoring-sidecar")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Requested port; 0 (default) or an unavailable port picks a free one.",
    )
    parser.add_argument(
        "--handshake-file",
        type=Path,
        required=True,
        help="File to write the {host, port, token} JSON line to.",
    )
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    """Start the sidecar. Returns the process exit code."""
    args = _parse_args(argv)
    token = generate_token()
    port = resolve_port(args.port)

    install_log_redaction(token)
    _emit_handshake(
        Handshake(host=LOOPBACK, port=port, token=token),
        args.handshake_file,
    )

    uvicorn.run(
        create_app(api_token=token),
        host=LOOPBACK,
        port=port,
        log_config=None,
        access_log=True,
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
