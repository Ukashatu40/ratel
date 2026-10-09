"""Audit entries and the rule for what may never be written into one. Pure, no I/O.

An entry never contains Ki, OPc, ciphertext, tokens or any other secret. The guard works on
field names, so callers pass structured state (status, speeds, apn names), never free text.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, TypedDict

from pydantic import SecretStr


class AuditEntry(TypedDict):
    """The `audit_log` collection (Build Plan: at, api_key_id, action, imsi, before, after)."""

    at: datetime
    api_key_id: str
    action: str
    imsi: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


# Field names that must never appear anywhere in `before` or `after`, at any depth.
FORBIDDEN_KEYS = frozenset(
    {
        "ki",
        "opc",
        "key",
        "secret",
        "token",
        "authorization",
        "ciphertext",
        "nonce",
        "pin",
        "password",
        "api_key",
        "secret_hash",
        "key_hash",
    }
)


class AuditContentError(Exception):
    """The entry would put forbidden content in the audit log. Never contains the content."""


def _normalise(key: str) -> str:
    return key.lower().replace("-", "_")


def check_audit_content(value: object, where: str) -> None:
    """Reject forbidden field names, secret or binary values, at any depth."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise AuditContentError(f"{where} has a field name that is not a string")
            if _normalise(key) in FORBIDDEN_KEYS:
                raise AuditContentError(f"{where} contains the forbidden field name {key!r}")
            check_audit_content(child, f"{where}.{key}")
    elif isinstance(value, list | tuple):
        for index, child in enumerate(value):
            check_audit_content(child, f"{where}[{index}]")
    elif isinstance(value, SecretStr | bytes | bytearray):
        raise AuditContentError(f"{where} contains a secret or binary value")
