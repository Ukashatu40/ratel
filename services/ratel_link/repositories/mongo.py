"""RatelLink's MongoDB access: the implementations of repositories/ports.py.

Only this module talks to pymongo for RatelLink's own `ratel_link` database. Services depend on
the ports, so tests use in-memory fakes and these classes are covered by integration tests.
"""

from __future__ import annotations

import logging
from typing import Any

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from ratel_link.config import Settings
from ratel_link.domain.api_keys import ApiKeyRecord
from ratel_link.domain.audit import AuditEntry
from ratel_link.domain.sim_keys import SimKeyDocument

SIM_KEY = "sim_key"


API_KEY = "api_key"


AUDIT_LOG = "audit_log"


# Collection -> field that must be unique. Created by `admin_cli init-db`, checked at startup.
UNIQUE_INDEXES: dict[str, str] = {SIM_KEY: "imsi", API_KEY: "api_key_id"}


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
    for collection, field in UNIQUE_INDEXES.items():
        database[collection].create_index([(field, ASCENDING)], unique=True)
    return [f"{c}.{f}" for c, f in UNIQUE_INDEXES.items()]


def missing_indexes(database: Database[Any]) -> list[str]:
    """'collection.field' for each required unique index that does not exist."""
    missing = []
    for collection, field in UNIQUE_INDEXES.items():
        existing = database[collection].index_information().values()
        wanted = [(field, ASCENDING)]
        if not any(i.get("unique") and list(i["key"]) == wanted for i in existing):
            missing.append(f"{collection}.{field}")
    return missing


class MongoSimKeyRepository:
    def __init__(self, database: Database[Any]) -> None:
        self._collection = database[SIM_KEY]

    def insert_if_absent(self, document: SimKeyDocument) -> bool:
        # One atomic upsert, so a repeat import never creates a second document even if the
        # unique index has not been created yet. With the index, a concurrent race raises below.
        try:
            result = self._collection.update_one(
                {"imsi": document["imsi"]}, {"$setOnInsert": dict(document)}, upsert=True
            )
        except DuplicateKeyError:
            return False
        return result.upserted_id is not None

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
