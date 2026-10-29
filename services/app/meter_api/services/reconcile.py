"""Compare the bytes we stored with the network's own counters (M-28).

The network team supplies, for a window, the bytes the network counted per IMSI. This says which
lines differ by more than the tolerance (1% by default, the Build Plan's finish line for data), and
by how much. It fixes nothing and bills nothing: a difference is for a person to look at.

Where the network's totals come from is the network team's (N7); this takes them as a CSV of
`imsi,bytes` lines. An IMSI is personal data: nothing here logs one, and the report masks all but
the last four digits.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime

from app.meter_api.domain import IMSI_PATTERN
from app.meter_api.repositories.ports import UsageRepository

DEFAULT_TOLERANCE_BPS = 100  # 1%


class BadNetworkTotals(ValueError):
    """The network's totals could not be read. The message names the line, never the value."""


@dataclass(frozen=True)
class Difference:
    imsi: str
    ours: int | None  # None: we stored nothing for this IMSI in the window
    network: int | None  # None: the network supplied nothing for this IMSI

    @property
    def masked_imsi(self) -> str:
        return "***********" + self.imsi[-4:]

    @property
    def percent(self) -> float | None:
        """How far ours is from the network's, as a percentage of the network's. None if either
        side is missing, or the network counted nothing."""
        if self.ours is None or not self.network:
            return None
        return abs(self.ours - self.network) * 100 / self.network


@dataclass(frozen=True)
class Report:
    compared: int
    within: int
    flagged: tuple[Difference, ...]
    our_total: int
    network_total: int

    @property
    def ok(self) -> bool:
        return not self.flagged


@dataclass(frozen=True)
class TotalReport:
    """All the bytes we stored in a window against one total from the network."""

    ours: int
    network: int
    tolerance_bps: int

    @property
    def percent(self) -> float | None:
        """How far ours is from the network's, as a percentage of the network's. None if the
        network counted nothing."""
        return abs(self.ours - self.network) * 100 / self.network if self.network else None

    @property
    def ok(self) -> bool:
        return abs(self.ours - self.network) * 10_000 <= self.tolerance_bps * self.network


def parse_network_totals(text: str) -> dict[str, int]:
    """`imsi,bytes` per line. A header line, blank lines and `#` comments are allowed."""
    totals: dict[str, int] = {}
    reader = csv.reader(io.StringIO(text))
    for number, row in enumerate(reader, start=1):
        if not row or not "".join(row).strip() or row[0].strip().startswith("#"):
            continue
        if number == 1 and row[0].strip().lower() == "imsi":
            continue
        if len(row) != 2:
            raise BadNetworkTotals(f"line {number}: expected imsi,bytes")
        imsi, raw = row[0].strip(), row[1].strip()
        if not IMSI_PATTERN.match(imsi):
            raise BadNetworkTotals(f"line {number}: not a 15-digit IMSI")
        if not raw.isdigit():
            raise BadNetworkTotals(f"line {number}: bytes must be a whole number, not negative")
        if imsi in totals:
            raise BadNetworkTotals(f"line {number}: an IMSI appears twice")
        totals[imsi] = int(raw)
    if not totals:
        raise BadNetworkTotals("no totals found")
    return totals


def compare(
    ours: dict[str, int], network: dict[str, int], tolerance_bps: int = DEFAULT_TOLERANCE_BPS
) -> Report:
    """Flag every IMSI that differs by more than `tolerance_bps` of the network's total.

    An IMSI present on one side only is flagged. The network counting nothing while we stored
    bytes is flagged however small. Both counting nothing is fine.
    """
    if tolerance_bps < 0:
        raise ValueError("tolerance must not be negative")
    flagged: list[Difference] = []
    within = 0
    for imsi in sorted(ours.keys() | network.keys()):
        mine, theirs = ours.get(imsi), network.get(imsi)
        if mine is None or theirs is None:
            flagged.append(Difference(imsi, mine, theirs))
        elif abs(mine - theirs) * 10_000 > tolerance_bps * theirs:
            flagged.append(Difference(imsi, mine, theirs))
        else:
            within += 1
    return Report(
        compared=len(ours.keys() | network.keys()),
        within=within,
        flagged=tuple(flagged),
        our_total=sum(ours.values()),
        network_total=sum(network.values()),
    )


def reconcile(
    usage: UsageRepository,
    network: dict[str, int],
    start: datetime,
    end: datetime,
    tolerance_bps: int = DEFAULT_TOLERANCE_BPS,
) -> Report:
    """Our stored totals for [start, end) against the network's."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("times must be timezone-aware (UTC)")
    if end <= start:
        raise ValueError("the window must end after it starts")
    return compare(usage.totals_by_imsi(start, end), network, tolerance_bps)


def reconcile_total(
    usage: UsageRepository,
    network_total: int,
    start: datetime,
    end: datetime,
    tolerance_bps: int = DEFAULT_TOLERANCE_BPS,
    imsi: str | None = None,
) -> TotalReport:
    """Everything we stored for [start, end) (or one SIM's) against a single network total.

    For when the network's own counter is an interface total (the kernel's byte counters on
    `ogstun`), which says how many bytes passed but not whose they were. Run it with one test phone
    on the network, or give `imsi` to compare that SIM alone.
    """
    if tolerance_bps < 0:
        raise ValueError("tolerance must not be negative")
    if network_total < 0:
        raise ValueError("the network total must not be negative")
    if imsi is not None and not IMSI_PATTERN.match(imsi):
        raise ValueError("an IMSI is 15 digits")
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("times must be timezone-aware (UTC)")
    if end <= start:
        raise ValueError("the window must end after it starts")
    totals = usage.totals_by_imsi(start, end)
    ours = totals.get(imsi, 0) if imsi is not None else sum(totals.values())
    return TotalReport(ours=ours, network=network_total, tolerance_bps=tolerance_bps)
