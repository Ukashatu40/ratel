"""Importing a SIM: stored once, audited once, never overwritten (decided 2026-10-10)."""

import json
import logging

import pytest
from pydantic import SecretStr

from ratel_link.domain.audit import AuditEntry
from ratel_link.security.key_provider import KeyUnavailableError, NoKeyProvider
from ratel_link.services.audit_log import AuditLog
from ratel_link.services.sim_import import ImportOutcome, SimImportService, SimKeysConflictError
from ratel_link.services.sim_keys import SimKeyStore
from tests.ratel_link.fakes import (
    FakeClock,
    InMemoryAuditLogRepository,
    InMemorySimKeyRepository,
    StaticKeyProvider,
)
from tests.synthetic import SYNTHETIC_IMSI, SYNTHETIC_KI_HEX, SYNTHETIC_OPC_HEX

KI = SecretStr(SYNTHETIC_KI_HEX)
OPC = SecretStr(SYNTHETIC_OPC_HEX)
OTHER = SecretStr("0f0e0d0c0b0a09080706050403020100")


class Setup:
    def __init__(self, provider: object | None = None) -> None:
        self.keys = InMemorySimKeyRepository()
        self.audit = InMemoryAuditLogRepository()
        clock = FakeClock()
        store = SimKeyStore(self.keys, provider or StaticKeyProvider(), clock)  # type: ignore[arg-type]
        self.service = SimImportService(store, AuditLog(self.audit, clock))


def test_a_new_sim_is_stored_and_audited_once() -> None:
    s = Setup()
    assert s.service.import_sim(SYNTHETIC_IMSI, KI, OPC, "bss-app") is ImportOutcome.CREATED
    assert list(s.keys.documents) == [SYNTHETIC_IMSI]
    (entry,) = s.audit.entries
    assert entry["action"] == "sim.import"
    assert entry["imsi"] == SYNTHETIC_IMSI
    assert entry["api_key_id"] == "bss-app"
    assert entry["before"] is None
    assert entry["after"] == {"status": "provisioned"}


def test_the_audit_entry_holds_no_key() -> None:
    s = Setup()
    s.service.import_sim(SYNTHETIC_IMSI, KI, OPC, "bss-app")
    text = json.dumps(s.audit.entries, default=str)
    assert SYNTHETIC_KI_HEX not in text and SYNTHETIC_OPC_HEX not in text


def test_the_same_keys_again_change_nothing_and_add_no_audit_entry() -> None:
    s = Setup()
    s.service.import_sim(SYNTHETIC_IMSI, KI, OPC, "bss-app")
    stored = json.dumps(s.keys.documents, default=str)
    assert s.service.import_sim(SYNTHETIC_IMSI, KI, OPC, "bss-app") is ImportOutcome.UNCHANGED
    assert json.dumps(s.keys.documents, default=str) == stored
    assert len(s.audit.entries) == 1


def test_different_keys_conflict_and_nothing_is_overwritten_or_audited() -> None:
    s = Setup()
    s.service.import_sim(SYNTHETIC_IMSI, KI, OPC, "bss-app")
    stored = json.dumps(s.keys.documents, default=str)
    for ki, opc in ((OTHER, OPC), (KI, OTHER), (OTHER, OTHER)):
        with pytest.raises(SimKeysConflictError) as exc:
            s.service.import_sim(SYNTHETIC_IMSI, ki, opc, "bss-app")
        assert SYNTHETIC_KI_HEX not in str(exc.value) and OTHER.get_secret_value() not in str(
            exc.value
        )
    assert json.dumps(s.keys.documents, default=str) == stored
    assert len(s.audit.entries) == 1


def test_no_encryption_key_stores_and_audits_nothing() -> None:
    s = Setup(NoKeyProvider())
    with pytest.raises(KeyUnavailableError):
        s.service.import_sim(SYNTHETIC_IMSI, KI, OPC, "bss-app")
    assert s.keys.documents == {} and s.audit.entries == []


def test_a_failing_audit_write_is_an_error_and_is_a_known_limit() -> None:
    # MongoDB without a replica set has no transaction. The keys are stored, the caller sees an
    # error, and a retry reports "unchanged" without writing the missing audit entry.
    class BrokenAudit(InMemoryAuditLogRepository):
        def insert(self, entry: AuditEntry) -> None:
            raise ConnectionError("audit store down")

    s = Setup()
    s.service = SimImportService(
        SimKeyStore(s.keys, StaticKeyProvider(), FakeClock()), AuditLog(BrokenAudit(), FakeClock())
    )
    with pytest.raises(ConnectionError):
        s.service.import_sim(SYNTHETIC_IMSI, KI, OPC, "bss-app")
    assert SYNTHETIC_IMSI in s.keys.documents
    assert s.service.import_sim(SYNTHETIC_IMSI, KI, OPC, "bss-app") is ImportOutcome.UNCHANGED


def test_operational_logs_name_the_outcome_and_caller_but_never_the_imsi_or_a_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    s = Setup()
    s.service.import_sim(SYNTHETIC_IMSI, KI, OPC, "bss-app")
    s.service.import_sim(SYNTHETIC_IMSI, KI, OPC, "bss-app")
    with pytest.raises(SimKeysConflictError):
        s.service.import_sim(SYNTHETIC_IMSI, OTHER, OPC, "bss-app")
    events = [r.__dict__.get("event") for r in caplog.records]
    assert events == ["sim.import.created", "sim.import.unchanged", "sim.import.conflict"]
    everything = json.dumps([r.__dict__ for r in caplog.records], default=str)
    for secret in (SYNTHETIC_IMSI, SYNTHETIC_KI_HEX, SYNTHETIC_OPC_HEX, OTHER.get_secret_value()):
        assert secret not in everything
