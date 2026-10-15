"""What the services need from storage, as interfaces. No database code here.

The MongoDB implementations are in mongo.py; tests use in-memory fakes (tests/ratel_link/fakes.py).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol

from ratel_link.domain.api_keys import ApiKeyRecord
from ratel_link.domain.audit import AuditEntry
from ratel_link.domain.ip_pool import IpAllocation
from ratel_link.domain.line_state import LineState
from ratel_link.domain.sim_keys import SimKeyDocument


class SimKeyRepository(Protocol):
    def insert_if_absent(self, document: SimKeyDocument) -> bool:
        """Store the document unless its IMSI exists. True if stored, False if already there."""
        ...

    def get(self, imsi: str) -> SimKeyDocument | None: ...

    def exists(self, imsi: str) -> bool:
        """Whether keys are stored for this IMSI, without reading them."""
        ...


class ApiKeyRepository(Protocol):
    """Calling systems and their keys. Systems are never deleted: audit records cite them."""

    def get(self, api_key_id: str) -> ApiKeyRecord | None: ...

    def list_all(self) -> list[ApiKeyRecord]: ...

    def insert(self, record: ApiKeyRecord) -> bool:
        """False if a system with this id already exists."""
        ...

    def replace(self, record: ApiKeyRecord) -> None:
        """Overwrite an existing system. Raises KeyError if it does not exist.

        Not safe against two operators changing the same system at the same moment. Key
        administration is a rare, single-operator task (admin_cli).
        """
        ...


class AuditLogRepository(Protocol):
    """Append-only: insert is the only operation. There is deliberately no update or delete."""

    def insert(self, entry: AuditEntry) -> None: ...


class IpAllocationRepository(Protocol):
    """Who holds which address. Each claim is one atomic step, so two activations at the same
    moment can never be given the same address."""

    def find_by_imsi(self, imsi: str) -> IpAllocation | None:
        """The address this line holds, or held most recently. At most one per line."""
        ...

    def unavailable(self, hold_cutoff: datetime) -> set[str]:
        """Addresses in use, plus those released after `hold_cutoff` (still on hold)."""
        ...

    def claim_free(self, ue_ip: str, imsi: str, now: datetime, hold_cutoff: datetime) -> bool:
        """Take an address that was never used, or was released at or before `hold_cutoff`.

        False if it is taken, on hold, or this line already holds another address.
        """
        ...

    def reclaim(self, ue_ip: str, imsi: str, now: datetime) -> bool:
        """Take back this line's own released address. False if it is no longer this line's."""
        ...

    def release(self, imsi: str, now: datetime) -> bool:
        """Release the line's address. False if it had no active address."""
        ...

    def list_current(self, hold_cutoff: datetime) -> list[IpAllocation]:
        """Addresses in use, plus those released after `hold_cutoff` (still theirs)."""
        ...


class LineStateRepository(Protocol):
    """What RatelLink last wrote to RatelCore for each line. One record per line."""

    def get(self, imsi: str) -> LineState | None: ...

    def put(self, state: LineState) -> None:
        """Insert or replace the line's record."""
        ...


class SubscriberRepository(Protocol):
    """RatelCore's `subscribers` collection (Open5GS). RatelLink is its only writer.

    Every method changes named fields only. None replaces a document, because the HSS writes
    fields of its own into it (`sqn`, `imeisv`, `mme_host`, `mm_realm`, `mme_timestamp`,
    `purge_flag`).
    """

    def upsert_line(
        self, imsi: str, owned: Mapping[str, Any], created_only: Mapping[str, Any]
    ) -> bool:
        """Create the document if absent, otherwise set only `owned`. True if it was created."""
        ...

    def set_internet_speeds(
        self, imsi: str, ambr: Mapping[str, Any], session_if_absent: Mapping[str, Any]
    ) -> bool:
        """Set the speed of the internet session, or insert it at position 0 if it is not there.

        False if the line has no subscriber document.
        """
        ...

    def remove_internet(self, imsi: str) -> bool:
        """Remove the internet session and leave the ims session. False if there is no document."""
        ...


class VoiceTemplateSource(Protocol):
    def ims_session(self) -> dict[str, Any] | None:
        """A copy of the lab's ims session, or None if no template is configured."""
        ...
