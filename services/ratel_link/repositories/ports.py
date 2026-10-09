"""What the services need from storage, as interfaces. No database code here.

The MongoDB implementations are in mongo.py; tests use in-memory fakes (tests/ratel_link/fakes.py).
"""

from __future__ import annotations

from typing import Protocol

from ratel_link.domain.api_keys import ApiKeyRecord
from ratel_link.domain.audit import AuditEntry
from ratel_link.domain.sim_keys import SimKeyDocument


class SimKeyRepository(Protocol):
    def insert_if_absent(self, document: SimKeyDocument) -> bool:
        """Store the document unless its IMSI exists. True if stored, False if already there."""
        ...

    def get(self, imsi: str) -> SimKeyDocument | None: ...


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
