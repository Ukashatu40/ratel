"""Snapshot parsers and the file-backed reader for core-up counters.

Reads cumulative byte counters from nftables JSON or conntrack text, keyed by UE IP address. The
live reader (it runs `nft`) is in nftables.py.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from common.logging import log_event
from common.timeutil import utc_epoch_now

from ..domain.records import Reading
from .errors import MalformedSnapshotError

log = logging.getLogger("ratel.meter.counters")

_CONNTRACK_LINE = re.compile(
    r"src=(?P<src1>\S+)\s+dst=(?P<dst1>\S+).*?bytes=(?P<b1>\d+).*?"
    r"src=(?P<src2>\S+)\s+dst=(?P<dst2>\S+).*?bytes=(?P<b2>\d+)"
)


def _validate_ip(ip_str: str) -> str:
    try:
        ipaddress.ip_address(ip_str)
        return ip_str
    except ValueError as exc:
        raise MalformedSnapshotError(f"Invalid IP address format: {exc}") from exc


UP_SET = "up"
DOWN_SET = "down"


def _counter_bytes(inner: dict[str, Any]) -> int:
    counter = inner.get("counter")
    if not isinstance(counter, dict):
        # A set element with no counter means the counting rules are not the ones we expect.
        raise MalformedSnapshotError("A set element has no counter: is the counting table right?")
    value = counter.get("bytes")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise MalformedSnapshotError("Counter bytes must be a non-negative integer")
    return value


def _set_totals(nft_set: dict[str, Any], name: str) -> dict[str, int]:
    """The cumulative bytes per address in one set, read from its `elem` list."""
    elements = nft_set.get("elem", [])  # a set nothing has been counted in has no `elem` key
    if not isinstance(elements, list):
        raise MalformedSnapshotError(f"Set '{name}': 'elem' must be a list")
    totals: dict[str, int] = {}
    for entry in elements:
        inner = entry.get("elem") if isinstance(entry, dict) else None
        if not isinstance(inner, dict):
            raise MalformedSnapshotError(f"Set '{name}': an element is not {{'elem': {{...}}}}")
        address = inner.get("val")
        if not isinstance(address, str):
            raise MalformedSnapshotError(f"Set '{name}': an element has no address")
        try:
            ipaddress.IPv4Address(address)
        except ValueError as exc:
            raise MalformedSnapshotError(f"Set '{name}': invalid IPv4 address") from exc
        if address in totals:
            raise MalformedSnapshotError(f"Set '{name}': the same address appears twice")
        totals[address] = _counter_bytes(inner)
    return totals


def parse_nftables_json(
    raw: dict[str, Any] | str,
    read_at: int | None = None,
    *,
    up_set: str = UP_SET,
    down_set: str = DOWN_SET,
) -> dict[str, Reading]:
    """Read the per-address byte counters out of `nft -j list set|table ...` output.

    The shape (nftables 1.0.2, captured on core-up on 2026-10-20) is:

        {"nftables": [{"metainfo": {...}},
                      {"set": {"name": "up", "type": "ipv4_addr", ...,
                               "elem": [{"elem": {"val": "192.0.2.2",
                                           "counter": {"packets": 100, "bytes": 102800}}}]}}]}

    A set nothing was counted in yet has no `elem` key and is valid. Anything else that is wrong
    raises `MalformedSnapshotError`: a document that is not nftables JSON, a missing `up` or `down`
    set (the counting table is not loaded), an element without a counter, a bad address or byte
    count. Nothing here ever turns a problem into an empty result.
    """
    now = read_at if read_at is not None else utc_epoch_now()

    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise MalformedSnapshotError("Snapshot is not valid JSON") from exc
    elif isinstance(raw, dict):
        data = raw
    else:
        raise MalformedSnapshotError(f"Expected dict or JSON string, got {type(raw).__name__}")

    if not isinstance(data, dict) or not isinstance(data.get("nftables"), list):
        raise MalformedSnapshotError("Snapshot is not nftables JSON: no 'nftables' list")

    totals: dict[str, dict[str, int]] = {}
    for item in data["nftables"]:
        if not isinstance(item, dict):
            raise MalformedSnapshotError("An nftables item is not an object")
        nft_set = item.get("set")
        if nft_set is None:
            continue  # metainfo, table, chain, rule: not counters
        if not isinstance(nft_set, dict):
            raise MalformedSnapshotError("A 'set' item is not an object")
        name = nft_set.get("name")
        if name not in (up_set, down_set):
            continue
        if name in totals:
            raise MalformedSnapshotError(f"Set '{name}' appears more than once")
        totals[name] = _set_totals(nft_set, name)

    missing = [n for n in (up_set, down_set) if n not in totals]
    if missing:
        raise MalformedSnapshotError(
            f"Snapshot has no set named {', '.join(missing)}: is the counting table loaded?"
        )

    up_map, down_map = totals[up_set], totals[down_set]
    return {
        ip: Reading(
            ue_ip=ip,
            bytes_up_total=up_map.get(ip, 0),
            bytes_down_total=down_map.get(ip, 0),
            read_at=now,
        )
        for ip in sorted(set(up_map) | set(down_map))
    }


def parse_conntrack_dump(
    text: str, ue_subnets: tuple[str, ...] = ("10.45.0.0/16",), read_at: int | None = None
) -> dict[str, Reading]:
    """Parse conntrack dump text.

    Aggregates flows by matching UE IP addresses. Packets from UE count as upload,
    packets to UE count as download.
    """
    now = read_at if read_at is not None else utc_epoch_now()
    parsed_subnets = [ipaddress.ip_network(s) for s in ue_subnets]

    def is_ue(ip_str: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip_str)
            return any(addr in net for net in parsed_subnets)
        except ValueError:
            return False

    up_accum: dict[str, int] = {}
    down_accum: dict[str, int] = {}

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        match = _CONNTRACK_LINE.search(line)
        if not match:
            # If line is non-empty and has flow-like tokens but cannot be parsed
            if "src=" in line and "bytes=" in line:
                raise MalformedSnapshotError("Malformed conntrack line")
            continue

        src1 = match.group("src1")
        dst1 = match.group("dst1")
        b1 = int(match.group("b1"))
        b2 = int(match.group("b2"))

        if is_ue(src1):
            # Forward flow: UE is source (upload), return flow has b2 (download)
            up_accum[src1] = up_accum.get(src1, 0) + b1
            down_accum[src1] = down_accum.get(src1, 0) + b2
        elif is_ue(dst1):
            # Return flow perspective: UE is destination
            down_accum[dst1] = down_accum.get(dst1, 0) + b1
            up_accum[dst1] = up_accum.get(dst1, 0) + b2

    all_ips = set(up_accum.keys()) | set(down_accum.keys())
    return {
        ip: Reading(
            ue_ip=ip,
            bytes_up_total=up_accum.get(ip, 0),
            bytes_down_total=down_accum.get(ip, 0),
            read_at=now,
        )
        for ip in all_ips
    }


class SnapshotCounterReader:
    """Counter reader backed by a recorded file or in-memory snapshot generator."""

    def __init__(
        self,
        source: Path | str | Callable[[], str | dict[str, Any]],
        format_type: str = "auto",
        ue_subnets: tuple[str, ...] = ("10.45.0.0/16",),
    ) -> None:
        self._source = source
        self._format_type = format_type
        self._ue_subnets = ue_subnets

    def read(self) -> dict[str, Reading]:
        if callable(self._source):
            raw = self._source()
        elif isinstance(self._source, (Path, str)):
            p = Path(self._source)
            if not p.exists():
                raise MalformedSnapshotError(f"Snapshot file does not exist: {p}")
            raw = p.read_text(encoding="utf-8")
        else:
            raise MalformedSnapshotError("Invalid snapshot source type")

        now = utc_epoch_now()

        # Format detection
        if self._format_type == "conntrack" or (
            self._format_type == "auto"
            and isinstance(raw, str)
            and ("src=" in raw and "bytes=" in raw)
        ):
            if not isinstance(raw, str):
                raise MalformedSnapshotError("Conntrack dump must be text, not a dict")
            readings = parse_conntrack_dump(raw, ue_subnets=self._ue_subnets, read_at=now)
        else:
            readings = parse_nftables_json(raw, read_at=now)

        # Log total count only; never log addresses
        log_event(
            log,
            logging.DEBUG,
            "meter.counters.read",
            address_count=len(readings),
        )
        return readings
