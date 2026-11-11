from fastapi.testclient import TestClient

from pokerbot.api.app import app, create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_module_level_app_serves_health() -> None:
    # uvicorn targets `pokerbot.api.app:app`
    assert TestClient(app).get("/health").status_code == 200


def test_unknown_route_is_404() -> None:
    assert TestClient(create_app()).get("/nope").status_code == 404
