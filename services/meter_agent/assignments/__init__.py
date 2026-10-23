"""Assignment cache protocol and HTTP client implementation for RatelMeter.

The cache refreshes every interval. If the refresh fails, the agent
spools the raw (ue_ip, bytes_up, bytes_down) and resolves IMSIs on
replay, once a refresh has worked — the policy confirmed by the RatelMeter owner.
"""

from __future__ import annotations

from typing import Protocol

from .client import HttpAssignmentCache


class AssignmentCache(Protocol):
    def refresh(self) -> bool:
        """Fetch GET /v1/assignments and replace the cache.

        Returns True when the cache is fresh, False when the refresh failed. Must not raise
        on a transient failure; leave the old cache in place. The agent keeps usage it cannot
        attribute until a refresh has worked.
        """
        ...

    def imsi_for(self, ue_ip: str) -> str | None:
        """Return the IMSI for an address, or None if unknown."""
        ...


__all__ = ["AssignmentCache", "HttpAssignmentCache"]
