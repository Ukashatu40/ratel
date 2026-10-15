"""Change a line's data (POST /v1/lines/{imsi}/data): `full`, `slow` or `off`.

Only the `internet` session is touched; calling (the `ims` session) never is, so running out of
data never stops calls. `full` and `slow` set the internet speed (the session is put back at
position 0 if it was removed), `off` removes it. Every change is a targeted update, never a
replace, and the keys are not needed. The change reaches the phone at its next attach.

The operation is repeated on every call, even when the line's recorded state already matches, so
a call also repairs a subscriber document that drifted. Only a real change is recorded and audited.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from common.logging import log_event
from common.timeutil import utc_now
from ratel_link.domain.line_state import DataMode
from ratel_link.domain.subscriber import (
    INTERNET,
    SpeedError,
    ambr_document,
    internet_session,
    speed_from_mbps,
)
from ratel_link.repositories.ports import LineStateRepository, SubscriberRepository
from ratel_link.services.audit_log import AuditLog
from ratel_link.services.line_audit import audit_view

log = logging.getLogger("ratel.link.lines")


class NoActiveLineError(Exception):
    """The line was never activated, or is not active now."""


class SubscriberMissingError(Exception):
    """RatelLink records the line as active but the core has no subscriber document for it."""


class DataModeService:
    def __init__(
        self,
        subscribers: SubscriberRepository,
        lines: LineStateRepository,
        audit: AuditLog,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._subscribers = subscribers
        self._lines = lines
        self._audit = audit
        self._now = now

    def set_mode(
        self,
        imsi: str,
        mode: DataMode,
        speed_ul_mbps: float | None,
        speed_dl_mbps: float | None,
        api_key_id: str,
    ) -> None:
        """Raises SpeedError (a speed is missing for full or slow, or is not valid),
        NoActiveLineError and SubscriberMissingError."""
        state = self._lines.get(imsi)
        if state is None or state.status != "active" or state.ue_ip is None:
            raise NoActiveLineError

        others = tuple(apn for apn in state.apns if apn != INTERNET)
        if mode == "off":
            if not self._subscribers.remove_internet(imsi):
                raise SubscriberMissingError
            new = replace(state, data_mode="off", apns=others, updated_at=self._now())
        else:
            if speed_ul_mbps is None or speed_dl_mbps is None:
                raise SpeedError("full and slow need both speeds")
            ambr = ambr_document(speed_from_mbps(speed_ul_mbps), speed_from_mbps(speed_dl_mbps))
            session = internet_session(ambr, state.ue_ip)
            if not self._subscribers.set_internet_speeds(imsi, ambr, session):
                raise SubscriberMissingError
            new = replace(
                state,
                data_mode=mode,
                apns=(INTERNET, *others),
                speed_ul_mbps=speed_ul_mbps,
                speed_dl_mbps=speed_dl_mbps,
                updated_at=self._now(),
            )

        if replace(new, updated_at=state.updated_at) == state:
            log_event(log, logging.INFO, "line.data.unchanged", api_key_id=api_key_id)
            return
        self._lines.put(new)
        self._audit.append("line.data", imsi, audit_view(state), audit_view(new), api_key_id)
        log_event(log, logging.INFO, "line.data.changed", api_key_id=api_key_id, mode=mode)
