"""Activate a line (POST /v1/lines/{imsi}/activate): write its subscriber document into RatelCore.

Order of work: check the SIM's keys exist, check voice can be offered, give the line its fixed
address (idempotent), write the subscriber document in one operation, record the line's state, and
audit the change. The keys are decrypted here and only here, only to write the document, and are
never logged, returned or put in an audit entry.

Activating a line again with the same settings writes the same values and changes nothing: no state
change, no audit entry. Activating with different settings updates the fields RatelLink owns, as
the network team's guide describes for an existing document (docs/RATELCORE_INTEGRATION_FACTS.md).
The change reaches the phone at its next attach.

Each step is idempotent, so a request that failed half way can simply be sent again.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from common.logging import log_event
from common.timeutil import utc_now
from ratel_link.domain.line_state import LineState
from ratel_link.domain.subscriber import (
    IMS,
    INTERNET,
    activation_fields,
    speed_from_mbps,
)
from ratel_link.repositories.ports import (
    LineStateRepository,
    SubscriberRepository,
    VoiceTemplateSource,
)
from ratel_link.services.audit_log import AuditLog
from ratel_link.services.ip_allocation import IpAllocator
from ratel_link.services.line_audit import audit_view
from ratel_link.services.sim_keys import SimKeyStore

log = logging.getLogger("ratel.link.lines")


class UnknownSimError(Exception):
    """No keys are stored for this IMSI: the SIM was never imported."""


class VoiceUnavailableError(Exception):
    """Voice was requested but RatelLink has no usable voice template."""


class LineActivationService:
    def __init__(
        self,
        keys: SimKeyStore,
        subscribers: SubscriberRepository,
        lines: LineStateRepository,
        allocator: IpAllocator,
        voice_template: VoiceTemplateSource,
        audit: AuditLog,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._keys = keys
        self._subscribers = subscribers
        self._lines = lines
        self._allocator = allocator
        self._voice_template = voice_template
        self._audit = audit
        self._now = now

    def activate(
        self,
        imsi: str,
        msisdn: str,
        speed_ul_mbps: float,
        speed_dl_mbps: float,
        voice: bool,
        api_key_id: str,
    ) -> None:
        """Raises SpeedError (bad speed), UnknownSimError, VoiceUnavailableError (and the
        allocator's errors when no address can be given)."""
        upload = speed_from_mbps(speed_ul_mbps)
        download = speed_from_mbps(speed_dl_mbps)
        keys = self._keys.get_keys(imsi)
        if keys is None:
            raise UnknownSimError
        ims = None
        if voice:
            try:
                ims = self._voice_template.ims_session()
            except ValueError:
                ims = None
            if ims is None:
                log_event(log, logging.ERROR, "voice.template.unavailable")
                raise VoiceUnavailableError

        ue_ip = self._allocator.allocate(imsi)
        fields = activation_fields(
            msisdn=msisdn,
            ki=keys.ki,
            opc=keys.opc,
            upload=upload,
            download=download,
            voice=voice,
            ue_ip=ue_ip,
            ims_session=ims,
        )
        created = self._subscribers.upsert_line(imsi, fields.owned, fields.created_only)

        before = self._lines.get(imsi)
        state = LineState(
            imsi=imsi,
            status="active",
            updated_at=self._now(),
            msisdn=msisdn,
            apns=(INTERNET, IMS) if voice else (INTERNET,),
            ue_ip=ue_ip,
            speed_ul_mbps=speed_ul_mbps,
            speed_dl_mbps=speed_dl_mbps,
            data_mode="full",
        )
        if (
            before is not None
            and not created
            and replace(before, updated_at=state.updated_at) == state
        ):
            log_event(log, logging.INFO, "line.activate.unchanged", api_key_id=api_key_id)
            return
        self._lines.put(state)
        self._audit.append("line.activate", imsi, audit_view(before), audit_view(state), api_key_id)
        log_event(
            log,
            logging.INFO,
            "line.activate.created" if created else "line.activate.updated",
            api_key_id=api_key_id,
            voice=voice,
        )
