"""W2-09 stub. The real implementation comes from W2-08 (@CaptRaven).

A CounterReader returns, for every address it can see, the cumulative
bytes_up_total and bytes_down_total. The agent computes the per-interval
increase itself.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.records import Reading


class CounterReader(Protocol):
    def read(self) -> dict[str, Reading]:
        """Return {ue_ip: Reading} for every address with a counter.

        Bytes are cumulative, integers. `read_at` is UTC epoch seconds.
        """
        ...
