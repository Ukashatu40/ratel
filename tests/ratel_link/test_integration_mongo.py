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
from typing import Any

import pytest
from pydantic import SecretStr
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from common.timeutil import utc_now
from ratel_link import admin_cli
from ratel_link.audit import AuditLog
from ratel_link.auth import ApiPrincipal, KeyPolicy, authenticate, create_system, revoke, rotate
from ratel_link.config import Settings
from ratel_link.crypto import DecryptionError
from ratel_link.models import ApiKeyRecord
from ratel_link.repositories import (
    MongoApiKeyRepository,
    MongoAuditLogRepository,
    MongoSimKeyRepository,
    ensure_indexes,
    missing_indexes,
    open_database,
)
from ratel_link.sim_keys import SimKeyStore
from tests.ratel_link.fakes import StaticKeyProvider
from tests.synthetic import (
    SYNTHETIC_IMSI,
    SYNTHETIC_IMSI_2,
    SYNTHETIC_KI_HEX,
    SYNTHETIC_OPC_HEX,
)

pytestmark = pytest.mark.integration

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


def _store(database: Database[Any]) -> SimKeyStore:
    return SimKeyStore(MongoSimKeyRepository(database), StaticKeyProvider())


def test_indexes_are_created_idempotently(database: Database[Any]) -> None:
    both = ["sim_key.imsi", "api_key.api_key_id"]
    assert missing_indexes(database) == both
    assert ensure_indexes(database) == both
    assert missing_indexes(database) == []
    ensure_indexes(database)  # second run changes nothing and does not fail
    assert missing_indexes(database) == []


def test_a_non_unique_index_does_not_count_as_the_required_one(database: Database[Any]) -> None:
    database["sim_key"].create_index("imsi")  # same field, not unique
    assert missing_indexes(database) == ["sim_key.imsi", "api_key.api_key_id"]


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
    assert event.__dict__["indexes"] == ["sim_key.imsi", "api_key.api_key_id"]
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
