"""In-memory stand-ins for RatelLink's key provider and repositories. Test code only.

Production code never imports this module (tests/architecture enforces it).
"""

from __future__ import annotations

import copy
import os
from datetime import datetime, timedelta
from typing import Any

from common.timeutil import utc_now
from ratel_link.domain.api_keys import ApiKeyRecord
from ratel_link.domain.audit import AuditEntry
from ratel_link.domain.ip_pool import IpAllocation
from ratel_link.domain.sim_keys import SimKeyDocument
from ratel_link.security.key_provider import KEY_BYTES, KeyUnavailableError


class StaticKeyProvider:
    """Holds keys in memory. Keys are random per test run, never committed."""

    def __init__(self, keys: dict[str, bytes] | None = None, current: str = "1") -> None:
        self._keys = keys if keys is not None else {current: os.urandom(KEY_BYTES)}
        self._current = current

    def current_key_id(self) -> str:
        return self._current

    def get_key(self, kid: str) -> bytes:
        try:
            return self._keys[kid]
        except KeyError:
            raise KeyUnavailableError("no key with that id is configured") from None

    def __repr__(self) -> str:
        return f"StaticKeyProvider(key_ids={sorted(self._keys)})"


class FakeClock:
    """A settable UTC clock, so tests move time without sleeping."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or utc_now()

    def __call__(self) -> datetime:
        return self._now

    def advance(self, *, days: int = 0, seconds: int = 0) -> None:
        self._now += timedelta(days=days, seconds=seconds)


class InMemorySimKeyRepository:
    def __init__(self) -> None:
        self.documents: dict[str, SimKeyDocument] = {}

    def insert_if_absent(self, document: SimKeyDocument) -> bool:
        if document["imsi"] in self.documents:
            return False
        self.documents[document["imsi"]] = copy.deepcopy(document)
        return True

    def get(self, imsi: str) -> SimKeyDocument | None:
        found = self.documents.get(imsi)
        return copy.deepcopy(found) if found else None


class InMemoryApiKeyRepository:
    """Stores the same documents MongoDB would, so tests can inspect exactly what is persisted."""

    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}

    def get(self, api_key_id: str) -> ApiKeyRecord | None:
        doc = self.documents.get(api_key_id)
        return None if doc is None else ApiKeyRecord.from_document(copy.deepcopy(doc))

    def list_all(self) -> list[ApiKeyRecord]:
        return [
            ApiKeyRecord.from_document(copy.deepcopy(d)) for _, d in sorted(self.documents.items())
        ]

    def insert(self, record: ApiKeyRecord) -> bool:
        if record.api_key_id in self.documents:
            return False
        self.documents[record.api_key_id] = copy.deepcopy(record.to_document())
        return True

    def replace(self, record: ApiKeyRecord) -> None:
        if record.api_key_id not in self.documents:
            raise KeyError(record.api_key_id)
        self.documents[record.api_key_id] = copy.deepcopy(record.to_document())


class InMemoryAuditLogRepository:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    def insert(self, entry: AuditEntry) -> None:
        self.entries.append(copy.deepcopy(entry))


class InMemoryIpAllocationRepository:
    """Same rules as the MongoDB version: one record per address and per line, each claim atomic."""

    def __init__(self) -> None:
        self.by_ip: dict[str, IpAllocation] = {}
        self.claim_attempts = 0

    def find_by_imsi(self, imsi: str) -> IpAllocation | None:
        return next((a for a in self.by_ip.values() if a.imsi == imsi), None)

    def unavailable(self, hold_cutoff: datetime) -> set[str]:
        return {
            ip
            for ip, a in self.by_ip.items()
            if a.state == "active" or (a.released_at is not None and a.released_at > hold_cutoff)
        }

    def claim_free(self, ue_ip: str, imsi: str, now: datetime, hold_cutoff: datetime) -> bool:
        self.claim_attempts += 1
        if self.find_by_imsi(imsi) is not None:  # a line holds at most one address
            return False
        current = self.by_ip.get(ue_ip)
        if current is not None and not (
            current.state == "released"
            and current.released_at is not None
            and current.released_at <= hold_cutoff
        ):
            return False
        self.by_ip[ue_ip] = IpAllocation(ue_ip, imsi, "active", now)
        return True

    def reclaim(self, ue_ip: str, imsi: str, now: datetime) -> bool:
        current = self.by_ip.get(ue_ip)
        if current is None or current.imsi != imsi or current.state != "released":
            return False
        self.by_ip[ue_ip] = IpAllocation(ue_ip, imsi, "active", now)
        return True

    def release(self, imsi: str, now: datetime) -> bool:
        current = self.find_by_imsi(imsi)
        if current is None or current.state != "active":
            return False
        self.by_ip[current.ue_ip] = IpAllocation(
            current.ue_ip, imsi, "released", current.allocated_at, now
        )
        return True
