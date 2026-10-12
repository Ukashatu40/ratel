"""GET /v1/lines/{imsi} and GET /v1/assignments through the real app, with in-memory storage."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ratel_link.config import Settings
from ratel_link.domain.ip_pool import IpPool
from ratel_link.domain.line_state import LineState
from ratel_link.main import create_app
from ratel_link.services.ip_allocation import IpAllocator
from tests.ratel_link.fakes import (
    FakeClock,
    InMemoryApiKeyRepository,
    InMemoryIpAllocationRepository,
    InMemoryLineStateRepository,
    InMemorySimKeyRepository,
    StaticKeyProvider,
)
from tests.ratel_link.helpers import all_fakes, register_system
from tests.synthetic import SYNTHETIC_IMSI, SYNTHETIC_IMSI_2, SYNTHETIC_KI_HEX, SYNTHETIC_OPC_HEX

REGISTERED = object()  # sentinel: send the environment's own valid key
UNAUTHORIZED = {"error": {"code": "unauthorized", "message": "Invalid or missing API key."}}
LINE_FIELDS = {"status", "msisdn", "apns", "ue_ip", "speed_ul_mbps", "speed_dl_mbps"}


class Env:
    def __init__(self) -> None:
        self.api_keys = InMemoryApiKeyRepository()
        self.sims = InMemorySimKeyRepository()
        self.lines = InMemoryLineStateRepository()
        self.ips = InMemoryIpAllocationRepository()
        self.clock = FakeClock()
        self.allocator = IpAllocator(self.ips, IpPool.from_cidr("10.45.0.0/16"), self.clock)
        self.app = create_app(
            Settings(),
            **{
                **all_fakes(),
                "api_keys": self.api_keys,
                "sim_keys": self.sims,
                "line_states": self.lines,
                "ip_allocations": self.ips,
            },
            key_provider=StaticKeyProvider(),
            clock=self.clock,
        )
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.token = register_system(self.api_keys, self.clock)

    def get(self, path: str, *, token: str | object | None = REGISTERED, **kw: Any) -> Any:
        headers = dict(kw.pop("headers", {}))
        key = self.token if token is REGISTERED else token
        if key is not None:
            headers["Authorization"] = f"Bearer {key}"
        return self.client.get(path, headers=headers, **kw)

    def import_sim(self, imsi: str = SYNTHETIC_IMSI) -> None:
        r = self.client.post(
            "/v1/sims",
            json={"imsi": imsi, "ki": SYNTHETIC_KI_HEX, "opc": SYNTHETIC_OPC_HEX},
            headers={"Authorization": f"Bearer {self.token}"},
        )
        assert r.status_code == 200


@pytest.fixture
def env() -> Env:
    return Env()


# --- GET /v1/lines/{imsi} ---


def test_a_line_that_was_never_imported_is_404(env: Env) -> None:
    r = env.get(f"/v1/lines/{SYNTHETIC_IMSI}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_an_imported_sim_is_provisioned_with_empty_service_fields(env: Env) -> None:
    env.import_sim()
    r = env.get(f"/v1/lines/{SYNTHETIC_IMSI}")
    assert r.status_code == 200
    assert r.json() == {
        "status": "provisioned",
        "msisdn": None,
        "apns": [],
        "ue_ip": None,
        "speed_ul_mbps": None,
        "speed_dl_mbps": None,
    }


def test_a_stored_line_state_is_reported(env: Env) -> None:
    env.lines.put(
        LineState(
            SYNTHETIC_IMSI,
            "active",
            datetime(2026, 10, 11, tzinfo=UTC),
            msisdn="2340000000001",
            apns=("internet", "ims"),
            ue_ip="10.45.0.2",
            speed_ul_mbps=5.0,
            speed_dl_mbps=20.0,
            data_mode="full",
        )
    )
    body = env.get(f"/v1/lines/{SYNTHETIC_IMSI}").json()
    assert body == {
        "status": "active",
        "msisdn": "2340000000001",
        "apns": ["internet", "ims"],
        "ue_ip": "10.45.0.2",
        "speed_ul_mbps": 5.0,
        "speed_dl_mbps": 20.0,
    }


def test_the_response_has_exactly_the_contract_fields_and_never_a_key(env: Env) -> None:
    env.import_sim()
    r = env.get(f"/v1/lines/{SYNTHETIC_IMSI}")
    assert set(r.json()) == LINE_FIELDS
    assert SYNTHETIC_KI_HEX not in r.text and SYNTHETIC_OPC_HEX not in r.text
    assert "ki" not in r.json() and "opc" not in r.json()


def test_one_line_does_not_show_another_lines_state(env: Env) -> None:
    env.lines.put(LineState(SYNTHETIC_IMSI, "active", datetime(2026, 10, 11, tzinfo=UTC)))
    assert env.get(f"/v1/lines/{SYNTHETIC_IMSI_2}").status_code == 404


@pytest.mark.parametrize("bad", ["abc", "62100000000000", "6210000000000012", "62100000000000a"])
def test_a_malformed_imsi_is_422(env: Env, bad: str) -> None:
    assert env.get(f"/v1/lines/{bad}").status_code == 422


@pytest.mark.parametrize("path", [f"/v1/lines/{SYNTHETIC_IMSI}", "/v1/assignments"])
@pytest.mark.parametrize("token", [None, "", "rlk_nope.nope", "garbage"])
def test_a_missing_or_wrong_key_is_the_same_generic_401(
    env: Env, path: str, token: str | None
) -> None:
    r = env.get(path, token=token)
    assert r.status_code == 401
    assert r.json() == UNAUTHORIZED
    assert r.headers["www-authenticate"] == "Bearer"


def test_authentication_comes_before_imsi_validation(env: Env) -> None:
    r = env.get("/v1/lines/not-an-imsi", token=None)
    assert r.status_code == 401 and r.json() == UNAUTHORIZED


def test_a_post_to_a_read_only_path_is_refused(env: Env) -> None:
    r = env.client.post(
        f"/v1/lines/{SYNTHETIC_IMSI}", headers={"Authorization": f"Bearer {env.token}"}
    )
    assert r.status_code == 405


# --- GET /v1/assignments ---


def test_no_assignments_is_an_empty_list(env: Env) -> None:
    r = env.get("/v1/assignments")
    assert r.status_code == 200 and r.json() == {"assignments": []}


def test_assignments_list_each_address_with_its_line(env: Env) -> None:
    env.allocator.allocate(SYNTHETIC_IMSI)
    env.allocator.allocate(SYNTHETIC_IMSI_2)
    assert env.get("/v1/assignments").json() == {
        "assignments": [
            {"ue_ip": "10.45.0.2", "imsi": SYNTHETIC_IMSI},
            {"ue_ip": "10.45.0.3", "imsi": SYNTHETIC_IMSI_2},
        ]
    }


def test_a_released_address_is_still_listed_during_the_hold_then_dropped(env: Env) -> None:
    env.allocator.allocate(SYNTHETIC_IMSI)
    env.allocator.release(SYNTHETIC_IMSI)
    env.clock.advance(seconds=24 * 3600 - 1)
    assert [a["imsi"] for a in env.get("/v1/assignments").json()["assignments"]] == [SYNTHETIC_IMSI]
    env.clock.advance(seconds=2)
    assert env.get("/v1/assignments").json() == {"assignments": []}


def test_the_assignments_response_holds_only_addresses_and_imsis(env: Env) -> None:
    env.import_sim()
    env.allocator.allocate(SYNTHETIC_IMSI)
    r = env.get("/v1/assignments")
    for item in r.json()["assignments"]:
        assert set(item) == {"ue_ip", "imsi"}
    assert SYNTHETIC_KI_HEX not in json.dumps(r.json())


def test_assignments_are_read_only(env: Env) -> None:
    r = env.client.delete("/v1/assignments", headers={"Authorization": f"Bearer {env.token}"})
    assert r.status_code == 405
