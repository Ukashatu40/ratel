"""Pure record types for the RatelMeter data agent.

No file, network or database access. See W2-14.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Reading:
    """One counter reading for a single address, as integers."""

    ue_ip: str
    bytes_up_total: int
    bytes_down_total: int
    read_at: int  # UTC epoch seconds


@dataclass(frozen=True, slots=True)
class Increase:
    """The increase between two readings, never negative."""

    bytes_up: int
    bytes_down: int


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """One 300-second record, keyed on imsi + period_start.

    bytes_up and bytes_down are integers. period_start and period_end are
    UTC epoch seconds, aligned to the clock.
    """

    imsi: str
    period_start: int
    period_end: int
    bytes_up: int
    bytes_down: int

    @property
    def key(self) -> tuple[str, int]:
        """The upsert key: a replay produces the same key."""
        return (self.imsi, self.period_start)
