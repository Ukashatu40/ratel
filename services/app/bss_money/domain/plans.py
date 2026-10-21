"""Plans and bundles: what a customer can buy. Pure data and the rules that keep it sane.

Fields are the Build Plan's (RatelBSS: money). The actual plans, prices and speeds are TODO(PRD):
nothing here invents one. Money is whole kobo; data is whole bytes; time is in whole days.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class OnExhaustion(StrEnum):
    """What happens to a line's data when its allowance runs out. Voice is never touched."""

    SLOW = "slow"  # keep the line, at the plan's slow speeds
    STOP = "stop"  # cut data


@dataclass(frozen=True)
class Plan:
    plan_id: int
    name: str
    price_kobo: int
    validity_days: int
    data_bytes: int
    speed_ul_mbps: float
    speed_dl_mbps: float
    # Where it is sold. TODO(PRD): what the channels are. Kept as opaque names.
    channels: tuple[str, ...]
    on_exhaustion: OnExhaustion
    slow_ul_mbps: float | None = None
    slow_dl_mbps: float | None = None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "on_exhaustion", OnExhaustion(self.on_exhaustion))
        except ValueError:
            raise ValueError("on_exhaustion must be 'slow' or 'stop'") from None
        _check_offer(self.plan_id, self.name, self.price_kobo, self.validity_days, self.data_bytes)
        _check_speed("speed_ul_mbps", self.speed_ul_mbps)
        _check_speed("speed_dl_mbps", self.speed_dl_mbps)
        if self.on_exhaustion is OnExhaustion.SLOW:
            if self.slow_ul_mbps is None or self.slow_dl_mbps is None:
                raise ValueError(
                    "a plan that slows on exhaustion needs slow_ul_mbps and slow_dl_mbps"
                )
            _check_speed("slow_ul_mbps", self.slow_ul_mbps)
            _check_speed("slow_dl_mbps", self.slow_dl_mbps)
        elif self.slow_ul_mbps is not None or self.slow_dl_mbps is not None:
            raise ValueError("a plan that stops on exhaustion has no slow speeds")
        _check_channels(self.channels)


@dataclass(frozen=True)
class Bundle:
    bundle_id: int
    name: str
    price_kobo: int
    validity_days: int
    data_bytes: int
    channels: tuple[str, ...]

    def __post_init__(self) -> None:
        _check_offer(
            self.bundle_id, self.name, self.price_kobo, self.validity_days, self.data_bytes
        )
        _check_channels(self.channels)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_offer(offer_id: int, name: str, price_kobo: int, days: int, data_bytes: int) -> None:
    if not _is_int(offer_id) or offer_id <= 0:
        raise ValueError("the id must be a positive whole number")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("the name must not be empty")
    if not _is_int(price_kobo) or price_kobo < 0:
        raise ValueError("price_kobo must be a whole number of kobo, zero or more")
    if not _is_int(days) or days < 1:
        raise ValueError("validity_days must be a whole number of days, at least 1")
    if not _is_int(data_bytes) or data_bytes < 1:
        raise ValueError("data_bytes must be a whole number of bytes, at least 1")


def _check_speed(field: str, value: object) -> None:
    ok = isinstance(value, int | float) and not isinstance(value, bool)
    if not ok or not math.isfinite(float(value)) or float(value) <= 0:  # type: ignore[arg-type]
        raise ValueError(f"{field} must be a positive number of Mbps")


def _check_channels(channels: tuple[str, ...]) -> None:
    if not isinstance(channels, tuple) or not all(isinstance(c, str) and c for c in channels):
        raise ValueError("channels must be a tuple of non-empty names")
