"""Smoke tests for the FastAPI sidecar."""

from fastapi.testclient import TestClient

from auto_scoring.api.app import create_app

client = TestClient(create_app())


def test_health_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_score_clamps_and_reports_ratio() -> None:
    response = client.post("/score", json={"key": "q1", "raw": 15, "maximum": 10})
    assert response.status_code == 200
    body = response.json()
    assert body == {"key": "q1", "awarded": 10, "maximum": 10, "ratio": 1.0}
