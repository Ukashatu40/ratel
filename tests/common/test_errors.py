from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from common.errors import ApiError, install_error_handlers
from tests.synthetic import SENTINEL_KI


class Body(BaseModel):
    imsi: str
    speed: int


def _app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise ApiError(409, "conflict", "already exists")

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError(f"secret in message {SENTINEL_KI}")

    @app.post("/body")
    async def body(b: Body) -> dict[str, str]:
        return {"ok": "yes"}

    return app


def test_api_error_uses_contract_shape() -> None:
    r = TestClient(_app()).get("/boom")
    assert r.status_code == 409
    assert r.json() == {"error": {"code": "conflict", "message": "already exists"}}


def test_not_found_uses_contract_shape() -> None:
    r = TestClient(_app()).get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_validation_error_does_not_echo_input() -> None:
    r = TestClient(_app()).post("/body", json={"imsi": 1, "speed": SENTINEL_KI})
    assert r.status_code == 422
    body = r.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "validation_error"
    assert SENTINEL_KI not in r.text


def test_unhandled_error_is_generic() -> None:
    r = TestClient(_app(), raise_server_exceptions=False).get("/crash")
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "internal_error", "message": "Internal error"}}
    assert SENTINEL_KI not in r.text
