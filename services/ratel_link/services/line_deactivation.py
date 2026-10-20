"""Deactivate a line (POST /v1/lines/{imsi}/deactivate): no internet and no calls.

Build Plan, Contract 1: "Deactivation is delete and rewrite, for now". The subscriber document is
deleted from RatelCore, the line's address is released (it stays held for 24 hours, so the same
line gets it back), and the line goes back to `provisioned`: its keys stay in RatelLink's store and
`/activate` writes a fresh document. The change reaches the phone at its next attach, where the
core rejects it (cause 8) because it has no record of the SIM.

Deleting the document also deletes what the HSS keeps in it, `security.sqn` included. Whether the
SIM accepts the network again straight after a re-activation is for the lab to confirm; barring
(`subscriber_status` 1) would avoid it and is the open question in the W2-05 spike.

Keys are not needed and not read. The delete is repeated on every call, even when the line's state
already says `provisioned`, so a call also removes a document that was left behind. Only a real
change is recorded and audited. Each step is idempotent, so a request that failed half way can
simply be sent again.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from common.logging import log_event
from common.timeutil import utc_now
from ratel_link.domain.line_state import LineState
from ratel_link.repositories.ports import (
    LineStateRepository,
    SimKeyRepository,
    SubscriberRepository,
)
from ratel_link.services.audit_log import AuditLog
from ratel_link.services.ip_allocation import IpAllocator
from ratel_link.services.line_activation import UnknownSimError
from ratel_link.services.line_audit import audit_view

log = logging.getLogger("ratel.link.lines")


class LineDeactivationService:
    def __init__(
        self,
        sims: SimKeyRepository,
        subscribers: SubscriberRepository,
        lines: LineStateRepository,
        allocator: IpAllocator,
        audit: AuditLog,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._sims = sims
        self._subscribers = subscribers
        self._lines = lines
        self._allocator = allocator
        self._audit = audit
        self._now = now

    def deactivate(self, imsi: str, reason: str, api_key_id: str) -> None:
        """Raises UnknownSimError when RatelLink has never heard of this IMSI."""
        before = self._lines.get(imsi)
        if before is None and not self._sims.exists(imsi):
            raise UnknownSimError

        removed = self._subscribers.remove_line(imsi)
        self._allocator.release(imsi)

        if before is None or before.status == "provisioned":
            if removed:
                # A document the state never recorded (made by hand, or left by an older run).
                log_event(log, logging.WARNING, "line.deactivate.orphan_removed")
            log_event(log, logging.INFO, "line.deactivate.unchanged", api_key_id=api_key_id)
            return

        after = LineState(imsi=imsi, status="provisioned", updated_at=self._now())
        self._lines.put(after)
        self._audit.append(
            "line.deactivate",
            imsi,
            audit_view(before),
            {**(audit_view(after) or {}), "reason": reason},
            api_key_id,
        )
        log_event(log, logging.INFO, "line.deactivate.done", api_key_id=api_key_id)
