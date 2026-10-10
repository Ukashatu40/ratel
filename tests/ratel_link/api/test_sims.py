"""POST /v1/sims through the real app, with in-memory storage."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from common.logging import JsonFormatter
from ratel_link.config import Settings
from ratel_link.domain.audit import AuditEntry
from ratel_link.main import create_app
from ratel_link.security.key_provider import KeyProvider, NoKeyProvider
from tests.ratel_link.fakes import (
    FakeClock,
    InMemoryApiKeyRepository,
    InMemoryAuditLogRepository,
    InMemorySimKeyRepository,
    StaticKeyProvider,
)
from tests.ratel_link.helpers import register_system
from tests.synthetic import SYNTHETIC_IMSI, SYNTHETIC_IMSI_2, SYNTHETIC_KI_HEX, SYNTHETIC_OPC_HEX

OTHER_HEX = "0f0e0d0c0b0a09080706050403020100"
USE_REGISTERED = "use-the-registered-key"  # sentinel meaning: send the env's own valid key
UNAUTHORIZED = {"error": {"code": "unauthorized", "message": "Invalid or missing API key."}}


def body(**changes: Any) -> dict[str, Any]:
    payload = {"imsi": SYNTHETIC_IMSI, "ki": SYNTHETIC_KI_HEX, "opc": SYNTHETIC_OPC_HEX}
    payload.update(changes)
    return payload


class Env:
    def __init__(
        self,
        key_provider: KeyProvider | None = None,
        audit: InMemoryAuditLogRepository | None = None,
    ) -> None:
        self.api_keys = InMemoryApiKeyRepository()
        self.sims = InMemorySimKeyRepository()
        self.audit = audit or InMemoryAuditLogRepository()
        self.clock = FakeClock()
        self.app = create_app(
            Settings(),
            api_keys=self.api_keys,
            sim_keys=self.sims,
            audit=self.audit,
            key_provider=key_provider or StaticKeyProvider(),
            clock=self.clock,
        )
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.token = register_system(self.api_keys, self.clock)
        self.logs = io.StringIO()
        handler = logging.StreamHandler(self.logs)  # after create_app, which resets handlers
        handler.setFormatter(JsonFormatter())
        logging.getLogger().addHandler(handler)
        self._handler = handler

    def close(self) -> None:
        logging.getLogger().removeHandler(self._handler)

    def post(self, payload: Any = None, *, token: str | None = USE_REGISTERED, **kw: Any) -> Any:
        headers = dict(kw.pop("headers", {}))
        key = self.token if token is USE_REGISTERED else token
        if key is not None:
            headers["Authorization"] = f"Bearer {key}"
        return self.client.post(
            "/v1/sims", json=payload if payload is not None else body(), headers=headers, **kw
        )


@pytest.fixture
def env() -> Iterator[Env]:
    e = Env()
    yield e
    e.close()


def test_a_valid_import_is_200_with_an_empty_object(env: Env) -> None:
    r = env.post()
    assert r.status_code == 200
    assert r.json() == {}
    assert list(env.sims.documents) == [SYNTHETIC_IMSI]


def test_what_is_stored_is_encrypted(env: Env) -> None:
    env.post()
    raw = json.dumps(env.sims.documents, default=str)
    assert SYNTHETIC_KI_HEX not in raw and SYNTHETIC_OPC_HEX not in raw
    assert set(env.sims.documents[SYNTHETIC_IMSI]["ki"]) == {"v", "alg", "kid", "nonce", "ct"}


def test_one_audit_entry_names_the_calling_system_and_holds_no_key(env: Env) -> None:
    env.post()
    (entry,) = env.audit.entries
    assert (entry["action"], entry["imsi"], entry["api_key_id"]) == (
        "sim.import",
        SYNTHETIC_IMSI,
        "bss-app",
    )
    assert entry["after"] == {"status": "provisioned"}
    text = json.dumps(env.audit.entries, default=str)
    assert SYNTHETIC_KI_HEX not in text and SYNTHETIC_OPC_HEX not in text and env.token not in text


def test_the_same_keys_again_are_200_and_change_nothing(env: Env) -> None:
    env.post()
    stored = json.dumps(env.sims.documents, default=str)
    r = env.post(body(ki=SYNTHETIC_KI_HEX.upper(), opc=SYNTHETIC_OPC_HEX.upper()))
    assert r.status_code == 200 and r.json() == {}
    assert json.dumps(env.sims.documents, default=str) == stored
    assert len(env.audit.entries) == 1


@pytest.mark.parametrize(
    "changes", [{"ki": OTHER_HEX}, {"opc": OTHER_HEX}, {"ki": OTHER_HEX, "opc": OTHER_HEX}]
)
def test_different_keys_for_a_known_imsi_are_409_and_never_replace_the_stored_ones(
    env: Env, changes: dict[str, str]
) -> None:
    env.post()
    stored = json.dumps(env.sims.documents, default=str)
    r = env.post(body(**changes))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"
    assert OTHER_HEX not in r.text and SYNTHETIC_KI_HEX not in r.text
    assert json.dumps(env.sims.documents, default=str) == stored
    assert len(env.audit.entries) == 1


def test_two_different_sims_are_both_stored(env: Env) -> None:
    assert env.post(body()).status_code == 200
    assert env.post(body(imsi=SYNTHETIC_IMSI_2, ki=OTHER_HEX, opc=OTHER_HEX)).status_code == 200
    assert len(env.sims.documents) == 2 and len(env.audit.entries) == 2


def test_the_idempotency_key_header_is_accepted(env: Env) -> None:
    headers = {"Idempotency-Key": "abc-123"}
    assert env.post(headers=headers).status_code == 200
    assert env.post(headers=headers).status_code == 200
    assert len(env.audit.entries) == 1


def test_an_empty_idempotency_key_is_refused_as_the_contract_says(env: Env) -> None:
    # The contract gives the header minLength 1. Found by Schemathesis, kept as a regression test.
    r = env.post(headers={"Idempotency-Key": ""})
    assert r.status_code == 422
    assert env.sims.documents == {} and env.audit.entries == []


# --- authentication comes first -----------------------------------------------------------------


@pytest.mark.parametrize("token", [None, "rlk_bss-app." + "A" * 43, "garbage"])
def test_without_a_valid_key_it_is_401_and_nothing_is_stored(env: Env, token: str | None) -> None:
    r = env.post(token=token)
    assert r.status_code == 401 and r.json() == UNAUTHORIZED
    assert env.sims.documents == {} and env.audit.entries == []


def test_a_malformed_body_without_a_key_is_401_not_422(env: Env) -> None:
    r = env.client.post(
        "/v1/sims", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 401 and r.json() == UNAUTHORIZED


def test_a_malformed_body_with_a_key_is_422(env: Env) -> None:
    r = env.client.post(
        "/v1/sims",
        content=b"{not json",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {env.token}"},
    )
    assert r.status_code == 422


# --- validation ---------------------------------------------------------------------------------

BAD_BODIES = {
    "short_imsi": body(imsi="62100000000000"),
    "long_imsi": body(imsi="6210000000000012"),
    "imsi_not_digits": body(imsi="62100000000000a"),
    "short_ki": body(ki=SYNTHETIC_KI_HEX[:-1]),
    "ki_not_hex": body(ki="z" * 32),
    "opc_not_hex": body(opc="z" * 32),
    "ki_with_newline": body(ki=SYNTHETIC_KI_HEX + "\n"),
    "ki_a_number": body(ki=12345),
    "missing_opc": {"imsi": SYNTHETIC_IMSI, "ki": SYNTHETIC_KI_HEX},
    "extra_field": body(amf="8000"),
    "empty_object": {"x": 1},
}


@pytest.mark.parametrize("name", sorted(BAD_BODIES))
def test_a_bad_body_is_422_and_nothing_is_stored_or_echoed(env: Env, name: str) -> None:
    r = env.post(BAD_BODIES[name])
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert "z" * 32 not in r.text and SYNTHETIC_KI_HEX not in r.text
    assert env.sims.documents == {} and env.audit.entries == []


def test_get_is_not_allowed(env: Env) -> None:
    r = env.client.get("/v1/sims", headers={"Authorization": f"Bearer {env.token}"})
    assert r.status_code == 405 and "POST" in r.headers["allow"]


# --- secrets stay out of everything -------------------------------------------------------------


def test_no_key_and_no_imsi_reaches_any_log_line(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    env.post()
    env.post()
    env.post(body(ki=OTHER_HEX))
    env.post(body(ki="z" * 32))
    everything = env.logs.getvalue() + caplog.text
    for secret in (SYNTHETIC_KI_HEX, SYNTHETIC_OPC_HEX, OTHER_HEX, SYNTHETIC_IMSI, env.token):
        assert secret not in everything, "a secret or an IMSI was logged"
    events = [
        json.loads(ln)["event"] for ln in env.logs.getvalue().splitlines() if ln.startswith("{")
    ]
    assert "sim.import.created" in events and "sim.import.unchanged" in events
    assert "sim.import.conflict" in events


def test_the_request_log_line_carries_the_caller_and_the_route_template(env: Env) -> None:
    env.post()
    lines = [json.loads(ln) for ln in env.logs.getvalue().splitlines() if ln.startswith("{")]
    request = next(line for line in lines if line["event"] == "http.request")
    assert request["route"] == "/v1/sims" and request["status"] == 200
    assert request["api_key_id"] == "bss-app"


# --- failure modes ------------------------------------------------------------------------------


def test_without_an_encryption_key_it_is_503_and_nothing_is_stored() -> None:
    e = Env(key_provider=NoKeyProvider())
    try:
        r = e.post()
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "unavailable"
        assert SYNTHETIC_KI_HEX not in r.text
        assert e.sims.documents == {} and e.audit.entries == []
    finally:
        e.close()


def test_a_failing_audit_write_is_a_generic_500() -> None:
    class BrokenAudit(InMemoryAuditLogRepository):
        def insert(self, entry: AuditEntry) -> None:
            raise ConnectionError(f"mongodb://user:hunter2@host {SYNTHETIC_KI_HEX}")

    e = Env(audit=BrokenAudit())
    try:
        r = e.post()
        assert r.status_code == 500
        assert r.json() == {"error": {"code": "internal_error", "message": "Internal error"}}
        assert "hunter2" not in r.text and SYNTHETIC_KI_HEX not in r.text
    finally:
        e.close()
