import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from ratel_link.config import Settings
from ratel_link.main import create_app


def test_healthz() -> None:
    r = TestClient(create_app(Settings())).get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert r.headers["x-request-id"]


def test_request_id_is_echoed() -> None:
    r = TestClient(create_app(Settings())).get("/healthz", headers={"x-request-id": "abc123"})
    assert r.headers["x-request-id"] == "abc123"


def test_unknown_route_uses_error_shape() -> None:
    r = TestClient(create_app(Settings())).get("/v1/nothing")
    assert r.status_code == 404
    assert set(r.json()) == {"error"}


@pytest.mark.parametrize(
    "uri",
    [
        "mongodb://127.0.0.1:27017",
        "mongodb://localhost:27017/?authSource=admin",
        "mongodb://user:pw@127.0.0.1:27017/?authSource=admin",
    ],
)
def test_localhost_mongo_accepted(uri: str) -> None:
    assert Settings(mongo_uri=SecretStr(uri)).mongo_uri.get_secret_value() == uri


@pytest.mark.parametrize(
    "uri",
    ["mongodb://192.168.1.50:27017", "mongodb://db.example.com", "mongodb://127.0.0.1,10.0.0.9"],
)
def test_remote_mongo_rejected_without_leaking_uri(uri: str) -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(mongo_uri=SecretStr(uri))
    assert uri not in str(exc.value)
