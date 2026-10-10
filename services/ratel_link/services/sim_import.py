"""Import a SIM's keys (POST /v1/sims): store them encrypted, once, and audit the change.

An IMSI that already has keys is never overwritten (docs/DECISIONS_PENDING.md, decided 2026-10-10):
the same keys again is a no-op, different keys is a conflict. Operational logs carry the outcome and
the calling system, never the IMSI or a key.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from pydantic import SecretStr

from common.logging import log_event
from ratel_link.services.audit_log import AuditLog
from ratel_link.services.sim_keys import SimKeyStore

log = logging.getLogger("ratel.link.sims")


class ImportOutcome(StrEnum):
    CREATED = "created"
    UNCHANGED = "unchanged"


class SimKeysConflictError(Exception):
    """The IMSI already has different keys. The message never contains a value."""

    def __init__(self) -> None:
        super().__init__("SIM keys are already stored for this IMSI with different values")


class SimImportService:
    def __init__(self, store: SimKeyStore, audit: AuditLog) -> None:
        self._store = store
        self._audit = audit

    def import_sim(
        self, imsi: str, ki: SecretStr, opc: SecretStr, api_key_id: str
    ) -> ImportOutcome:
        if self._store.put_if_absent(imsi, ki, opc):
            # Stored first, then audited. MongoDB without a replica set has no transaction, so a
            # failure here leaves keys stored without an entry and the caller sees an error.
            # The audit entry holds no key: only that the SIM now exists, without service.
            self._audit.append("sim.import", imsi, None, {"status": "provisioned"}, api_key_id)
            log_event(log, logging.INFO, "sim.import.created", api_key_id=api_key_id)
            return ImportOutcome.CREATED
        if self._store.has_same_keys(imsi, ki, opc):
            log_event(log, logging.INFO, "sim.import.unchanged", api_key_id=api_key_id)
            return ImportOutcome.UNCHANGED
        log_event(log, logging.WARNING, "sim.import.conflict", api_key_id=api_key_id)
        raise SimKeysConflictError
