from fastapi.testclient import TestClient
from src.app import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_overview_rejects_dates_outside_case_study_without_network_call():
    response = client.get("/api/overview?decision_date_from=2025-12-31")
    assert response.status_code == 400


def test_overview_rejects_reversed_date_range():
    response = client.get("/api/overview?decision_date_from=2026-01-20&decision_date_to=2026-01-01")
    assert response.status_code == 400


def test_overview_rejects_invalid_cutoff():
    response = client.get("/api/overview?cutoff_time=25:00")
    assert response.status_code == 400
