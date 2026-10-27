"""Domain models and business invariants for data usage metering.

Pure logic: no I/O, no database drivers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

IMSI_PATTERN = re.compile(r"^[0-9]{15}$")


@dataclass(frozen=True, slots=True)
class UsageRecord:
    imsi: str
    period_start: int  # UTC epoch seconds
    period_end: int  # UTC epoch seconds
    bytes_up: int
    bytes_down: int

    def validate(self) -> None:
        if not IMSI_PATTERN.match(self.imsi):
            raise ValueError("Invalid IMSI format: must be 15 digits")
        if self.period_start < 0 or self.period_end < 0:
            raise ValueError("Period timestamps must be non-negative")
        if self.bytes_up < 0 or self.bytes_down < 0:
            raise ValueError("Byte counts must be non-negative integers")
