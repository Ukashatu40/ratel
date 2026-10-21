"""Counter reader interfaces, parsers and errors for core-up.

A CounterReader returns, for every address it can see, the cumulative
bytes_up_total and bytes_down_total. The agent computes the per-interval
increase itself.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.records import Reading
from .errors import MalformedSnapshotError
from .reader import (
    SnapshotCounterReader,
    parse_conntrack_dump,
    parse_nftables_json,
)


class CounterReader(Protocol):
    def read(self) -> dict[str, Reading]:
        """Return {ue_ip: Reading} for every address with a counter.

        Bytes are cumulative, integers. `read_at` is UTC epoch seconds.
        """
        ...


__all__ = [
    "CounterReader",
    "MalformedSnapshotError",
    "SnapshotCounterReader",
    "parse_conntrack_dump",
    "parse_nftables_json",
]
