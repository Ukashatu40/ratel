"""Time rules: store and send UTC, epoch seconds on the wire, 300-second aligned intervals."""

from __future__ import annotations

import time
from datetime import UTC, datetime

INTERVAL_SECONDS = 300


def utc_epoch_now() -> int:
    return int(time.time())


def to_epoch(dt: datetime) -> int:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("naive datetime rejected: time must be timezone-aware UTC")
    return int(dt.astimezone(UTC).timestamp())


def from_epoch(seconds: int) -> datetime:
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        raise TypeError("epoch seconds must be an int")
    return datetime.fromtimestamp(seconds, tz=UTC)


def interval_start(epoch: int, interval: int = INTERVAL_SECONDS) -> int:
    """Floor to the clock-aligned interval (00:00, 00:05, 00:10 ... UTC).

    A replayed interval always lands on the same key (imsi + period_start).
    """
    if interval <= 0:
        raise ValueError("interval must be positive")
    return epoch - (epoch % interval)
