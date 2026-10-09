import ast
import json
from datetime import UTC
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from ratel_link.domain.audit import FORBIDDEN_KEYS, AuditContentError
from ratel_link.repositories.mongo import MongoAuditLogRepository
from ratel_link.repositories.ports import AuditLogRepository
from ratel_link.security.crypto import encrypt_field
from ratel_link.services.audit_log import AuditLog
from tests.ratel_link.fakes import (
    FakeClock,
    InMemoryAuditLogRepository,
    StaticKeyProvider,
)
from tests.synthetic import (
    SENTINEL_API_KEY,
    SENTINEL_KI,
    SENTINEL_OPC,
    SYNTHETIC_IMSI,
)

PACKAGE = Path(__file__).resolve().parents[3] / "services" / "ratel_link"


def _log() -> tuple[AuditLog, InMemoryAuditLogRepository, FakeClock]:
    repo, clock = InMemoryAuditLogRepository(), FakeClock()
    return AuditLog(repo, clock), repo, clock


def test_entry_has_exactly_the_build_plan_fields() -> None:
    log, repo, clock = _log()
    before = {"status": "provisioned"}
    after = {"status": "active", "speed_dl_mbps": 10}
    log.append("line.activate", SYNTHETIC_IMSI, before, after, "bss-app")
    (entry,) = repo.entries
    assert set(entry) == {"at", "api_key_id", "action", "imsi", "before", "after"}
    assert entry["api_key_id"] == "bss-app"
    assert entry["action"] == "line.activate"
    assert entry["imsi"] == SYNTHETIC_IMSI
    assert entry["before"] == before and entry["after"] == after
    assert entry["at"] == clock() and entry["at"].tzinfo == UTC


def test_before_and_after_may_be_absent() -> None:
    log, repo, _ = _log()
    log.append("line.create", SYNTHETIC_IMSI, None, {"status": "provisioned"}, "bss-app")
    log.append("line.delete", SYNTHETIC_IMSI, {"status": "active"}, None, "bss-app")
    assert [(e["before"] is None, e["after"] is None) for e in repo.entries] == [
        (True, False),
        (False, True),
    ]


def test_the_entry_cites_the_key_id_never_a_key() -> None:
    log, repo, _ = _log()
    with pytest.raises(ValueError, match="api_key_id"):
        log.append("x", SYNTHETIC_IMSI, None, None, SENTINEL_API_KEY)  # a whole token by mistake
    assert repo.entries == []
    assert SENTINEL_API_KEY not in json.dumps(repo.entries, default=str)


@pytest.mark.parametrize("name", sorted(FORBIDDEN_KEYS))
@pytest.mark.parametrize("side", ["before", "after"])
def test_forbidden_field_names_are_rejected(name: str, side: str) -> None:
    log, repo, _ = _log()
    payload: dict[str, Any] = {"status": "active", name: SENTINEL_KI}
    kwargs = {"before": None, "after": None, side: payload}
    with pytest.raises(AuditContentError) as exc:
        log.append("line.activate", SYNTHETIC_IMSI, kwargs["before"], kwargs["after"], "bss-app")
    assert SENTINEL_KI not in str(exc.value) and SENTINEL_KI not in repr(exc.value)
    assert side in str(exc.value)
    assert repo.entries == []


@pytest.mark.parametrize("variant", ["KI", "Opc", "API-KEY", "Secret_Hash", "Authorization"])
def test_forbidden_names_match_whatever_the_case_or_separator(variant: str) -> None:
    log, repo, _ = _log()
    with pytest.raises(AuditContentError):
        log.append("x", SYNTHETIC_IMSI, None, {variant: "v"}, "bss-app")
    assert repo.entries == []


def test_nested_forbidden_keys_are_rejected_at_any_depth() -> None:
    log, repo, _ = _log()
    deep = {"apns": [{"name": "internet", "auth": {"inner": [{"opc": SENTINEL_OPC}]}}]}
    with pytest.raises(AuditContentError) as exc:
        log.append("line.activate", SYNTHETIC_IMSI, None, deep, "bss-app")
    assert SENTINEL_OPC not in str(exc.value)
    assert "after.apns[0].auth.inner[0]" in str(exc.value)
    assert repo.entries == []


def test_a_stored_envelope_is_rejected() -> None:
    # Ciphertext does not belong in the audit log either.
    envelope = encrypt_field(StaticKeyProvider(), SYNTHETIC_IMSI, "ki", b"x")
    log, repo, _ = _log()
    with pytest.raises(AuditContentError):
        log.append("x", SYNTHETIC_IMSI, None, {"sim": dict(envelope)}, "bss-app")
    assert repo.entries == []


@pytest.mark.parametrize("bad", [SecretStr("x"), b"bytes", bytearray(b"b"), [SecretStr("x")]])
def test_secret_and_binary_values_are_rejected_under_any_name(bad: Any) -> None:
    log, repo, _ = _log()
    with pytest.raises(AuditContentError):
        log.append("x", SYNTHETIC_IMSI, None, {"harmless_name": bad}, "bss-app")
    assert repo.entries == []


def test_non_string_field_names_are_rejected() -> None:
    log, _, _ = _log()
    with pytest.raises(AuditContentError):
        log.append("x", SYNTHETIC_IMSI, None, {1: "v"}, "bss-app")


def test_near_misses_are_allowed() -> None:
    log, repo, _ = _log()
    after = {"kind": "x", "pinned": True, "token_count": 1, "key_id": "bss-app", "status": "active"}
    log.append("x", SYNTHETIC_IMSI, None, after, "bss-app")
    assert repo.entries[0]["after"] == after


def test_the_guard_works_on_field_names_not_on_values() -> None:
    # Documented limit: a secret placed as a VALUE under an innocent name is not detected, so
    # callers pass structured state (status, speeds, apn names), never free text. A value check
    # such as "32 hex characters" would also reject request ids, so there is none.
    log, repo, _ = _log()
    log.append("x", SYNTHETIC_IMSI, None, {"note": SENTINEL_KI}, "bss-app")
    assert repo.entries[0]["after"] == {"note": SENTINEL_KI}


@pytest.mark.parametrize("imsi", ["", "123", SYNTHETIC_IMSI + "0"])
def test_invalid_imsi_is_rejected(imsi: str) -> None:
    log, repo, _ = _log()
    with pytest.raises(ValueError, match="IMSI"):
        log.append("x", imsi, None, None, "bss-app")
    assert repo.entries == []


def test_an_action_is_required() -> None:
    with pytest.raises(ValueError, match="action"):
        _log()[0].append("", SYNTHETIC_IMSI, None, None, "bss-app")


# --- append-only --------------------------------------------------------------------------------


def _public(cls: type) -> set[str]:
    return {name for name in dir(cls) if not name.startswith("_")}


@pytest.mark.parametrize(
    "cls", [AuditLogRepository, MongoAuditLogRepository, InMemoryAuditLogRepository]
)
def test_the_audit_repository_can_only_insert(cls: type) -> None:
    public = _public(cls) - {"entries"}  # the fake exposes its list for inspection
    assert public == {"insert"}, f"{cls.__name__} offers more than insert: {sorted(public)}"


def test_the_audit_log_class_offers_only_append() -> None:
    assert _public(AuditLog) == {"append"}


# --- failed authentication is not an audit event ------------------------------------------------


def test_authentication_code_never_touches_the_audit_log() -> None:
    for relative in (
        "services/authentication.py",
        "api/dependencies.py",
        "services/api_key_admin.py",
    ):
        tree = ast.parse((PACKAGE / relative).read_text())
        imported = {
            n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
        } | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not {m for m in imported if "audit" in m}, f"{relative} imports the audit log"
