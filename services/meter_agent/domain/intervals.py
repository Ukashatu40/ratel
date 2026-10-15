"""Interval alignment and counter delta logic (W2-14).

Pure functions. No file, network or database access.
"""

from __future__ import annotations

from common.timeutil import interval_start

from .records import Increase, Reading, UsageRecord

# The interval length, in seconds. The Build Plan fixes this at 300.
INTERVAL_SECONDS = 300


def interval_bounds(read_at: int) -> tuple[int, int]:
    """Return (period_start, period_end) for a reading time.

    period_start is aligned to the clock in UTC via common.timeutil.
    period_end is period_start + INTERVAL_SECONDS.
    """
    start = interval_start(read_at, INTERVAL_SECONDS)
    return start, start + INTERVAL_SECONDS


def increase(previous: Reading | None, current: Reading) -> Increase:
    """Return the increase between two readings for one address.

    If the current total is lower than the previous one, the host or UPF
    restarted: the new reading counts from zero, never a negative number.

    If there is no previous reading, the current reading is treated as the
    baseline and the increase is zero (see the open question in W2-14; the
    ticket proposes this and asks for it to be confirmed).
    """
    if previous is None:
        # Baseline reading. Count zero for this interval so nothing is
        # double counted. Confirm with @CaptRaven and the project lead.
        return Increase(bytes_up=0, bytes_down=0)

    up = current.bytes_up_total - previous.bytes_up_total
    down = current.bytes_down_total - previous.bytes_down_total

    # A counter reset means the total went backwards. Count the new
    # reading from zero; never return a negative number.
    if up < 0:
        up = current.bytes_up_total
    if down < 0:
        down = current.bytes_down_total

    return Increase(bytes_up=up, bytes_down=down)


def build_record(
    imsi: str,
    read_at: int,
    increase_value: Increase,
) -> UsageRecord | None:
    """Build one UsageRecord, or None for a zero-byte interval.

    A zero-byte interval (both up and down are zero) produces no record.
    """
    if increase_value.bytes_up == 0 and increase_value.bytes_down == 0:
        return None

    period_start, period_end = interval_bounds(read_at)
    return UsageRecord(
        imsi=imsi,
        period_start=period_start,
        period_end=period_end,
        bytes_up=increase_value.bytes_up,
        bytes_down=increase_value.bytes_down,
    )
