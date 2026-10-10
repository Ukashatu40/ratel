"""The pool of fixed IPv4 addresses given to lines (Build Plan, RatelLink spec). Pure, no I/O.

Rules from the Build Plan: every line gets one fixed address from the internet APN pool at
activation (10.45.0.0/16 in the lab), no line is activated without one, and an address that was
released is not given to anyone else for 24 hours, so a late counter reading can never be charged
to the wrong person. The same line may take its own released address back at any time.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Collection, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

RELEASE_HOLD = timedelta(hours=24)

AllocationState = Literal["active", "released"]


class PoolExhaustedError(Exception):
    """Every usable address is in use or still on hold."""


def hold_cutoff(now: datetime) -> datetime:
    """An address released at or before this moment is free for anyone to take."""
    return now - RELEASE_HOLD


@dataclass(frozen=True, slots=True)
class IpAllocation:
    """One address and who has it, or who had it last. One document per address, one per line."""

    ue_ip: str
    imsi: str
    state: AllocationState
    allocated_at: datetime
    released_at: datetime | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "ue_ip": self.ue_ip,
            "imsi": self.imsi,
            "state": self.state,
            "allocated_at": self.allocated_at,
            "released_at": self.released_at,
        }

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> IpAllocation:
        released = doc["released_at"]
        return cls(
            ue_ip=doc["ue_ip"],
            imsi=doc["imsi"],
            state=doc["state"],
            allocated_at=_utc(doc["allocated_at"]),
            released_at=None if released is None else _utc(released),
        )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class IpPool:
    """The usable addresses of an IPv4 network, lowest first.

    The network and broadcast addresses are never used. `reserved` addresses are never given out:
    by default the first host (10.45.0.1), which by convention is the gateway on the `ogstun`
    interface. TODO(network team): confirm which addresses in the lab pool are taken.
    """

    def __init__(self, network: str, reserved: Iterable[str] = ()) -> None:
        net = ipaddress.ip_network(network, strict=True)
        if not isinstance(net, ipaddress.IPv4Network) or net.prefixlen > 30:
            raise ValueError("the pool must be an IPv4 network of at least 4 addresses")
        self._network = net
        self._reserved = frozenset(reserved)

    @classmethod
    def from_cidr(cls, cidr: str) -> IpPool:
        first_host = str(next(ipaddress.ip_network(cidr, strict=True).hosts()))
        return cls(cidr, reserved={first_host})

    def usable(self) -> Iterator[str]:
        for host in self._network.hosts():
            address = str(host)
            if address not in self._reserved:
                yield address

    def first_free(self, unavailable: Collection[str]) -> str:
        """The lowest usable address that is not in `unavailable`."""
        for address in self.usable():
            if address not in unavailable:
                return address
        raise PoolExhaustedError
