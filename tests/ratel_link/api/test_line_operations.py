"""Activate, data and deactivate through the real app, with in-memory storage."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from ratel_link.config import Settings
from ratel_link.domain.ip_pool import IpPool
from ratel_link.main import create_app
from ratel_link.services.ip_allocation import IpAllocator
from tests.ratel_link.fakes import (
    FakeClock,
    InMemoryApiKeyRepository,
    InMemoryAuditLogRepository,
    InMemoryIpAllocationRepository,
    InMemoryLineStateRepository,
    InMemorySimKeyRepository,
    InMemorySubscriberRepository,
    InMemoryVoiceTemplate,
    StaticKeyProvider,
)
from tests.ratel_link.helpers import all_fakes, register_system
from tests.synthetic import (
    SYNTHETIC_IMS_SESSION,
    SYNTHETIC_IMSI,
    SYNTHETIC_IMSI_2,
    SYNTHETIC_KI_HEX,
    SYNTHETIC_MSISDN,
    SYNTHETIC_OPC_HEX,
)

REGISTERED = object()  # sentinel: send the environment's own valid key
UNAUTHORIZED = {"error": {"code": "unauthorized", "message": "Invalid or missing API key."}}
ACTIVATE = f"/v1/lines/{SYNTHETIC_IMSI}/activate"
DATA = f"/v1/lines/{SYNTHETIC_IMSI}/data"
DEACTIVATE = f"/v1/lines/{SYNTHETIC_IMSI}/deactivate"
REASON = {"reason": "customer asked to cancel"}


def good(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "msisdn": SYNTHETIC_MSISDN,
        "speed_ul_mbps": 5,
        "speed_dl_mbps": 10,
        "voice": True,
    }
    body.update(changes)
    return body


class Env:
    def __init__(self, *, voice_template: bool = True, pool: str = "10.45.0.0/16") -> None:
        self.api_keys = InMemoryApiKeyRepository()
        self.sims = InMemorySimKeyRepository()
        self.audit = InMemoryAuditLogRepository()
        self.lines = InMemoryLineStateRepository()
        self.ips = InMemoryIpAllocationRepository()
        self.subscribers = InMemorySubscriberRepository()
        self.clock = FakeClock()
        self.app = create_app(
            Settings(ratel_link_ue_pool=pool),
            **{
                **all_fakes(),
                "api_keys": self.api_keys,
                "sim_keys": self.sims,
                "audit": self.audit,
                "line_states": self.lines,
                "ip_allocations": self.ips,
                "subscribers": self.subscribers,
                "voice_template": InMemoryVoiceTemplate(
                    SYNTHETIC_IMS_SESSION if voice_template else None
                ),
            },
            key_provider=StaticKeyProvider(),
            clock=self.clock,
        )
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.token = register_system(self.api_keys, self.clock)
        self.allocator = IpAllocator(self.ips, IpPool.from_cidr(pool), self.clock)

    def _headers(self, token: Any, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(extra or {})
        key = self.token if token is REGISTERED else token
        if key is not None:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def post(
        self,
        path: str,
        payload: Any = None,
        *,
        token: Any = REGISTERED,
        headers: dict[str, str] | None = None,
        **kw: Any,
    ) -> Any:
        return self.client.post(path, json=payload, headers=self._headers(token, headers), **kw)

    def import_sim(self, imsi: str = SYNTHETIC_IMSI) -> None:
        r = self.post("/v1/sims", {"imsi": imsi, "ki": SYNTHETIC_KI_HEX, "opc": SYNTHETIC_OPC_HEX})
        assert r.status_code == 200

    def line(self, imsi: str = SYNTHETIC_IMSI) -> Any:
        return self.client.get(f"/v1/lines/{imsi}", headers=self._headers(REGISTERED))


@pytest.fixture
def env() -> Env:
    e = Env()
    e.import_sim()
    return e


# --- activate ---------------------------------------------------------------------------------


def test_activating_an_imported_sim_is_200_with_an_empty_object(env: Env) -> None:
    r = env.post(ACTIVATE, good())
    assert r.status_code == 200 and r.json() == {}


def test_the_line_then_reports_as_active_with_its_address_and_speeds(env: Env) -> None:
    env.post(ACTIVATE, good())
    r = env.line()
    assert r.status_code == 200
    assert r.json() == {
        "status": "active",
        "msisdn": SYNTHETIC_MSISDN,
        "apns": ["internet", "ims"],
        "ue_ip": "10.45.0.2",
        "speed_ul_mbps": 5.0,
        "speed_dl_mbps": 10.0,
    }


def test_the_address_shows_in_the_assignments_list(env: Env) -> None:
    env.post(ACTIVATE, good())
    r = env.client.get("/v1/assignments", headers=env._headers(REGISTERED))
    assert r.json() == {"assignments": [{"ue_ip": "10.45.0.2", "imsi": SYNTHETIC_IMSI}]}


def test_activating_twice_with_the_same_settings_is_200_and_changes_nothing(env: Env) -> None:
    assert env.post(ACTIVATE, good()).status_code == 200
    document = repr(env.subscribers.documents)
    assert env.post(ACTIVATE, good()).status_code == 200
    assert repr(env.subscribers.documents) == document
    assert len(env.audit.entries) == 2  # the SIM import, and one activation


def test_the_audit_entry_names_the_calling_system(env: Env) -> None:
    env.post(ACTIVATE, good())
    entry = env.audit.entries[-1]
    assert (entry["action"], entry["api_key_id"], entry["imsi"]) == (
        "line.activate",
        "bss-app",
        SYNTHETIC_IMSI,
    )


def test_an_unknown_sim_is_404_and_nothing_is_written(env: Env) -> None:
    r = env.post(f"/v1/lines/{SYNTHETIC_IMSI_2}/activate", good())
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert not env.subscribers.documents and not env.ips.by_ip


def test_voice_without_a_template_is_503_and_nothing_is_written() -> None:
    env = Env(voice_template=False)
    env.import_sim()
    r = env.post(ACTIVATE, good(voice=True))
    assert r.status_code == 503 and r.json()["error"]["code"] == "unavailable"
    assert not env.subscribers.documents and not env.ips.by_ip


def test_a_line_without_voice_works_with_no_template() -> None:
    env = Env(voice_template=False)
    env.import_sim()
    assert env.post(ACTIVATE, good(voice=False)).status_code == 200
    assert env.line().json()["apns"] == ["internet"]


def test_a_full_pool_is_503_for_the_next_line() -> None:
    env = Env(pool="10.45.0.0/30")
    env.import_sim()
    env.import_sim(SYNTHETIC_IMSI_2)
    assert env.post(ACTIVATE, good()).status_code == 200
    r = env.post(f"/v1/lines/{SYNTHETIC_IMSI_2}/activate", good())
    assert r.status_code == 503 and r.json()["error"]["code"] == "unavailable"
    assert SYNTHETIC_IMSI_2 not in env.subscribers.documents


@pytest.mark.parametrize(
    "msisdn",
    [
        "+2342064730042",  # a plus sign
        "02064730042",  # the dialled form
        "234206473004",  # one digit short
        "23420647300421",  # one digit long
        "2352064730042",  # not 234
        "234206473004a",
        " 2342064730042",
        "",
        2342064730042,
        None,
    ],
)
def test_a_phone_number_not_in_the_stored_form_is_422(env: Env, msisdn: Any) -> None:
    assert env.post(ACTIVATE, good(msisdn=msisdn)).status_code == 422
    assert not env.subscribers.documents


@pytest.mark.parametrize(
    "speed", [0, -1, 0.0, 10_000.5, 1e30, "10", None, True, [5], 1.23456789, 0.0000005]
)
def test_a_speed_that_is_not_allowed_is_422(env: Env, speed: Any) -> None:
    assert env.post(ACTIVATE, good(speed_dl_mbps=speed)).status_code == 422
    assert env.post(ACTIVATE, good(speed_ul_mbps=speed)).status_code == 422
    assert not env.subscribers.documents


@pytest.mark.parametrize("speed", [0.128, 1.5, 3.85, 10, 10_000])
def test_every_speed_the_contract_allows_is_accepted(env: Env, speed: float) -> None:
    assert env.post(ACTIVATE, good(speed_dl_mbps=speed, speed_ul_mbps=speed)).status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"msisdn": SYNTHETIC_MSISDN},
        good(voice="yes"),
        good(voice=None),
        {**good(), "ki": SYNTHETIC_KI_HEX},  # extra fields are refused
        {**good(), "ue_ip": "10.45.0.250"},  # the address is never chosen by the caller
        [],
        "text",
    ],
)
def test_a_malformed_body_is_422(env: Env, payload: Any) -> None:
    assert env.post(ACTIVATE, payload).status_code == 422


@pytest.mark.parametrize("bad", ["abc", "62100000000000", "6210000000000012", "62100000000000a"])
def test_a_malformed_imsi_is_422(env: Env, bad: str) -> None:
    assert env.post(f"/v1/lines/{bad}/activate", good()).status_code == 422


def test_an_empty_idempotency_key_is_422_and_a_present_one_is_fine(env: Env) -> None:
    assert env.post(ACTIVATE, good(), headers={"Idempotency-Key": ""}).status_code == 422
    assert env.post(ACTIVATE, good(), headers={"Idempotency-Key": "abc-123"}).status_code == 200


def test_the_error_bodies_never_echo_a_number_or_a_key(env: Env) -> None:
    for payload in (good(msisdn="+2342064730042"), good(speed_dl_mbps=1.23456789)):
        text = env.post(ACTIVATE, payload).text
        assert "2064730042" not in text and "1.23456789" not in text
    assert SYNTHETIC_KI_HEX not in env.post(ACTIVATE, {**good(), "ki": SYNTHETIC_KI_HEX}).text


# --- data -------------------------------------------------------------------------------------


def test_data_slow_off_and_full_round_trip(env: Env) -> None:
    env.post(ACTIVATE, good())
    assert (
        env.post(DATA, {"mode": "slow", "speed_ul_mbps": 0.128, "speed_dl_mbps": 0.256}).status_code
        == 200
    )
    assert env.line().json()["speed_dl_mbps"] == 0.256
    assert env.post(DATA, {"mode": "off"}).status_code == 200
    assert env.line().json()["apns"] == ["ims"]
    assert (
        env.post(DATA, {"mode": "full", "speed_ul_mbps": 5, "speed_dl_mbps": 10}).status_code == 200
    )
    assert env.line().json()["apns"] == ["internet", "ims"]


def test_calling_survives_every_data_change(env: Env) -> None:
    env.post(ACTIVATE, good())
    for payload in (
        {"mode": "slow", "speed_ul_mbps": 1, "speed_dl_mbps": 1},
        {"mode": "off"},
        {"mode": "full", "speed_ul_mbps": 5, "speed_dl_mbps": 10},
    ):
        env.post(DATA, payload)
        names = [
            s["name"] for s in env.subscribers.documents[SYNTHETIC_IMSI]["slice"][0]["session"]
        ]
        assert "ims" in names


def test_data_on_a_line_that_was_never_activated_is_404(env: Env) -> None:
    r = env.post(DATA, {"mode": "off"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_data_full_or_slow_without_speeds_is_422(env: Env) -> None:
    env.post(ACTIVATE, good())
    for payload in ({"mode": "full"}, {"mode": "slow", "speed_ul_mbps": 1}):
        assert env.post(DATA, payload).status_code == 422


@pytest.mark.parametrize("speed", [5e-324, 1.23456789, 0, -1, "1", True, None])
def test_a_bad_speed_is_422_even_when_the_mode_does_not_use_it(env: Env, speed: Any) -> None:
    # Found by the contract fuzzer: `off` ignores speeds, but a present speed must still be valid.
    env.post(ACTIVATE, good())
    assert env.post(DATA, {"mode": "off", "speed_dl_mbps": speed}).status_code == 422
    assert env.post(DATA, {"mode": "off", "speed_ul_mbps": speed}).status_code == 422


@pytest.mark.parametrize("payload", [{}, {"mode": "fast"}, {"mode": None}, {"mode": "off", "x": 1}])
def test_a_malformed_data_body_is_422(env: Env, payload: Any) -> None:
    env.post(ACTIVATE, good())
    assert env.post(DATA, payload).status_code == 422


def test_a_missing_core_record_is_409_and_nothing_is_recorded(env: Env) -> None:
    env.post(ACTIVATE, good())
    entries = len(env.audit.entries)
    del env.subscribers.documents[SYNTHETIC_IMSI]
    r = env.post(DATA, {"mode": "off"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    assert len(env.audit.entries) == entries


# --- deactivate -------------------------------------------------------------------------------


def test_deactivating_is_200_with_an_empty_object_and_the_document_is_gone(env: Env) -> None:
    env.post(ACTIVATE, good())
    r = env.post(DEACTIVATE, REASON)
    assert r.status_code == 200 and r.json() == {}
    assert SYNTHETIC_IMSI not in env.subscribers.documents


def test_the_line_then_reports_as_provisioned_and_keeps_its_address_on_hold(env: Env) -> None:
    env.post(ACTIVATE, good())
    env.post(DEACTIVATE, REASON)
    assert env.line().json() == {
        "status": "provisioned",
        "msisdn": None,
        "apns": [],
        "ue_ip": None,
        "speed_ul_mbps": None,
        "speed_dl_mbps": None,
    }
    # The released address stays listed for 24 hours: usage seen on it still belongs to this line.
    r = env.client.get("/v1/assignments", headers=env._headers(REGISTERED))
    assert r.json() == {"assignments": [{"ue_ip": "10.45.0.2", "imsi": SYNTHETIC_IMSI}]}


def test_a_deactivated_line_can_be_activated_again_with_the_same_address(env: Env) -> None:
    env.post(ACTIVATE, good())
    env.post(DEACTIVATE, REASON)
    assert env.post(ACTIVATE, good()).status_code == 200
    assert env.line().json()["ue_ip"] == "10.45.0.2" and env.line().json()["status"] == "active"


def test_deactivating_twice_is_200_and_records_nothing_more(env: Env) -> None:
    env.post(ACTIVATE, good())
    env.post(DEACTIVATE, REASON)
    entries = len(env.audit.entries)
    assert env.post(DEACTIVATE, REASON).status_code == 200
    assert len(env.audit.entries) == entries


def test_deactivating_a_sim_that_was_never_activated_is_200(env: Env) -> None:
    assert env.post(DEACTIVATE, REASON).status_code == 200
    assert env.line().json()["status"] == "provisioned"


def test_deactivating_an_unknown_sim_is_404(env: Env) -> None:
    r = env.post(f"/v1/lines/{SYNTHETIC_IMSI_2}/deactivate", REASON)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_data_on_a_deactivated_line_is_404(env: Env) -> None:
    env.post(ACTIVATE, good())
    env.post(DEACTIVATE, REASON)
    assert env.post(DATA, {"mode": "off"}).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"reason": ""},
        {"reason": 5},
        {"reason": None},
        {"reason": "x" * 201},
        {"why": "x"},
    ],
)
def test_a_malformed_deactivate_body_is_422_and_changes_nothing(env: Env, payload: Any) -> None:
    env.post(ACTIVATE, good())
    assert env.post(DEACTIVATE, payload).status_code == 422
    assert SYNTHETIC_IMSI in env.subscribers.documents


def test_the_longest_allowed_reason_is_accepted(env: Env) -> None:
    env.post(ACTIVATE, good())
    assert env.post(DEACTIVATE, {"reason": "x" * 200}).status_code == 200


# --- authentication ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [ACTIVATE, DATA, DEACTIVATE])
@pytest.mark.parametrize("token", [None, "", "rlk_nope.nope", "garbage"])
def test_a_missing_or_wrong_key_is_the_same_generic_401(env: Env, path: str, token: Any) -> None:
    r = env.post(path, good(), token=token)
    assert r.status_code == 401 and r.json() == UNAUTHORIZED
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("path", [ACTIVATE, DATA, DEACTIVATE, "/v1/lines/not-an-imsi/activate"])
def test_authentication_comes_before_body_and_path_validation(env: Env, path: str) -> None:
    r = env.client.post(path, content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 401 and r.json() == UNAUTHORIZED
    assert not env.subscribers.documents


def test_nothing_is_written_for_an_unauthenticated_request(env: Env) -> None:
    env.post(ACTIVATE, good(), token=None)
    assert not env.subscribers.documents and not env.ips.by_ip and not env.lines.states


def test_a_get_on_a_write_only_path_is_refused(env: Env) -> None:
    r = env.client.get(ACTIVATE, headers=env._headers(REGISTERED))
    assert r.status_code == 405
