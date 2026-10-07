"""Append-only audit log of every change RatelLink makes (Build Plan: RatelLink spec, `audit_log`).

An entry records when, which calling system (by `api_key_id`, never the key), what, which line,
and the line state before and after. It never contains Ki, OPc, ciphertext, tokens or any other
secret: a content guard refuses such entries, and its error never repeats the offending value.

Failed authentication is not written here. This log records changes. Failures go to the
operational log as `auth.rejected` (see auth.py).

TODO(project lead): enforce append-only in MongoDB itself (a user that may only insert into
`audit_log`). This module and its repository offer insert only, but a database permission would
hold even if the code were changed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from pydantic import SecretStr

from common.timeutil import utc_now
from ratel_link.models import AuditEntry, is_api_key_id, is_imsi
from ratel_link.repositories import AuditLogRepository

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


class AuditLog:
    def __init__(
        self, repository: AuditLogRepository, now: Callable[[], datetime] = utc_now
    ) -> None:
        self._repository = repository
        self._now = now

    def append(
        self,
        action: str,
        imsi: str,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        api_key_id: str,
    ) -> None:
        if not action:
            raise ValueError("an audit entry needs an action")
        if not is_imsi(imsi):
            raise ValueError("invalid IMSI")
        if not is_api_key_id(api_key_id):
            # Also stops a key from being written here by mistake: a token does not match.
            raise ValueError("invalid api_key_id")
        check_audit_content(before, "before")
        check_audit_content(after, "after")
        entry: AuditEntry = {
            "at": self._now(),
            "api_key_id": api_key_id,
            "action": action,
            "imsi": imsi,
            "before": None if before is None else dict(before),
            "after": None if after is None else dict(after),
        }
        self._repository.insert(entry)
