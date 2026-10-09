"""Append-only audit log of every change RatelLink makes (Build Plan: RatelLink spec, `audit_log`).

An entry records when, which calling system (by `api_key_id`, never the key), what, which line,
and the line state before and after. The content guard (domain/audit.py) refuses secrets.

Failed authentication is not written here. This log records changes. Failures go to the
operational log as `auth.rejected`.

TODO(project lead): enforce append-only in MongoDB itself (a user that may only insert into
`audit_log`). This class and its repository offer insert only, but a database permission would
hold even if the code were changed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from common.timeutil import utc_now
from ratel_link.domain.audit import AuditEntry, check_audit_content
from ratel_link.domain.identifiers import is_api_key_id, is_imsi
from ratel_link.repositories.ports import AuditLogRepository


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
