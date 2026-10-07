from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_healthz() -> None:
    r = TestClient(create_app(Settings())).get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_unknown_route_uses_error_shape() -> None:
    r = TestClient(create_app(Settings())).get("/v1/nothing")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
