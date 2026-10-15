"""RatelLink's repositories against a real MongoDB (compose.dev.yaml).

Run: make up, export RATEL_TEST_MONGO_URI (local root URI with ?authSource=admin), then
`make test-integration`. Each run uses its own throwaway database and drops it afterwards.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

import pytest
from pydantic import SecretStr
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from common.timeutil import utc_now
from ratel_link import admin_cli
from ratel_link.config import Settings
from ratel_link.domain.api_keys import ApiKeyRecord
from ratel_link.domain.ip_pool import Assignment, IpPool, hold_cutoff
from ratel_link.domain.line_state import LineState
from ratel_link.domain.subscriber import (
    activation_fields,
    ambr_document,
    ims_session_from_template,
    internet_session,
    speed_from_mbps,
)
from ratel_link.repositories.mongo import (
    MongoApiKeyRepository,
    MongoAuditLogRepository,
    MongoIpAllocationRepository,
    MongoLineStateRepository,
    MongoSimKeyRepository,
    MongoSubscriberRepository,
    ensure_indexes,
    missing_indexes,
    open_database,
    subscriber_index_missing,
)
from ratel_link.security.crypto import DecryptionError
from ratel_link.services.api_key_admin import KeyPolicy, create_system, revoke, rotate
from ratel_link.services.assignments import AssignmentService
from ratel_link.services.audit_log import AuditLog
from ratel_link.services.authentication import ApiPrincipal, authenticate
from ratel_link.services.ip_allocation import IpAllocator
from ratel_link.services.sim_keys import SimKeyStore
from tests.ratel_link.fakes import StaticKeyProvider
from tests.synthetic import (
    SYNTHETIC_IMS_SESSION,
    SYNTHETIC_IMSI,
    SYNTHETIC_IMSI_2,
    SYNTHETIC_KI_HEX,
    SYNTHETIC_MSISDN,
    SYNTHETIC_OPC_HEX,
)

pytestmark = pytest.mark.integration

ALL_INDEXES = [
    "sim_key.imsi",
    "api_key.api_key_id",
    "ip_allocation.ue_ip",
    "ip_allocation.imsi",
    "line_state.imsi",
]
HEX_KI = SYNTHETIC_KI_HEX
HEX_OPC = SYNTHETIC_OPC_HEX


@pytest.fixture
def database() -> Iterator[Database[Any]]:
    uri = os.environ.get("RATEL_TEST_MONGO_URI")
    if not uri:
        pytest.skip("RATEL_TEST_MONGO_URI is not set")
    name = f"ratel_link_it_{secrets.token_hex(4)}"
    db = open_database(Settings(mongo_uri=SecretStr(uri), ratel_link_db_name=name))
    try:
        yield db
    finally:
        db.client.drop_database(name)
        db.client.close()


@pytest.fixture
def core() -> Iterator[Database[Any]]:
    """A throwaway stand-in for the core's `open5gs` database, with the unique index on `imsi`
    that Open5GS's own tooling creates. Never the real `open5gs` database."""
    uri = os.environ.get("RATEL_TEST_MONGO_URI")
    if not uri:
        pytest.skip("RATEL_TEST_MONGO_URI is not set")
    name = f"open5gs_it_{secrets.token_hex(4)}"
    db = open_database(Settings(mongo_uri=SecretStr(uri), ratel_link_db_name=name))
    db["subscribers"].create_index("imsi", unique=True)
    try:
        yield db
    finally:
        db.client.drop_database(name)
        db.client.close()


def _store(database: Database[Any]) -> SimKeyStore:
    return SimKeyStore(MongoSimKeyRepository(database), StaticKeyProvider())


def test_indexes_are_created_idempotently(database: Database[Any]) -> None:
    both = ALL_INDEXES
    assert missing_indexes(database) == both
    assert ensure_indexes(database) == both
    assert missing_indexes(database) == []
    ensure_indexes(database)  # second run changes nothing and does not fail
    assert missing_indexes(database) == []


def test_a_non_unique_index_does_not_count_as_the_required_one(database: Database[Any]) -> None:
    database["sim_key"].create_index("imsi")  # same field, not unique
    assert missing_indexes(database) == ALL_INDEXES


def test_raw_document_has_no_plaintext(database: Database[Any]) -> None:
    ensure_indexes(database)
    _store(database).put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC))
    raw = database["sim_key"].find_one({"imsi": SYNTHETIC_IMSI})
    assert raw is not None
    assert set(raw) == {"_id", "imsi", "ki", "opc", "created_at"}
    assert set(raw["ki"]) == {"v", "alg", "kid", "nonce", "ct"}
    text = json.dumps(raw, default=str)
    assert HEX_KI not in text and HEX_OPC not in text
    assert raw["created_at"].utcoffset().total_seconds() == 0


def test_round_trip_through_mongo(database: Database[Any]) -> None:
    store = _store(database)
    store.put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC))
    keys = store.get_keys(SYNTHETIC_IMSI)
    assert keys is not None
    assert (keys.ki.get_secret_value(), keys.opc.get_secret_value()) == (
        HEX_KI,
        HEX_OPC,
    )
    assert store.get_keys(SYNTHETIC_IMSI_2) is None


@pytest.mark.parametrize("with_index", [True, False])
def test_reimport_creates_no_second_document(database: Database[Any], with_index: bool) -> None:
    if with_index:
        ensure_indexes(database)
    store = _store(database)
    assert store.put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC)) is True
    assert store.put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_OPC), SecretStr(HEX_KI)) is False
    assert database["sim_key"].count_documents({"imsi": SYNTHETIC_IMSI}) == 1
    keys = store.get_keys(SYNTHETIC_IMSI)
    assert keys is not None and keys.ki.get_secret_value() == HEX_KI  # the first import is kept


def test_unique_index_rejects_a_duplicate_imsi(database: Database[Any]) -> None:
    ensure_indexes(database)
    _store(database).put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC))
    with pytest.raises(DuplicateKeyError):
        database["sim_key"].insert_one({"imsi": SYNTHETIC_IMSI})


def test_concurrent_imports_of_one_imsi_store_exactly_once(database: Database[Any]) -> None:
    ensure_indexes(database)
    store = _store(database)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: store.put_if_absent(
                    SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC)
                ),
                range(16),
            )
        )
    assert results.count(True) == 1
    assert results.count(False) == 15
    assert database["sim_key"].count_documents({}) == 1


def test_a_record_swapped_inside_mongo_fails_to_decrypt(database: Database[Any]) -> None:
    store = _store(database)
    store.put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC))
    store.put_if_absent(SYNTHETIC_IMSI_2, SecretStr(HEX_OPC), SecretStr(HEX_KI))
    source = database["sim_key"].find_one({"imsi": SYNTHETIC_IMSI})
    assert source is not None
    database["sim_key"].update_one({"imsi": SYNTHETIC_IMSI_2}, {"$set": {"ki": source["ki"]}})
    with pytest.raises(DecryptionError):
        store.get_keys(SYNTHETIC_IMSI_2)


# --- API keys -----------------------------------------------------------------------------------


def test_api_key_repository_round_trip(database: Database[Any]) -> None:
    ensure_indexes(database)
    repo = MongoApiKeyRepository(database)
    now = utc_now()
    token = create_system(repo, "bss-app", "RatelBSS", now, KeyPolicy())
    record = repo.get("bss-app")
    assert record is not None
    assert record.generations[0].created_at == now  # whole seconds survive BSON, and stay UTC
    assert record.generations[0].created_at.utcoffset().total_seconds() == 0
    assert repo.get("nobody") is None
    assert repo.insert(record) is False  # unique id
    raw = database["api_key"].find_one({"api_key_id": "bss-app"})
    assert raw is not None
    text = json.dumps(raw, default=str)
    assert token not in text and token.split(".", 1)[1] not in text  # only the hash is stored
    assert raw["generations"][0]["secret_hash"] == record.generations[0].secret_hash


def test_api_key_unique_index_rejects_a_duplicate_id(database: Database[Any]) -> None:
    ensure_indexes(database)
    create_system(MongoApiKeyRepository(database), "bss-app", "x", utc_now(), KeyPolicy())
    with pytest.raises(DuplicateKeyError):
        database["api_key"].insert_one({"api_key_id": "bss-app"})


def test_api_key_replace_and_list(database: Database[Any]) -> None:
    repo = MongoApiKeyRepository(database)
    now = utc_now()
    create_system(repo, "meter-agent", "RatelMeter agent", now, KeyPolicy())
    create_system(repo, "bss-app", "RatelBSS", now, KeyPolicy())
    assert [r.api_key_id for r in repo.list_all()] == ["bss-app", "meter-agent"]
    rotate(repo, "bss-app", now, KeyPolicy())
    revoke(repo, "bss-app", 1, now)
    record = repo.get("bss-app")
    assert record is not None
    assert [g.generation for g in record.generations] == [1, 2]
    assert record.generations[0].revoked_at == now
    with pytest.raises(KeyError):
        repo.replace(ApiKeyRecord("ghost", "x", "active", now))
    assert repo.get("ghost") is None  # replace never creates


def test_admin_cli_end_to_end(
    database: Database[Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    uri = os.environ["RATEL_TEST_MONGO_URI"]
    monkeypatch.setenv("MONGO_URI", uri)
    monkeypatch.setenv("RATEL_LINK_DB_NAME", database.name)

    assert admin_cli.main(["init-db"]) == 0
    assert missing_indexes(database) == []
    capsys.readouterr()

    assert admin_cli.main(["api-key", "create", "--id", "bss-app", "--name", "RatelBSS"]) == 0
    token = capsys.readouterr().out.strip()
    repo = MongoApiKeyRepository(database)
    assert authenticate(f"Bearer {token}", repo, utc_now()) == ApiPrincipal("bss-app", 1)

    assert admin_cli.main(["api-key", "list"]) == 0
    listing = capsys.readouterr().out
    assert "bss-app" in listing and token not in listing

    assert admin_cli.main(["api-key", "revoke", "--id", "bss-app", "--generation", "1"]) == 0
    capsys.readouterr()
    assert not isinstance(authenticate(f"Bearer {token}", repo, utc_now()), ApiPrincipal)


# --- startup ------------------------------------------------------------------------------------


def test_startup_reports_missing_indexes_then_stays_quiet_after_init_db(
    database: Database[Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from fastapi.testclient import TestClient

    from ratel_link.main import create_app

    settings = Settings(
        mongo_uri=SecretStr(os.environ["RATEL_TEST_MONGO_URI"]), ratel_link_db_name=database.name
    )
    caplog.set_level(logging.INFO)

    with TestClient(create_app(settings)):
        pass
    (event,) = [r for r in caplog.records if r.__dict__.get("event") == "startup.indexes.missing"]
    assert event.__dict__["indexes"] == ALL_INDEXES
    assert missing_indexes(database) != []  # startup reported, it did not create anything

    ensure_indexes(database)
    caplog.clear()
    with TestClient(create_app(settings)):
        pass
    assert not [r for r in caplog.records if r.__dict__.get("event") == "startup.indexes.missing"]


# --- audit log ----------------------------------------------------------------------------------


def test_audit_entries_are_stored_as_the_build_plan_describes(database: Database[Any]) -> None:
    log = AuditLog(MongoAuditLogRepository(database))
    log.append(
        "line.activate", SYNTHETIC_IMSI, {"status": "provisioned"}, {"status": "active"}, "bss-app"
    )
    (raw,) = list(database["audit_log"].find({}))
    assert set(raw) == {"_id", "at", "api_key_id", "action", "imsi", "before", "after"}
    assert raw["api_key_id"] == "bss-app" and raw["before"] == {"status": "provisioned"}
    assert raw["at"].utcoffset().total_seconds() == 0


# --- fixed IP addresses -------------------------------------------------------------------------


def _allocator(database: Database[Any]) -> tuple[IpAllocator, MongoIpAllocationRepository]:
    repo = MongoIpAllocationRepository(database)
    return IpAllocator(repo, IpPool.from_cidr("10.45.0.0/16")), repo


def test_addresses_are_allocated_and_held_in_mongodb(database: Database[Any]) -> None:
    ensure_indexes(database)
    allocator, repo = _allocator(database)
    first = allocator.allocate(SYNTHETIC_IMSI)
    assert first == "10.45.0.2" and allocator.allocate(SYNTHETIC_IMSI) == first
    assert allocator.allocate(SYNTHETIC_IMSI_2) == "10.45.0.3"
    allocator.release(SYNTHETIC_IMSI)
    raw = database["ip_allocation"].find_one({"ue_ip": first})
    assert raw is not None and raw["state"] == "released" and raw["released_at"] is not None
    assert raw["released_at"].utcoffset().total_seconds() == 0
    # during the hold nobody else gets it, but its own line can have it back
    assert repo.unavailable(hold_cutoff(utc_now())) == {first, "10.45.0.3"}
    assert allocator.allocate(SYNTHETIC_IMSI) == first


def test_the_unique_indexes_refuse_a_second_holder(database: Database[Any]) -> None:
    ensure_indexes(database)
    _, repo = _allocator(database)
    now = utc_now()
    assert repo.claim_free("10.45.0.9", SYNTHETIC_IMSI, now, hold_cutoff(now)) is True
    assert repo.claim_free("10.45.0.9", SYNTHETIC_IMSI_2, now, hold_cutoff(now)) is False  # taken
    assert repo.claim_free("10.45.0.10", SYNTHETIC_IMSI, now, hold_cutoff(now)) is False  # has one
    assert database["ip_allocation"].count_documents({}) == 1


def test_a_released_address_is_taken_over_only_after_the_hold(database: Database[Any]) -> None:
    ensure_indexes(database)
    _, repo = _allocator(database)
    from datetime import timedelta

    t0 = utc_now()
    repo.claim_free("10.45.0.9", SYNTHETIC_IMSI, t0, hold_cutoff(t0))
    repo.release(SYNTHETIC_IMSI, t0)
    soon = t0 + timedelta(hours=23, minutes=59)
    assert repo.claim_free("10.45.0.9", SYNTHETIC_IMSI_2, soon, hold_cutoff(soon)) is False
    later = t0 + timedelta(hours=24)
    assert repo.claim_free("10.45.0.9", SYNTHETIC_IMSI_2, later, hold_cutoff(later)) is True
    assert repo.reclaim("10.45.0.9", SYNTHETIC_IMSI, later) is False  # it is no longer theirs
    owner = database["ip_allocation"].find_one({"ue_ip": "10.45.0.9"})
    assert owner is not None and owner["imsi"] == SYNTHETIC_IMSI_2 and owner["state"] == "active"


def test_many_activations_at_once_never_share_an_address(database: Database[Any]) -> None:
    ensure_indexes(database)
    allocator, _ = _allocator(database)
    imsis = [f"6210000000{n:05d}" for n in range(60)]
    with ThreadPoolExecutor(max_workers=12) as pool:
        addresses = list(pool.map(allocator.allocate, imsis))
    assert len(set(addresses)) == 60
    assert database["ip_allocation"].count_documents({}) == 60


def test_the_same_line_activated_twice_at_once_gets_one_address(database: Database[Any]) -> None:
    ensure_indexes(database)
    allocator, _ = _allocator(database)
    with ThreadPoolExecutor(max_workers=8) as pool:
        addresses = list(pool.map(lambda _: allocator.allocate(SYNTHETIC_IMSI), range(16)))
    assert len(set(addresses)) == 1
    assert database["ip_allocation"].count_documents({"imsi": SYNTHETIC_IMSI}) == 1


# --- line state, assignments, and GET /v1/lines, GET /v1/assignments -----------------------------


def _line(imsi: str = SYNTHETIC_IMSI, **changes: Any) -> LineState:
    fields: dict[str, Any] = {
        "imsi": imsi,
        "status": "active",
        "updated_at": utc_now(),
        "msisdn": "2340000000001",
        "apns": ("internet", "ims"),
        "ue_ip": "10.45.0.2",
        "speed_ul_mbps": 5.0,
        "speed_dl_mbps": 20.0,
        "data_mode": "full",
    }
    fields.update(changes)
    return LineState(**fields)


def test_line_state_round_trips_with_utc_times(database: Database[Any]) -> None:
    ensure_indexes(database)
    repo = MongoLineStateRepository(database)
    assert repo.get(SYNTHETIC_IMSI) is None
    state = _line(updated_at=utc_now().replace(microsecond=0))
    repo.put(state)
    assert repo.get(SYNTHETIC_IMSI) == state
    raw = database["line_state"].find_one({"imsi": SYNTHETIC_IMSI})
    assert raw is not None and raw["updated_at"].utcoffset().total_seconds() == 0
    assert set(raw) == {"_id", *state.to_document()}  # no key material, nothing extra


def test_putting_a_line_state_again_replaces_it_and_keeps_one_document(
    database: Database[Any],
) -> None:
    ensure_indexes(database)
    repo = MongoLineStateRepository(database)
    repo.put(_line(status="active"))
    repo.put(_line(status="barred", ue_ip=None))
    got = repo.get(SYNTHETIC_IMSI)
    assert got is not None and (got.status, got.ue_ip) == ("barred", None)
    assert database["line_state"].count_documents({"imsi": SYNTHETIC_IMSI}) == 1


def test_concurrent_puts_for_one_line_leave_one_document(database: Database[Any]) -> None:
    ensure_indexes(database)
    repo = MongoLineStateRepository(database)
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda n: repo.put(_line(speed_dl_mbps=float(n))), range(48)))
    assert database["line_state"].count_documents({}) == 1


def test_the_unique_index_refuses_a_second_state_document_for_a_line(
    database: Database[Any],
) -> None:
    ensure_indexes(database)
    database["line_state"].insert_one(_line().to_document())
    with pytest.raises(DuplicateKeyError):
        database["line_state"].insert_one(_line().to_document())


def test_sim_key_exists_does_not_need_a_key_and_matches_what_is_stored(
    database: Database[Any],
) -> None:
    ensure_indexes(database)
    store = SimKeyStore(MongoSimKeyRepository(database), StaticKeyProvider(), utc_now)
    repo = MongoSimKeyRepository(database)
    assert repo.exists(SYNTHETIC_IMSI) is False
    store.put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC))
    assert repo.exists(SYNTHETIC_IMSI) is True
    assert repo.exists(SYNTHETIC_IMSI_2) is False


def test_assignments_come_from_mongodb_with_the_hold_applied(database: Database[Any]) -> None:
    ensure_indexes(database)
    allocator, repo = _allocator(database)
    service = AssignmentService(repo, utc_now)
    assert service.list_current() == []
    first = allocator.allocate(SYNTHETIC_IMSI)
    second = allocator.allocate(SYNTHETIC_IMSI_2)
    assert service.list_current() == [
        Assignment(first, SYNTHETIC_IMSI),
        Assignment(second, SYNTHETIC_IMSI_2),
    ]
    allocator.release(SYNTHETIC_IMSI)
    assert Assignment(first, SYNTHETIC_IMSI) in service.list_current()  # still on hold
    # age the release past the hold directly in the database
    database["ip_allocation"].update_one(
        {"ue_ip": first}, {"$set": {"released_at": utc_now() - timedelta(hours=25)}}
    )
    assert service.list_current() == [Assignment(second, SYNTHETIC_IMSI_2)]


def test_lines_and_assignments_over_http_against_mongodb(database: Database[Any]) -> None:
    from fastapi.testclient import TestClient

    from ratel_link.main import create_app

    ensure_indexes(database)
    settings = Settings(
        mongo_uri=SecretStr(os.environ["RATEL_TEST_MONGO_URI"]), ratel_link_db_name=database.name
    )
    token = create_system(
        MongoApiKeyRepository(database), "bss-app", "RatelBSS", utc_now(), KeyPolicy()
    )
    client = TestClient(create_app(settings, key_provider=StaticKeyProvider()))
    headers = {"Authorization": f"Bearer {token}"}
    line = f"/v1/lines/{SYNTHETIC_IMSI}"

    assert client.get(line, headers=headers).status_code == 404
    imported = {"imsi": SYNTHETIC_IMSI, "ki": HEX_KI, "opc": HEX_OPC}
    assert client.post("/v1/sims", json=imported, headers=headers).status_code == 200
    r = client.get(line, headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "provisioned"

    MongoLineStateRepository(database).put(_line())
    r = client.get(line, headers=headers)
    assert r.json()["status"] == "active" and r.json()["apns"] == ["internet", "ims"]
    assert HEX_KI not in r.text and HEX_OPC not in r.text

    allocator, _ = _allocator(database)
    address = allocator.allocate(SYNTHETIC_IMSI)
    r = client.get("/v1/assignments", headers=headers)
    assert r.json() == {"assignments": [{"ue_ip": address, "imsi": SYNTHETIC_IMSI}]}

    assert client.get(line).status_code == 401
    assert client.get("/v1/assignments").status_code == 401


# --- POST /v1/sims end to end (real app, real MongoDB) -------------------------------------------


def test_sim_import_over_http_against_mongodb(database: Database[Any]) -> None:
    from fastapi.testclient import TestClient

    from ratel_link.main import create_app

    ensure_indexes(database)
    settings = Settings(
        mongo_uri=SecretStr(os.environ["RATEL_TEST_MONGO_URI"]), ratel_link_db_name=database.name
    )
    token = create_system(
        MongoApiKeyRepository(database), "bss-app", "RatelBSS", utc_now(), KeyPolicy()
    )
    client = TestClient(create_app(settings, key_provider=StaticKeyProvider()))
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"imsi": SYNTHETIC_IMSI, "ki": HEX_KI, "opc": HEX_OPC}

    assert client.post("/v1/sims", json=payload, headers=headers).status_code == 200
    assert client.post("/v1/sims", json=payload, headers=headers).status_code == 200
    other = {**payload, "ki": HEX_OPC}
    assert client.post("/v1/sims", json=other, headers=headers).status_code == 409
    assert client.post("/v1/sims", json=payload).status_code == 401

    raw = database["sim_key"].find_one({"imsi": SYNTHETIC_IMSI})
    assert raw is not None and set(raw["ki"]) == {"v", "alg", "kid", "nonce", "ct"}
    assert HEX_KI not in json.dumps(raw, default=str) and HEX_OPC not in json.dumps(
        raw, default=str
    )
    assert database["sim_key"].count_documents({}) == 1
    entries = list(database["audit_log"].find({}))
    assert len(entries) == 1 and entries[0]["api_key_id"] == "bss-app"
    assert HEX_KI not in json.dumps(entries, default=str)


# --- the core's subscriber collection ---------------------------------------------------------


def _fields(voice: bool = True, upload: float = 5, download: float = 10) -> Any:
    ims = ims_session_from_template({"slice": [{"session": [SYNTHETIC_IMS_SESSION]}]})
    return activation_fields(
        msisdn=SYNTHETIC_MSISDN,
        ki=SecretStr(HEX_KI),
        opc=SecretStr(HEX_OPC),
        upload=speed_from_mbps(upload),
        download=speed_from_mbps(download),
        voice=voice,
        ue_ip="10.45.0.2",
        ims_session=ims if voice else None,
    )


def _activate(repo: MongoSubscriberRepository, imsi: str = SYNTHETIC_IMSI, **kw: Any) -> bool:
    fields = _fields(**kw)
    return repo.upsert_line(imsi, fields.owned, fields.created_only)


def _count(core: Database[Any], query: dict[str, Any]) -> int:
    return core["subscribers"].count_documents(query)


def test_the_unique_imsi_index_check_is_read_only_and_correct(core: Database[Any]) -> None:
    assert subscriber_index_missing(core) is False
    core["subscribers"].drop_index("imsi_1")
    assert subscriber_index_missing(core) is True
    core["subscribers"].create_index("imsi")  # present but not unique
    assert subscriber_index_missing(core) is True
    assert "subscribers" in core.list_collection_names()  # the check created nothing


def test_activation_creates_the_document_with_the_types_the_core_reads(core: Database[Any]) -> None:
    repo = MongoSubscriberRepository(core)
    assert _activate(repo) is True
    doc = core["subscribers"].find_one({"imsi": SYNTHETIC_IMSI})
    assert doc is not None
    assert doc["msisdn"] == [SYNTHETIC_MSISDN]
    assert doc["security"] == {
        "k": HEX_KI.upper(),
        "opc": HEX_OPC.upper(),
        "op": None,
        "amf": "8000",
    }
    assert "sqn" not in doc["security"]
    assert [s["name"] for s in doc["slice"][0]["session"]] == ["internet", "ims"]
    # BSON types, not Python types: the core wants int32 where the guide says so.
    for path in (
        "schema_version",
        "network_access_mode",
        "subscriber_status",
        "access_restriction_data",
        "subscribed_rau_tau_timer",
        "ambr.downlink.value",
        "ambr.downlink.unit",
        "slice.0.session.0.type",
        "slice.0.session.0.qos.index",
        "slice.0.session.0.qos.arp.priority_level",
        "slice.0.session.1.pcc_rule.0.qos.index",
    ):
        assert _count(core, {"imsi": SYNTHETIC_IMSI, path: {"$type": "int"}}) == 1, path
    assert _count(core, {"imsi": SYNTHETIC_IMSI, "msisdn.0": {"$type": "string"}}) == 1
    assert _count(core, {"imsi": SYNTHETIC_IMSI, "slice.0.session.1.ue": {"$exists": True}}) == 0


def test_reactivating_never_touches_what_the_hss_wrote(core: Database[Any]) -> None:
    from bson import Int64

    repo = MongoSubscriberRepository(core)
    _activate(repo)
    core["subscribers"].update_one(
        {"imsi": SYNTHETIC_IMSI},
        {
            "$set": {
                "security.sqn": Int64(123456789012345),
                "imeisv": ["3540000000000001"],
                "mme_host": ["mme.example"],
                "mm_realm": ["realm.example"],
                "mme_timestamp": Int64(1760000000),
                "purge_flag": [{"purged": True}],
            }
        },
    )
    assert _activate(repo, download=25, voice=False) is False  # an update, not a create
    doc = core["subscribers"].find_one({"imsi": SYNTHETIC_IMSI})
    assert doc is not None
    assert doc["security"]["sqn"] == 123456789012345
    assert _count(core, {"imsi": SYNTHETIC_IMSI, "security.sqn": {"$type": "long"}}) == 1
    assert doc["imeisv"] == ["3540000000000001"] and doc["mme_host"] == ["mme.example"]
    assert doc["mm_realm"] == ["realm.example"] and doc["purge_flag"] == [{"purged": True}]
    assert _count(core, {"imsi": SYNTHETIC_IMSI, "mme_timestamp": {"$type": "long"}}) == 1
    # ... while the fields RatelLink owns did change
    assert doc["ambr"]["downlink"] == {"value": 25, "unit": 2}
    assert [s["name"] for s in doc["slice"][0]["session"]] == ["internet"]


def test_fields_nobody_asked_about_are_left_alone(core: Database[Any]) -> None:
    repo = MongoSubscriberRepository(core)
    core["subscribers"].insert_one({"imsi": SYNTHETIC_IMSI, "custom": {"note": "keep"}, "__v": 7})
    assert _activate(repo) is False
    doc = core["subscribers"].find_one({"imsi": SYNTHETIC_IMSI})
    assert doc is not None and doc["custom"] == {"note": "keep"} and doc["__v"] == 7


def test_one_activation_leaves_exactly_one_document_even_when_repeated(core: Database[Any]) -> None:
    repo = MongoSubscriberRepository(core)
    assert [_activate(repo) for _ in range(3)] == [True, False, False]
    assert _count(core, {}) == 1


def test_simultaneous_first_activations_of_one_line_make_one_document(core: Database[Any]) -> None:
    repo = MongoSubscriberRepository(core)
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: _activate(repo), range(48)))
    assert _count(core, {"imsi": SYNTHETIC_IMSI}) == 1
    assert results.count(True) == 1


def test_two_lines_do_not_affect_each_other(core: Database[Any]) -> None:
    repo = MongoSubscriberRepository(core)
    _activate(repo, SYNTHETIC_IMSI)
    _activate(repo, SYNTHETIC_IMSI_2, voice=False)
    repo.remove_internet(SYNTHETIC_IMSI)
    other = core["subscribers"].find_one({"imsi": SYNTHETIC_IMSI_2})
    assert other is not None and [s["name"] for s in other["slice"][0]["session"]] == ["internet"]


def test_removing_a_line_deletes_its_document_and_only_its_document(core: Database[Any]) -> None:
    repo = MongoSubscriberRepository(core)
    _activate(repo, SYNTHETIC_IMSI)
    _activate(repo, SYNTHETIC_IMSI_2)
    assert repo.remove_line(SYNTHETIC_IMSI) is True
    assert _count(core, {"imsi": SYNTHETIC_IMSI}) == 0
    assert _count(core, {"imsi": SYNTHETIC_IMSI_2}) == 1
    assert repo.remove_line(SYNTHETIC_IMSI) is False  # again: nothing to delete, no error
    assert subscriber_index_missing(core) is False  # the unique index is not touched


def test_a_line_activated_again_after_removal_gets_a_fresh_document(core: Database[Any]) -> None:
    from bson import Int64

    repo = MongoSubscriberRepository(core)
    _activate(repo)
    core["subscribers"].update_one(
        {"imsi": SYNTHETIC_IMSI}, {"$set": {"security.sqn": Int64(99), "imeisv": ["35"]}}
    )
    repo.remove_line(SYNTHETIC_IMSI)
    assert _activate(repo) is True  # created, not updated
    doc = core["subscribers"].find_one({"imsi": SYNTHETIC_IMSI})
    assert doc is not None
    # What the HSS had written is gone with the old document (see line_deactivation.py).
    assert "sqn" not in doc["security"] and doc["imeisv"] == []
    assert _names(core) == ["internet", "ims"]


def _names(core: Database[Any], imsi: str = SYNTHETIC_IMSI) -> list[str]:
    doc = core["subscribers"].find_one({"imsi": imsi})
    assert doc is not None
    return [s["name"] for s in doc["slice"][0]["session"]]


def test_data_off_removes_only_internet_and_on_puts_it_back_first(core: Database[Any]) -> None:
    repo = MongoSubscriberRepository(core)
    _activate(repo)
    voice_before = core["subscribers"].find_one({"imsi": SYNTHETIC_IMSI})["slice"][0]["session"][1]
    assert repo.remove_internet(SYNTHETIC_IMSI) is True
    assert _names(core) == ["ims"]
    assert repo.remove_internet(SYNTHETIC_IMSI) is True  # again: harmless
    assert _names(core) == ["ims"]

    ambr = ambr_document(speed_from_mbps(2), speed_from_mbps(4))
    assert repo.set_internet_speeds(SYNTHETIC_IMSI, ambr, internet_session(ambr, "10.45.0.2"))
    assert _names(core) == ["internet", "ims"]
    doc = core["subscribers"].find_one({"imsi": SYNTHETIC_IMSI})
    assert doc is not None
    assert doc["slice"][0]["session"][1] == voice_before  # calling untouched throughout
    assert doc["slice"][0]["session"][0]["ue"] == {"ipv4": "10.45.0.2"}


def test_changing_the_speed_changes_only_the_internet_session_and_the_top_level(
    core: Database[Any],
) -> None:
    repo = MongoSubscriberRepository(core)
    _activate(repo)
    before = core["subscribers"].find_one({"imsi": SYNTHETIC_IMSI})
    assert before is not None
    ambr = ambr_document(speed_from_mbps(0.128), speed_from_mbps(0.256))
    assert repo.set_internet_speeds(SYNTHETIC_IMSI, ambr, internet_session(ambr, "10.45.0.2"))
    after = core["subscribers"].find_one({"imsi": SYNTHETIC_IMSI})
    assert after is not None
    assert after["slice"][0]["session"][0]["ambr"] == ambr and after["ambr"] == ambr
    assert after["slice"][0]["session"][1] == before["slice"][0]["session"][1]
    assert _names(core) == ["internet", "ims"]  # no second internet session was added
    assert _count(core, {"imsi": SYNTHETIC_IMSI, "slice.0.session.0.ambr.downlink.unit": 1}) == 1


def test_data_changes_on_a_missing_document_report_false_and_create_nothing(
    core: Database[Any],
) -> None:
    repo = MongoSubscriberRepository(core)
    ambr = ambr_document(speed_from_mbps(1), speed_from_mbps(1))
    assert (
        repo.set_internet_speeds(SYNTHETIC_IMSI, ambr, internet_session(ambr, "10.45.0.2")) is False
    )
    assert repo.remove_internet(SYNTHETIC_IMSI) is False
    assert _count(core, {}) == 0


def test_simultaneous_speed_changes_never_duplicate_the_internet_session(
    core: Database[Any],
) -> None:
    repo = MongoSubscriberRepository(core)
    _activate(repo)
    repo.remove_internet(SYNTHETIC_IMSI)

    def change(n: int) -> bool:
        ambr = ambr_document(speed_from_mbps(1 + n % 5), speed_from_mbps(2))
        return repo.set_internet_speeds(SYNTHETIC_IMSI, ambr, internet_session(ambr, "10.45.0.2"))

    with ThreadPoolExecutor(max_workers=16) as pool:
        assert all(pool.map(change, range(48)))
    assert _names(core).count("internet") == 1
    assert _names(core)[0] == "internet"


# --- activate and data over HTTP against real MongoDB -----------------------------------------


def test_activate_and_data_over_http_against_mongodb(
    database: Database[Any], core: Database[Any], tmp_path: Any
) -> None:
    import json as _json

    from fastapi.testclient import TestClient

    from ratel_link.main import create_app

    ensure_indexes(database)
    template = tmp_path / "ims.json"
    template.write_text(_json.dumps({"slice": [{"session": [SYNTHETIC_IMS_SESSION]}]}))
    settings = Settings(
        mongo_uri=SecretStr(os.environ["RATEL_TEST_MONGO_URI"]),
        ratel_link_db_name=database.name,
        open5gs_db_name=core.name,
        ratel_link_voice_template_file=template,
    )
    token = create_system(
        MongoApiKeyRepository(database), "bss-app", "RatelBSS", utc_now(), KeyPolicy()
    )
    client = TestClient(create_app(settings, key_provider=StaticKeyProvider()))
    headers = {"Authorization": f"Bearer {token}"}
    activate = f"/v1/lines/{SYNTHETIC_IMSI}/activate"
    body = {"msisdn": SYNTHETIC_MSISDN, "speed_ul_mbps": 5, "speed_dl_mbps": 10, "voice": True}

    assert client.post(activate, json=body, headers=headers).status_code == 404  # no SIM yet
    imported = {"imsi": SYNTHETIC_IMSI, "ki": HEX_KI, "opc": HEX_OPC}
    assert client.post("/v1/sims", json=imported, headers=headers).status_code == 200
    assert client.post(activate, json=body, headers=headers).status_code == 200
    assert client.post(activate, json=body, headers=headers).status_code == 200  # repeat
    assert _count(core, {}) == 1 and _names(core) == ["internet", "ims"]

    line = client.get(f"/v1/lines/{SYNTHETIC_IMSI}", headers=headers).json()
    assert (
        line["status"] == "active"
        and line["ue_ip"] == "10.45.0.2"
        and line["apns"]
        == [
            "internet",
            "ims",
        ]
    )
    data = f"/v1/lines/{SYNTHETIC_IMSI}/data"
    assert client.post(data, json={"mode": "off"}, headers=headers).status_code == 200
    assert _names(core) == ["ims"]
    on = {"mode": "full", "speed_ul_mbps": 5, "speed_dl_mbps": 10}
    assert client.post(data, json=on, headers=headers).status_code == 200
    assert _names(core) == ["internet", "ims"]
    assigned = client.get("/v1/assignments", headers=headers).json()["assignments"]
    assert assigned == [{"ue_ip": "10.45.0.2", "imsi": SYNTHETIC_IMSI}]

    # the audit log has the changes, with the calling system and no key
    actions = [e["action"] for e in database["audit_log"].find({}).sort("at", 1)]
    assert actions == ["sim.import", "line.activate", "line.data", "line.data"]
    assert HEX_KI not in _json.dumps(list(database["audit_log"].find({})), default=str)
    assert HEX_KI not in _json.dumps(list(database["line_state"].find({})), default=str)
    assert client.post(activate, json=body).status_code == 401
    assert _count(core, {}) == 1


def test_startup_reports_a_missing_subscriber_index_and_voice_template(
    database: Database[Any], caplog: pytest.LogCaptureFixture
) -> None:
    from fastapi.testclient import TestClient

    from ratel_link.main import create_app

    ensure_indexes(database)
    absent = f"open5gs_absent_{secrets.token_hex(3)}"
    settings = Settings(
        mongo_uri=SecretStr(os.environ["RATEL_TEST_MONGO_URI"]),
        ratel_link_db_name=database.name,
        open5gs_db_name=absent,
    )
    caplog.set_level(logging.INFO)
    try:
        with TestClient(create_app(settings, key_provider=StaticKeyProvider())):
            pass
        events = {r.__dict__.get("event") for r in caplog.records}
        assert "startup.subscribers.index.missing" in events
        assert "startup.voice.template.not_configured" in events
        assert absent not in database.client.list_database_names()  # looking created nothing
    finally:
        database.client.drop_database(absent)
