"""Smoke and auth tests for the FastAPI sidecar."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
