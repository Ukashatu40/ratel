"""Meter poster protocol and HTTP implementation for RatelMeter ingest.

The poster takes a batch (a list of UsageRecord-shaped dicts) and returns
True when the API acknowledged it. It is the same shape as the spool's
Sender, so the loop can hand the poster to Spool.replay() directly.
"""

from __future__ import annotations

from typing import Protocol

from .poster import HttpMeterPoster


class MeterPoster(Protocol):
    def __call__(self, batch: object) -> bool:
        """POST a batch to the RatelMeter API. True on acknowledgement."""
        ...


__all__ = ["HttpMeterPoster", "MeterPoster"]
