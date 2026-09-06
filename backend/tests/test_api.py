"""Smoke and auth tests for the FastAPI sidecar."""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

import pytest
from fastapi.testclient import TestClient

from auto_scoring.adapters.data_root_lock import DataRootLockedError
from auto_scoring.api.app import create_app

_TOKEN = "test-token-value"
client = TestClient(create_app(api_token=_TOKEN))
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


def test_healthz_ok_without_auth() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_score_clamps_and_reports_ratio() -> None:
    response = client.post(
        "/score",
        json={"key": "q1", "raw": 15, "maximum": 10},
        headers=_AUTH,
    )
    assert response.status_code == 200
    assert response.json() == {"key": "q1", "awarded": 10, "maximum": 10, "ratio": 1.0}


def test_score_rejects_missing_token() -> None:
    response = client.post("/score", json={"key": "q1", "raw": 5, "maximum": 10})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_score_rejects_wrong_token() -> None:
    response = client.post(
        "/score",
        json={"key": "q1", "raw": 5, "maximum": 10},
        headers={"Authorization": "Bearer not-the-token"},
    )
    assert response.status_code == 401


def test_each_app_has_its_own_random_token() -> None:
    assert create_app().state.api_token != create_app().state.api_token


def test_a_second_create_app_on_the_same_data_root_fails_to_start(tmp_path: Path) -> None:
    """Issue #18 review round 9, P1 / round 10, P1: two sidecar processes
    launched against the same --app-data-dir must not both touch it -- a
    second process running migrations/sweep_temp/repair (or, if it got
    that far, start()'s own crash-recovery sweep) against a data_root the
    first, still-alive process actually owns could delete *.part files the
    first process is still writing, mark its in-flight submissions
    erroneous, or let a duplicate provider call happen and the owning
    process's own eventual finalize lose its compare-and-set, silently
    discarding real, completed work.

    The data-root lock is acquired synchronously inside create_app() itself
    (round 10, P1), before migrations/sweep_temp/repair ever run -- not
    merely later, at ASGI lifespan startup (round 9, P1's original
    placement, which left every one of those steps unprotected: by the
    time api/sidecar.py's run() reaches create_app(), it has already bound
    its socket and written its handshake file, well before any lifespan
    exists to fail in). So the second create_app() call itself fails
    outright, without even reaching TestClient/uvicorn.
    """
    first_app = create_app(api_token=_TOKEN, data_root=tmp_path)
    with TestClient(first_app), pytest.raises(DataRootLockedError):
        create_app(api_token=_TOKEN, data_root=tmp_path)


def test_a_second_create_app_fails_before_any_lifespan_ever_runs(tmp_path: Path) -> None:
    """Issue #18 review round 10, P1: before this fix, the data-root lock
    was only acquired inside the ASGI lifespan (review round 9, P1's
    original placement), so it protected nothing until a lifespan actually
    ran. create_app() itself -- migrations, sweep_temp,
    repair_incomplete_submissions -- ran fully unprotected for every
    caller that never drives a lifespan at all, which is exactly what
    api/sidecar.py's run() does: it calls create_app() well before handing
    the result to uvicorn, whose lifespan only starts once the server
    itself starts serving. No TestClient/lifespan is used here at all --
    the second create_app() call must still fail on construction alone.
    """
    first_app = create_app(api_token=_TOKEN, data_root=tmp_path)
    with pytest.raises(DataRootLockedError):
        create_app(api_token=_TOKEN, data_root=tmp_path)
    assert first_app.state.api_token == _TOKEN  # the first app is unaffected


def test_a_failed_create_app_releases_its_data_root_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #18 review round 10, P1: create_app() takes the data-root lock
    before running migrations, so a migration failure (or anything else
    that fails before this function returns) must release it again --
    otherwise a single failed attempt would strand the lock held for the
    rest of the process, and even a caller that fixes whatever failed and
    retries create_app() against the same data_root would wrongly find it
    "in use by another instance".

    The failed call's traceback is deliberately kept referenced (``held_tb``)
    across the retry below: a traceback keeps every frame it passed through
    alive, including the failed create_app() call's own locals -- among
    them the lock handle itself, which would otherwise most likely already
    be closed by plain CPython reference counting once that frame is
    discarded, regardless of whether create_app() ever explicitly closes
    it. Holding the traceback is what makes this test actually exercise
    create_app()'s own explicit release rather than incidentally passing
    on CPython's collection timing either way.
    """

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr("auto_scoring.api.app.upgrade", _boom)
    held_tb: TracebackType | None = None
    try:
        create_app(api_token=_TOKEN, data_root=tmp_path)
    except RuntimeError:
        held_tb = sys.exc_info()[2]
    assert held_tb is not None

    monkeypatch.undo()  # restore the real upgrade() for the retry below
    create_app(api_token=_TOKEN, data_root=tmp_path)  # must not raise DataRootLockedError


def test_default_temp_app_data_dir_cleanup_disposes_the_engine_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create_app() without ``data_root`` registers a temp-dir cleanup at
    process exit. The startup repair query (and every other DB access this
    app makes) leaves a connection sitting in the engine's pool --
    SQLAlchemy does not close a pooled connection until the engine itself is
    disposed. On Windows, that open connection keeps the sqlite file open,
    so cleaning up the directory without disposing the engine first fails
    with ``PermissionError`` and leaks the whole temp directory.
    """
    created_dirs: list[tempfile.TemporaryDirectory[str]] = []
    real_temporary_directory = tempfile.TemporaryDirectory

    def _tracking_temporary_directory(*, prefix: str) -> tempfile.TemporaryDirectory[str]:
        instance = real_temporary_directory(prefix=prefix)
        created_dirs.append(instance)
        return instance

    monkeypatch.setattr(
        "auto_scoring.api.app.tempfile.TemporaryDirectory",
        _tracking_temporary_directory,
    )

    registered: list[Callable[[], None]] = []
    monkeypatch.setattr("auto_scoring.api.app.atexit.register", registered.append)

    create_app(api_token=_TOKEN)

    assert len(created_dirs) == 1
    assert len(registered) == 1
    temp_path = Path(created_dirs[0].name)
    assert temp_path.exists()

    registered[0]()  # simulate process exit; must not raise

    assert not temp_path.exists()
