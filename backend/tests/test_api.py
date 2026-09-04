"""Smoke and auth tests for the FastAPI sidecar."""

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
