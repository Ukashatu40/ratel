"""Give a line its fixed address, and take it back.

Build Plan, RatelLink: "Give every line a fixed IPv4 address on the internet APN at activation".

Used by activation and deactivation (W2-02). Idempotent: allocating for a line that has an address
returns the same address; releasing twice is harmless. Operational logs never carry the IMSI.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from common.logging import log_event
from common.timeutil import utc_now
from ratel_link.domain.identifiers import is_imsi
from ratel_link.domain.ip_pool import IpPool, hold_cutoff
from ratel_link.repositories.ports import IpAllocationRepository

log = logging.getLogger("ratel.link.ip")

# Several activations can race for the same lowest address. Each lost race moves on to the next.
_MAX_ATTEMPTS = 50


class AllocationContentionError(Exception):
    """Too many simultaneous claims. Try again."""


class IpAllocator:
    def __init__(
        self,
        repository: IpAllocationRepository,
        pool: IpPool,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._pool = pool
        self._now = now

    def allocate(self, imsi: str) -> str:
        """The line's address: its current one, its own released one, or the lowest free one.

        Raises PoolExhaustedError when no address is free.
        """
        if not is_imsi(imsi):
            raise ValueError("invalid IMSI")
        for _ in range(_MAX_ATTEMPTS):
            now = self._now()
            held = self._repository.find_by_imsi(imsi)
            if held is not None and held.state == "active":
                return held.ue_ip
            if held is not None:
                # Its own address is safe to take back at any time: nobody else can have it yet.
                if self._repository.reclaim(held.ue_ip, imsi, now):
                    log_event(log, logging.INFO, "ip.reclaimed")
                    return held.ue_ip
                continue  # someone took it after the hold: look again
            cutoff = hold_cutoff(now)
            candidate = self._pool.first_free(self._repository.unavailable(cutoff))
            if self._repository.claim_free(candidate, imsi, now, cutoff):
                log_event(log, logging.INFO, "ip.allocated")
                return candidate
        raise AllocationContentionError

    def release(self, imsi: str) -> bool:
        """Release the line's address. It stays on hold for 24 hours. False if it held none."""
        if not is_imsi(imsi):
            raise ValueError("invalid IMSI")
        released = self._repository.release(imsi, self._now())
        if released:
            log_event(log, logging.INFO, "ip.released")
        return released
