"""Every current IP address with the line it belongs to (GET /v1/assignments), for RatelMeter.

An address stays listed against its line for 24 hours after the line is deactivated, because a late
counter reading for it must still be charged to that line and nobody else. After the hold ends the
address is either given to another line (and listed against it) or no longer listed.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable
from datetime import datetime

from common.timeutil import utc_now
from ratel_link.domain.ip_pool import Assignment, hold_cutoff
from ratel_link.repositories.ports import IpAllocationRepository


class AssignmentService:
    def __init__(
        self, repository: IpAllocationRepository, now: Callable[[], datetime] = utc_now
    ) -> None:
        self._repository = repository
        self._now = now

    def list_current(self) -> list[Assignment]:
        """Active addresses plus those still on hold, lowest address first."""
        current = self._repository.list_current(hold_cutoff(self._now()))
        ordered = sorted(current, key=lambda a: ipaddress.ip_address(a.ue_ip))
        return [Assignment(a.ue_ip, a.imsi) for a in ordered]
