"""API-key authentication through the real app: middleware, error handlers, logging.

Test-only routes are added to the real app after it is built, behind the same dependency the
production /v1 router uses. The real /v1 router has no routes yet (W2-01..03).
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from common.errors import ApiError
from common.logging import JsonFormatter
from ratel_link.api.dependencies import require_api_key
from ratel_link.api.router import new_v1_router
from ratel_link.config import Settings
from ratel_link.domain.api_keys import ApiKeyGeneration, ApiKeyRecord
from ratel_link.main import create_app
from ratel_link.security.api_key_tokens import hash_secret
from ratel_link.services.api_key_admin import KeyPolicy, create_system, disable, revoke, rotate
from ratel_link.services.authentication import ApiPrincipal
from tests.ratel_link.fakes import FakeClock, InMemoryApiKeyRepository
from tests.synthetic import (
    SENTINEL_API_KEY,
    SENTINEL_API_KEY_ID,
    SENTINEL_API_SECRET,
)

EXPECTED_BODY = {"error": {"code": "unauthorized", "message": "Invalid or missing API key."}}
test_logger = logging.getLogger("ratel.test.handler")


class Thing(BaseModel):
    name: str
    size: int


def _test_router() -> APIRouter:
    router = new_v1_router()  # the production router, so these routes get its protection

    @router.get("/whoami")
    def whoami(principal: ApiPrincipal = Depends(require_api_key)) -> dict[str, Any]:  # noqa: B008
        test_logger.info("inside.handler")
        return {"api_key_id": principal.api_key_id, "generation": principal.generation}

    @router.post("/things")
    def create_thing(thing: Thing) -> dict[str, str]:
        return {"name": thing.name}

    @router.get("/things/{thing_id}")
    def get_thing(thing_id: int) -> None:
        raise ApiError(404, "not_found", "No such thing.")

    return router


class Env:
    def __init__(self) -> None:
        self.repo = InMemoryApiKeyRepository()
        self.clock = FakeClock()
        self.app: FastAPI = create_app(Settings(), api_keys=self.repo, clock=self.clock)
        self.app.include_router(_test_router())
        self.client = TestClient(self.app)
        self.logs = io.StringIO()
        handler = logging.StreamHandler(self.logs)  # added AFTER create_app, which resets handlers
        handler.setFormatter(JsonFormatter())
        logging.getLogger().addHandler(handler)
        self._handler = handler
        self.token = create_system(self.repo, "bss-app", "RatelBSS", self.clock(), KeyPolicy())

    def close(self) -> None:
        logging.getLogger().removeHandler(self._handler)

    def get(self, path: str, token: str | None = None, **kw: Any) -> Any:
        headers = {} if token is None else {"Authorization": f"Bearer {token}"}
        return self.client.get(path, headers=headers, **kw)

    def log_lines(self) -> list[dict[str, Any]]:
        return [
            json.loads(line) for line in self.logs.getvalue().splitlines() if line.startswith("{")
        ]


@pytest.fixture
def env() -> Iterator[Env]:
    e = Env()
    yield e
    e.close()


def _assert_generic_401(r: Any) -> None:
    assert r.status_code == 401
    assert r.json() == EXPECTED_BODY
    assert r.headers["www-authenticate"] == "Bearer"
    assert r.headers["content-type"] == "application/json"


# --- the 401 ------------------------------------------------------------------------------------


def test_missing_header_is_401(env: Env) -> None:
    _assert_generic_401(env.get("/v1/whoami"))


def _bad_credentials(env: Env) -> dict[str, dict[str, str]]:
    secret = env.token.split(".", 1)[1]
    other = "rlk_bss-app." + "A" * 43
    return {
        "wrong_scheme": {"Authorization": f"Basic {secret}"},
        "raw_key_without_scheme": {"Authorization": env.token},
        "empty_token": {"Authorization": "Bearer "},
        "malformed_token": {"Authorization": "Bearer nonsense"},
        "unknown_id": {"Authorization": f"Bearer rlk_nobody-here.{secret}"},
        "wrong_secret": {"Authorization": f"Bearer {other}"},
    }


def test_every_failure_gives_the_same_response(env: Env) -> None:
    responses = [env.client.get("/v1/whoami", headers=h) for h in _bad_credentials(env).values()]
    for r in responses:
        _assert_generic_401(r)
    assert len({r.content for r in responses}) == 1  # byte-identical bodies


def test_revoked_expired_and_disabled_give_the_same_response(env: Env) -> None:
    good = env.token
    new = rotate(env.repo, "bss-app", env.clock(), KeyPolicy())
    revoke(env.repo, "bss-app", 1, env.clock())
    revoked = env.get("/v1/whoami", good)
    env.clock.advance(days=91)
    expired = env.get("/v1/whoami", new)
    other = create_system(env.repo, "meter-agent", "Meter", env.clock(), KeyPolicy())
    disable(env.repo, "meter-agent")
    disabled = env.get("/v1/whoami", other)
    for r in (revoked, expired, disabled):
        _assert_generic_401(r)
    assert revoked.content == expired.content == disabled.content


def test_body_matches_the_contract_error_schema(env: Env) -> None:
    body = env.get("/v1/whoami").json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message"}


# --- the 200 ------------------------------------------------------------------------------------


def test_valid_key_reaches_the_handler_with_the_principal(env: Env) -> None:
    r = env.get("/v1/whoami", env.token)
    assert r.status_code == 200
    assert r.json() == {"api_key_id": "bss-app", "generation": 1}


def test_lowercase_bearer_is_accepted(env: Env) -> None:
    r = env.client.get("/v1/whoami", headers={"Authorization": f"bearer {env.token}"})
    assert r.status_code == 200


def test_both_keys_work_during_a_rotation_overlap(env: Env) -> None:
    new = rotate(env.repo, "bss-app", env.clock(), KeyPolicy())
    assert env.get("/v1/whoami", env.token).json()["generation"] == 1
    assert env.get("/v1/whoami", new).json()["generation"] == 2
    env.clock.advance(days=8)
    _assert_generic_401(env.get("/v1/whoami", env.token))
    assert env.get("/v1/whoami", new).status_code == 200


def test_healthz_needs_no_key(env: Env) -> None:
    r = env.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


# --- authentication comes before everything else ------------------------------------------------


def test_invalid_body_without_a_key_is_401_not_422(env: Env) -> None:
    r = env.client.post("/v1/things", json={"name": 5})  # schema-invalid
    _assert_generic_401(r)
    r = env.client.post("/v1/things", json={})
    _assert_generic_401(r)


def test_invalid_body_with_a_key_is_422(env: Env) -> None:
    r = env.client.post(
        "/v1/things", json={"name": 5}, headers={"Authorization": f"Bearer {env.token}"}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_invalid_path_parameter_without_a_key_is_401_not_422(env: Env) -> None:
    _assert_generic_401(env.get("/v1/things/not-a-number"))


def test_unknown_resource_without_a_key_is_401_not_404(env: Env) -> None:
    _assert_generic_401(env.get("/v1/things/42"))
    assert env.get("/v1/things/42", env.token).status_code == 404


def test_malformed_json_without_a_key(env: Env) -> None:
    r = env.client.post(
        "/v1/things", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    _assert_generic_401(r)


# --- logging ------------------------------------------------------------------------------------


def test_rejection_is_logged_with_a_reason_and_never_the_token(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    secret = env.token.split(".", 1)[1]
    cases = {
        "missing_header": {},
        "wrong_scheme": {"Authorization": f"Basic {secret}"},
        "malformed_token": {"Authorization": "Bearer nonsense"},
        "unknown_id": {"Authorization": f"Bearer rlk_nobody-here.{secret}"},
        "bad_secret": {"Authorization": "Bearer rlk_bss-app." + "A" * 43},
    }
    for headers in cases.values():
        env.client.get("/v1/whoami", headers=headers)
    rejections = [r for r in env.log_lines() if r["event"] == "auth.rejected"]
    assert [r["reason"] for r in rejections] == list(cases)
    by_reason = {r["reason"]: r for r in rejections}
    assert "api_key_id" not in by_reason["missing_header"]
    assert "api_key_id" not in by_reason["malformed_token"]  # unparsed: nothing to name
    assert by_reason["unknown_id"]["api_key_id"] == "nobody-here"
    assert by_reason["bad_secret"]["api_key_id"] == "bss-app"
    everything = env.logs.getvalue() + caplog.text
    assert secret not in everything and env.token not in everything
    assert "A" * 43 not in everything


def test_revoked_expired_and_disabled_are_distinguished_in_the_log_only(env: Env) -> None:
    good = env.token
    new = rotate(env.repo, "bss-app", env.clock(), KeyPolicy())
    revoke(env.repo, "bss-app", 1, env.clock())
    env.get("/v1/whoami", good)
    env.clock.advance(days=91)
    env.get("/v1/whoami", new)
    other = create_system(env.repo, "meter-agent", "Meter", env.clock(), KeyPolicy())
    disable(env.repo, "meter-agent")
    env.get("/v1/whoami", other)
    reasons = [r["reason"] for r in env.log_lines() if r["event"] == "auth.rejected"]
    assert reasons == ["revoked", "expired", "disabled"]


def test_authenticated_log_lines_carry_the_key_id_and_generation(env: Env) -> None:
    env.get("/v1/whoami", env.token)
    lines = {r["event"]: r for r in env.log_lines()}
    for event in ("inside.handler", "http.request"):
        assert lines[event]["api_key_id"] == "bss-app", event
        assert lines[event]["api_key_generation"] == 1, event
    assert lines["http.request"]["status"] == 200


def test_the_key_id_does_not_leak_into_the_next_request(env: Env) -> None:
    env.get("/v1/whoami", env.token)
    env.get("/healthz")
    last = [r for r in env.log_lines() if r["event"] == "http.request"][-1]
    assert last["route"] == "/healthz"
    assert "api_key_id" not in last


def test_the_token_never_appears_in_any_log_line(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    secret = env.token.split(".", 1)[1]
    env.get("/v1/whoami", env.token)
    env.get("/v1/things/5", env.token)
    env.client.post(
        "/v1/things", json={"name": 1}, headers={"Authorization": f"Bearer {env.token}"}
    )
    everything = env.logs.getvalue() + caplog.text
    assert env.token not in everything and secret not in everything
    assert "authorization" not in everything.lower().replace("auth.rejected", "")


def test_sentinel_key_is_valid_end_to_end_and_never_logged(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    # tests/conftest.py also fails the whole run if this value reaches the session log.
    caplog.set_level(logging.DEBUG)
    env.repo.documents.pop("bss-app")
    now = env.clock()
    env.repo.insert(
        ApiKeyRecord(
            SENTINEL_API_KEY_ID,
            "RatelBSS",
            "active",
            now,
            (ApiKeyGeneration(1, hash_secret(SENTINEL_API_SECRET), now, now + timedelta(days=90)),),
        )
    )
    assert env.get("/v1/whoami", SENTINEL_API_KEY).status_code == 200
    assert env.get("/v1/whoami", SENTINEL_API_KEY[:-1] + "x").status_code == 401
    everything = env.logs.getvalue() + caplog.text
    assert SENTINEL_API_KEY not in everything and SENTINEL_API_SECRET not in everything


def test_request_logging_never_includes_headers(env: Env) -> None:
    env.client.get(
        "/v1/whoami",
        headers={"Authorization": f"Bearer {env.token}", "X-Custom-Secret": "header-value-xyz"},
    )
    assert "header-value-xyz" not in env.logs.getvalue()
    request_line = next(r for r in env.log_lines() if r["event"] == "http.request")
    assert set(request_line) <= {
        "ts", "level", "logger", "event", "request_id", "api_key_id", "api_key_generation",
        "method", "route", "status", "duration_ms",
    }  # fmt: skip


# --- unmatched and wrong-method requests --------------------------------------------------------


def test_a_path_with_no_route_is_404_because_there_is_nothing_to_protect(env: Env) -> None:
    r = env.get("/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_the_whole_response_stays_free_of_the_key(env: Env) -> None:
    r = env.get("/v1/whoami", env.token)
    assert env.token not in r.text and env.token not in str(r.headers)


def test_one_request_costs_one_key_lookup(env: Env) -> None:
    lookups: list[str] = []
    real_get = env.repo.get

    def counting_get(api_key_id: str) -> ApiKeyRecord | None:
        lookups.append(api_key_id)
        return real_get(api_key_id)

    env.repo.get = counting_get  # type: ignore[method-assign]
    assert env.get("/v1/whoami", env.token).status_code == 200  # pre-check plus dependency
    assert lookups == ["bss-app"]


def test_the_router_dependency_protects_on_its_own() -> None:
    # Defence in depth: a router built without the auth-first route class is still protected.
    repo = InMemoryApiKeyRepository()
    app = create_app(Settings(), api_keys=repo, clock=FakeClock())
    plain = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])

    @plain.get("/plain")
    def plain_route() -> dict[str, str]:
        return {"ok": "yes"}

    app.include_router(plain)
    _assert_generic_401(TestClient(app).get("/v1/plain"))


def test_an_authenticated_request_does_not_authenticate_the_next_one(env: Env) -> None:
    # The cached principal lives and dies with one request.
    assert env.get("/v1/whoami", env.token).status_code == 200
    _assert_generic_401(env.get("/v1/whoami"))
    assert env.get("/v1/whoami", env.token).status_code == 200
    _assert_generic_401(env.get("/v1/whoami"))
