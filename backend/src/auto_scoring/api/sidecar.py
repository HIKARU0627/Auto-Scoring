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


def _bind_socket(requested: int, host: str = LOOPBACK) -> socket.socket:
    """Bind and return an open socket on a bindable port -- held open (not
    yet listening) until the caller hands it straight to uvicorn.

    ``0`` means "any free port". A non-zero ``requested`` port that cannot be
    bound (already in use) falls back to any free port rather than failing
    startup.

    This used to be a plain ``resolve_port() -> int``: bind a throwaway probe
    socket, read the port number the OS assigned it, close the probe, and
    hand back just the number for the *caller* to bind again later. That left
    a real gap between "a free port was found" and "the real server is
    listening on it" -- during which the OS was free to hand that exact
    number to something else. Observed in practice on Windows: the longer
    ``create_app()`` (schema migrations) took to run in that gap, the more
    often asyncio's own event loop -- started moments later, inside this same
    process, to actually serve the app -- ended up binding its own internal
    sockets to the just-freed port first, silently shifting the real server
    onto the *next* port instead, while the handshake file had already been
    written with the original one. A client trusting the handshake would
    then reach nothing at all. Returning the still-open, already-bound
    socket instead of a bare number closes that gap entirely: nothing else
    can ever claim this exact port between here and ``run()`` handing the
    same socket object to uvicorn.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, requested))
    except OSError:
        sock.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((host, 0))
    return sock


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
    parser.add_argument(
        "--app-data-dir",
        type=Path,
        default=Path.cwd() / "app-data",
        help=(
            "app-data/ root (simplified-design-spec.md §23): database, source "
            "PDFs, generated images. Persists across restarts -- the final "
            "production location is provisional pending the Windows "
            "distribution issue (docs/answer-intake-and-preprocessing.md §5)."
        ),
    )
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    """Start the sidecar. Returns the process exit code."""
    args = _parse_args(argv)
    token = generate_token()

    # Bound (and held open) before anything else in this function -- see
    # _bind_socket's docstring for why: create_app() below runs schema
    # migrations and can take a while, and the socket must stay reserved for
    # the whole of that, not just for the instant this line runs.
    sock = _bind_socket(args.port)
    port = int(sock.getsockname()[1])

    install_log_redaction(token)
    _emit_handshake(
        Handshake(host=LOOPBACK, port=port, token=token),
        args.handshake_file,
    )

    # data_root only, no session_factory: create_app() builds the database
    # itself (migrations, engine, the startup repair sweep) rather than this
    # function duplicating that -- see create_app()'s docstring for why
    # session_factory is reserved for callers (Issue #26's tests) that need
    # to hand in an already-migrated database instead.
    config = uvicorn.Config(
        create_app(api_token=token, data_root=args.app_data_dir),
        host=LOOPBACK,
        port=port,
        log_config=None,
        access_log=True,
    )
    # sockets=[sock], not host=/port= alone: uvicorn would otherwise bind a
    # *new* socket to config.port itself, reopening exactly the gap
    # _bind_socket exists to close.
    uvicorn.Server(config).run(sockets=[sock])
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
