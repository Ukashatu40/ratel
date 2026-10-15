"""RatelLink works with exactly the MongoDB privileges deploy/core-cp/mongo/ratel-link-roles.json
grants, and those privileges stop it from doing anything else.

The roles file is applied here the same way create-ratel-link-user.js applies it. Run with a real
MongoDB that has authentication on (the compose and CI MongoDB do): RATEL_TEST_MONGO_URI is an
administrator connection string. Everything is created under random names and removed afterwards.
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pymongo import MongoClient
from pymongo.errors import OperationFailure

from common.timeutil import utc_now
from ratel_link.config import Settings
from ratel_link.main import create_app
from ratel_link.repositories.mongo import (
    MongoApiKeyRepository,
    ensure_indexes,
    missing_indexes,
    open_database,
    subscriber_index_missing,
)
from ratel_link.services.api_key_admin import KeyPolicy, create_system
from tests.ratel_link.fakes import StaticKeyProvider
from tests.synthetic import (
    SYNTHETIC_IMS_SESSION,
    SYNTHETIC_IMSI,
    SYNTHETIC_KI_HEX,
    SYNTHETIC_MSISDN,
    SYNTHETIC_OPC_HEX,
)

pytestmark = pytest.mark.integration

ROLES_FILE = Path(__file__).resolve().parents[3] / "deploy/core-cp/mongo/ratel-link-roles.json"


class Setup:
    def __init__(self, admin: MongoClient[Any], admin_uri: str) -> None:
        token = secrets.token_hex(4)
        self.ratel_db, self.core_db = f"rl_roles_{token}", f"core_roles_{token}"
        self.suffix, self.user = f"_{token}", f"rl_user_{token}"
        self.password = secrets.token_urlsafe(24)
        self.admin, self.admin_uri = admin, admin_uri

    def roles(self) -> list[dict[str, Any]]:
        text = ROLES_FILE.read_text()
        for key, value in (
            ("RATEL_DB", self.ratel_db),
            ("CORE_DB", self.core_db),
            ("SUFFIX", self.suffix),
        ):
            text = text.replace("{{" + key + "}}", value)
        return json.loads(text)["roles"]  # type: ignore[no-any-return]

    def create(self) -> None:
        admin_db = self.admin["admin"]
        names = []
        for role in self.roles():
            admin_db.command("createRole", role["role"], privileges=role["privileges"], roles=[])
            names.append({"role": role["role"], "db": "admin"})
        admin_db.command("createUser", self.user, pwd=self.password, roles=names)
        # The stand-in for the core's database has the unique index Open5GS's tooling creates.
        self.admin[self.core_db]["subscribers"].create_index("imsi", unique=True)

    def drop(self) -> None:
        admin_db = self.admin["admin"]
        admin_db.command("dropUser", self.user)
        for role in self.roles():
            admin_db.command("dropRole", role["role"])
        self.admin.drop_database(self.ratel_db)
        self.admin.drop_database(self.core_db)

    def user_uri(self) -> str:
        parts = urlsplit(self.admin_uri)
        host = parts.netloc.rsplit("@", 1)[-1]
        netloc = f"{quote(self.user)}:{quote(self.password)}@{host}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


@pytest.fixture
def restricted() -> Iterator[Setup]:
    uri = os.environ.get("RATEL_TEST_MONGO_URI")
    if not uri:
        pytest.skip("RATEL_TEST_MONGO_URI is not set")
    admin: MongoClient[Any] = MongoClient(uri, serverSelectionTimeoutMS=5000)
    setup = Setup(admin, uri)
    setup.create()
    try:
        yield setup
    finally:
        setup.drop()
        admin.close()


def _client(setup: Setup) -> MongoClient[Any]:
    return MongoClient(setup.user_uri(), serverSelectionTimeoutMS=5000, tz_aware=True)


def _settings(setup: Setup, template: Path | None = None) -> Settings:
    return Settings(
        mongo_uri=SecretStr(setup.user_uri()),
        ratel_link_db_name=setup.ratel_db,
        open5gs_db_name=setup.core_db,
        ratel_link_voice_template_file=template,
    )


def test_ratellink_does_all_its_work_with_only_these_privileges(
    restricted: Setup, tmp_path: Path
) -> None:
    """Index creation, API key creation, SIM import, activation, data changes, audit, reads."""
    template = tmp_path / "ims.json"
    template.write_text(json.dumps({"slice": [{"session": [SYNTHETIC_IMS_SESSION]}]}))
    settings = _settings(restricted, template)

    database = open_database(settings)
    try:
        assert ensure_indexes(database)  # init-db, as the service user
        assert missing_indexes(database) == []
        assert subscriber_index_missing(database.client[restricted.core_db]) is False
        token = create_system(
            MongoApiKeyRepository(database), "bss-app", "RatelBSS", utc_now(), KeyPolicy()
        )
    finally:
        database.client.close()

    app = create_app(settings, key_provider=StaticKeyProvider())
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = {"Authorization": f"Bearer {token}"}
        keys = {"imsi": SYNTHETIC_IMSI, "ki": SYNTHETIC_KI_HEX, "opc": SYNTHETIC_OPC_HEX}
        assert client.post("/v1/sims", json=keys, headers=headers).status_code == 200
        assert client.post("/v1/sims", json=keys, headers=headers).status_code == 200  # unchanged
        different = {**keys, "ki": SYNTHETIC_OPC_HEX}
        assert client.post("/v1/sims", json=different, headers=headers).status_code == 409
        body = {"msisdn": SYNTHETIC_MSISDN, "speed_ul_mbps": 5, "speed_dl_mbps": 10, "voice": True}
        path = f"/v1/lines/{SYNTHETIC_IMSI}"
        assert client.post(path + "/activate", json=body, headers=headers).status_code == 200
        assert client.post(path + "/activate", json=body, headers=headers).status_code == 200
        off = client.post(path + "/data", json={"mode": "off"}, headers=headers)
        assert off.status_code == 200
        on = {"mode": "full", "speed_ul_mbps": 5, "speed_dl_mbps": 10}
        assert client.post(path + "/data", json=on, headers=headers).status_code == 200
        assert client.get(path, headers=headers).json()["status"] == "active"
        assigned = client.get("/v1/assignments", headers=headers).json()["assignments"]
        assert [a["imsi"] for a in assigned] == [SYNTHETIC_IMSI]

        # Deactivating deletes the core's document: the one delete the user may do.
        subscribers = restricted.admin[restricted.core_db]["subscribers"]
        assert subscribers.count_documents({}) == 1
        stop = client.post(path + "/deactivate", json={"reason": "test"}, headers=headers)
        assert stop.status_code == 200
        assert subscribers.count_documents({}) == 0
        assert client.get(path, headers=headers).json()["status"] == "provisioned"
        assert client.post(path + "/activate", json=body, headers=headers).status_code == 200

    admin_view = restricted.admin
    assert admin_view[restricted.core_db]["subscribers"].count_documents({}) == 1
    actions = [e["action"] for e in admin_view[restricted.ratel_db]["audit_log"].find({})]
    assert sorted(actions) == sorted(
        [
            "sim.import",
            "line.activate",
            "line.data",
            "line.data",
            "line.deactivate",
            "line.activate",
        ]
    )


NEW_USER = {"pwd": "z" * 20, "roles": []}

# (what the user must not do, which database, collection or None, method, arguments, keywords)
FORBIDDEN: list[tuple[str, str, str | None, str, tuple[Any, ...], dict[str, Any]]] = [
    ("change a stored SIM key", "ratel", "sim_key", "update_one", ({}, {"$set": {"a": 1}}), {}),
    ("delete a stored SIM key", "ratel", "sim_key", "delete_many", ({},), {}),
    ("read an audit entry", "ratel", "audit_log", "find_one", (), {}),
    ("change an audit entry", "ratel", "audit_log", "update_many", ({}, {"$set": {"a": 1}}), {}),
    ("delete an audit entry", "ratel", "audit_log", "delete_many", ({},), {}),
    ("delete an API key", "ratel", "api_key", "delete_many", ({},), {}),
    ("delete a line's state", "ratel", "line_state", "delete_many", ({},), {}),
    ("delete an address record", "ratel", "ip_allocation", "delete_many", ({},), {}),
    ("drop a collection", "ratel", None, "drop_collection", ("sim_key",), {}),
    ("create a collection of its own", "ratel", None, "create_collection", ("extra",), {}),
    ("create an index in the core", "core", "subscribers", "create_index", ("msisdn",), {}),
    ("drop the core's subscribers", "core", None, "drop_collection", ("subscribers",), {}),
    ("read another core collection", "core", "other", "find_one", (), {}),
    ("write another core collection", "core", "other", "insert_one", ({"a": 1},), {}),
    ("read another database", "admin", "system.users", "find_one", (), {}),
    ("create a user", "admin", None, "command", ("createUser", "x"), NEW_USER),
]  # fmt: skip


@pytest.mark.parametrize(
    ("what", "where", "collection", "method", "args", "kwargs"),
    FORBIDDEN,
    ids=[row[0] for row in FORBIDDEN],
)
def test_the_user_cannot(
    what: str,
    where: str,
    collection: str | None,
    method: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    restricted: Setup,
) -> None:
    client = _client(restricted)
    try:
        database = client[
            {"ratel": restricted.ratel_db, "core": restricted.core_db}.get(where, where)
        ]
        target = database if collection is None else database[collection]
        with pytest.raises(OperationFailure) as caught:
            getattr(target, method)(*args, **kwargs)
        assert caught.value.code == 13, what  # 13 is Unauthorized
    finally:
        client.close()


def test_the_roles_file_names_nothing_but_the_collections_ratellink_uses() -> None:
    spec = json.loads(ROLES_FILE.read_text())
    granted = {
        (p["resource"]["db"], p["resource"]["collection"])
        for r in spec["roles"]
        for p in r["privileges"]
    }
    assert granted == {
        ("{{RATEL_DB}}", "sim_key"),
        ("{{RATEL_DB}}", "api_key"),
        ("{{RATEL_DB}}", "ip_allocation"),
        ("{{RATEL_DB}}", "line_state"),
        ("{{RATEL_DB}}", "audit_log"),
        ("{{CORE_DB}}", "subscribers"),
    }
    for role in spec["roles"]:
        for privilege in role["privileges"]:
            # Deleting is allowed in one place only: a deactivated line's subscriber document.
            may_delete = privilege["resource"]["collection"] == "subscribers"
            assert ("remove" in privilege["actions"]) == may_delete
            assert set(privilege["actions"]) <= {
                "find",
                "insert",
                "update",
                "remove",
                "createIndex",
                "listIndexes",
            }
