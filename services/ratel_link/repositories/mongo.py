"""RatelLink's MongoDB access: the implementations of repositories/ports.py.

Only this module talks to pymongo for RatelLink's own `ratel_link` database. Services depend on
the ports, so tests use in-memory fakes and these classes are covered by integration tests.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from ratel_link.config import Settings
from ratel_link.domain.api_keys import ApiKeyRecord
from ratel_link.domain.audit import AuditEntry
from ratel_link.domain.ip_pool import IpAllocation
from ratel_link.domain.line_state import LineState
from ratel_link.domain.sim_keys import SimKeyDocument

SIM_KEY = "sim_key"
API_KEY = "api_key"
AUDIT_LOG = "audit_log"
IP_ALLOCATION = "ip_allocation"
LINE_STATE = "line_state"

# (collection, field) pairs that must be unique. Created by `admin_cli init-db`, checked at startup.
# A line holds at most one address and an address belongs to at most one line.
UNIQUE_INDEXES: list[tuple[str, str]] = [
    (SIM_KEY, "imsi"),
    (API_KEY, "api_key_id"),
    (IP_ALLOCATION, "ue_ip"),
    (IP_ALLOCATION, "imsi"),
    (LINE_STATE, "imsi"),
]


def open_database(settings: Settings) -> Database[Any]:
    """The `ratel_link` database. The client connects lazily, on first use.

    tz_aware makes timestamps come back as UTC datetimes instead of naive ones.
    """
    # At DEBUG the driver logs whole command documents (ciphertext, key hashes). Keep it quiet
    # whatever LOG_LEVEL the service runs at.
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    client: MongoClient[Any] = MongoClient(
        settings.mongo_uri.get_secret_value(),
        tz_aware=True,
        serverSelectionTimeoutMS=5000,
        appname="ratel-link",
    )
    return client[settings.ratel_link_db_name]


def ensure_indexes(database: Database[Any]) -> list[str]:
    """Create the unique indexes. Safe to run again. Returns 'collection.field' for each."""
    for collection, field in UNIQUE_INDEXES:
        database[collection].create_index([(field, ASCENDING)], unique=True)
    return [f"{c}.{f}" for c, f in UNIQUE_INDEXES]


def missing_indexes(database: Database[Any]) -> list[str]:
    """'collection.field' for each required unique index that does not exist."""
    missing = []
    for collection, field in UNIQUE_INDEXES:
        existing = database[collection].index_information().values()
        wanted = [(field, ASCENDING)]
        if not any(i.get("unique") and list(i["key"]) == wanted for i in existing):
            missing.append(f"{collection}.{field}")
    return missing


class MongoSimKeyRepository:
    def __init__(self, database: Database[Any]) -> None:
        self._collection = database[SIM_KEY]

    def insert_if_absent(self, document: SimKeyDocument) -> bool:
        # Insert only, never an update: the database user RatelLink runs as may add a stored key
        # but not change or delete one (deploy/core-cp/mongo/ratel-link-roles.json). The look-up
        # makes a repeat import a no-op even before the unique index exists. When two imports of
        # one IMSI race, the unique index lets exactly one insert succeed.
        if self._collection.find_one({"imsi": document["imsi"]}, {"_id": 1}) is not None:
            return False
        try:
            self._collection.insert_one(dict(document))
        except DuplicateKeyError:
            return False
        return True

    def exists(self, imsi: str) -> bool:
        return self._collection.find_one({"imsi": imsi}, {"_id": 1}) is not None

    def get(self, imsi: str) -> SimKeyDocument | None:
        found: Any = self._collection.find_one({"imsi": imsi}, {"_id": 0})
        return found  # type: ignore[no-any-return]


class MongoApiKeyRepository:
    def __init__(self, database: Database[Any]) -> None:
        self._collection = database[API_KEY]

    def get(self, api_key_id: str) -> ApiKeyRecord | None:
        doc: Any = self._collection.find_one({"api_key_id": api_key_id}, {"_id": 0})
        return None if doc is None else ApiKeyRecord.from_document(doc)

    def list_all(self) -> list[ApiKeyRecord]:
        return [
            ApiKeyRecord.from_document(doc)
            for doc in self._collection.find({}, {"_id": 0}).sort("api_key_id")
        ]

    def insert(self, record: ApiKeyRecord) -> bool:
        try:
            self._collection.insert_one(record.to_document())
        except DuplicateKeyError:
            return False
        return True

    def replace(self, record: ApiKeyRecord) -> None:
        result = self._collection.replace_one(
            {"api_key_id": record.api_key_id}, record.to_document()
        )
        if result.matched_count == 0:
            raise KeyError(record.api_key_id)


class MongoAuditLogRepository:
    def __init__(self, database: Database[Any]) -> None:
        self._collection = database[AUDIT_LOG]

    def insert(self, entry: AuditEntry) -> None:
        self._collection.insert_one(dict(entry))  # a copy: the driver adds an _id to what it gets


class MongoIpAllocationRepository:
    def __init__(self, database: Database[Any]) -> None:
        self._collection = database[IP_ALLOCATION]

    def find_by_imsi(self, imsi: str) -> IpAllocation | None:
        doc: Any = self._collection.find_one({"imsi": imsi}, {"_id": 0})
        return None if doc is None else IpAllocation.from_document(doc)

    def list_current(self, hold_cutoff: datetime) -> list[IpAllocation]:
        held = {"state": "released", "released_at": {"$gt": hold_cutoff}}
        cursor = self._collection.find({"$or": [{"state": "active"}, held]}, {"_id": 0})
        return [IpAllocation.from_document(doc) for doc in cursor]

    def unavailable(self, hold_cutoff: datetime) -> set[str]:
        held = {"state": "released", "released_at": {"$gt": hold_cutoff}}
        cursor = self._collection.find({"$or": [{"state": "active"}, held]}, {"ue_ip": 1, "_id": 0})
        return {doc["ue_ip"] for doc in cursor}

    def claim_free(self, ue_ip: str, imsi: str, now: datetime, hold_cutoff: datetime) -> bool:
        taken = {"imsi": imsi, "state": "active", "allocated_at": now, "released_at": None}
        try:
            # An address released long enough ago is re-used by updating its document in place...
            reused = self._collection.update_one(
                {"ue_ip": ue_ip, "state": "released", "released_at": {"$lte": hold_cutoff}},
                {"$set": taken},
            )
            if reused.modified_count == 1:
                return True
            # ...a never-used one is inserted. The unique indexes make a second claim fail.
            self._collection.insert_one({"ue_ip": ue_ip, **taken})
        except DuplicateKeyError:
            return False
        return True

    def reclaim(self, ue_ip: str, imsi: str, now: datetime) -> bool:
        result = self._collection.update_one(
            {"ue_ip": ue_ip, "imsi": imsi, "state": "released"},
            {"$set": {"state": "active", "allocated_at": now, "released_at": None}},
        )
        return result.modified_count == 1

    def release(self, imsi: str, now: datetime) -> bool:
        result = self._collection.update_one(
            {"imsi": imsi, "state": "active"}, {"$set": {"state": "released", "released_at": now}}
        )
        return result.modified_count == 1


class MongoLineStateRepository:
    def __init__(self, database: Database[Any]) -> None:
        self._collection = database[LINE_STATE]

    def get(self, imsi: str) -> LineState | None:
        doc: Any = self._collection.find_one({"imsi": imsi}, {"_id": 0})
        return None if doc is None else LineState.from_document(doc)

    def put(self, state: LineState) -> None:
        self._collection.replace_one({"imsi": state.imsi}, state.to_document(), upsert=True)


SUBSCRIBERS = "subscribers"
_SESSIONS = "slice.0.session"


class MongoSubscriberRepository:
    """Writes to the Open5GS `subscribers` collection, one atomic operation per change.

    Nothing here replaces a document. Updates name the paths they change (`$set`, `$pull`,
    `$push`), so the fields the HSS writes survive.
    """

    def __init__(self, open5gs_database: Database[Any]) -> None:
        self._collection = open5gs_database[SUBSCRIBERS]

    def upsert_line(
        self, imsi: str, owned: Mapping[str, Any], created_only: Mapping[str, Any]
    ) -> bool:
        # One operation: create with every field if absent, otherwise set only the owned fields.
        # `imsi` comes from the filter. The two field sets share no path.
        result = self._collection.update_one(
            {"imsi": imsi},
            {"$set": dict(owned), "$setOnInsert": dict(created_only)},
            upsert=True,
        )
        return result.upserted_id is not None

    def set_internet_speeds(
        self, imsi: str, ambr: Mapping[str, Any], session_if_absent: Mapping[str, Any]
    ) -> bool:
        has_internet = {"imsi": imsi, f"{_SESSIONS}.name": "internet"}
        no_internet = {"imsi": imsi, f"{_SESSIONS}.name": {"$ne": "internet"}}
        for _ in range(3):  # a second caller may add or remove the session between the two steps
            changed = self._collection.update_one(
                has_internet,
                {"$set": {"ambr": dict(ambr), f"{_SESSIONS}.$[s].ambr": dict(ambr)}},
                array_filters=[{"s.name": "internet"}],
            )
            if changed.matched_count:
                return True
            added = self._collection.update_one(
                no_internet,
                {
                    "$set": {"ambr": dict(ambr)},
                    "$push": {_SESSIONS: {"$each": [dict(session_if_absent)], "$position": 0}},
                },
            )
            if added.matched_count:
                return True
            if self._collection.count_documents({"imsi": imsi}, limit=1) == 0:
                return False
        return False

    def remove_internet(self, imsi: str) -> bool:
        result = self._collection.update_one(
            {"imsi": imsi}, {"$pull": {_SESSIONS: {"name": "internet"}}}
        )
        return result.matched_count == 1


def subscriber_index_missing(open5gs_database: Database[Any]) -> bool:
    """True if `subscribers` has no unique index on `imsi`. Read only: RatelLink never creates one.

    Without it, two activations at the same moment could create two documents for one IMSI.
    """
    try:
        info = open5gs_database[SUBSCRIBERS].index_information()
    except Exception:  # a missing collection is reported as missing too
        return True
    return not any(
        spec.get("unique") and [key for key, _ in spec["key"]] == ["imsi"] for spec in info.values()
    )
