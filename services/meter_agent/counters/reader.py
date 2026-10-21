"""Counter reader implementations and snapshot parsers for core-up.

Reads cumulative byte counters from nftables or conntrack snapshots,
keyed by UE IP address.
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


def parse_nftables_json(
    raw: dict[str, Any] | str, read_at: int | None = None
) -> dict[str, Reading]:
    """Parse nftables JSON output containing set/map elements or counter rules.

    Expected formats:
    1. Standard `nft -j list ...` with element entries in 'ue_up' and 'ue_down' sets/maps.
    2. Direct structured snapshot dict with 'entries' list.
    """
    now = read_at if read_at is not None else utc_epoch_now()

    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception as exc:
            raise MalformedSnapshotError(f"Malformed JSON in snapshot: {exc}") from exc
    elif isinstance(raw, dict):
        data = raw
    else:
        raise MalformedSnapshotError(f"Expected dict or JSON string, got {type(raw).__name__}")

    if not isinstance(data, dict):
        raise MalformedSnapshotError("Snapshot root must be a JSON object")

    up_map: dict[str, int] = {}
    down_map: dict[str, int] = {}

    # Handle direct structured snapshot: {"timestamp": ..., "entries": [...]}
    if "entries" in data:
        entries = data.get("entries")
        if not isinstance(entries, list):
            raise MalformedSnapshotError("'entries' field must be a list")
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise MalformedSnapshotError(f"Entry {idx} must be a dict")
            ip = entry.get("ue_ip")
            if not isinstance(ip, str):
                raise MalformedSnapshotError(f"Entry {idx} missing 'ue_ip'")
            _validate_ip(ip)

            bytes_up = entry.get("bytes_up")
            bytes_down = entry.get("bytes_down")
            if (
                not isinstance(bytes_up, int)
                or isinstance(bytes_up, bool)
                or not isinstance(bytes_down, int)
                or isinstance(bytes_down, bool)
            ):
                raise MalformedSnapshotError(f"Entry {idx} bytes must be integer")
            if bytes_up < 0 or bytes_down < 0:
                raise MalformedSnapshotError(f"Entry {idx} bytes must be non-negative")

            up_map[ip] = bytes_up
            down_map[ip] = bytes_down

    # Handle nftables JSON: {"nftables": [...]}
    elif "nftables" in data:
        items = data.get("nftables")
        if not isinstance(items, list):
            raise MalformedSnapshotError("'nftables' field must be a list")

        for item in items:
            if not isinstance(item, dict):
                continue
            elem = item.get("element")
            if not elem or not isinstance(elem, dict):
                continue

            set_name = elem.get("name")
            elem_obj = elem.get("elem")
            if not elem_obj:
                continue

            elements = elem_obj if isinstance(elem_obj, list) else [elem_obj]
            for e in elements:
                if not isinstance(e, dict):
                    continue
                val = e.get("val")
                if not isinstance(val, str):
                    continue
                _validate_ip(val)

                counter = e.get("counter")
                if not isinstance(counter, dict):
                    continue
                b = counter.get("bytes")
                if not isinstance(b, int) or isinstance(b, bool) or b < 0:
                    raise MalformedSnapshotError("Counter bytes must be a non-negative integer")

                if set_name in ("ue_up", "upload", "up"):
                    up_map[val] = b
                elif set_name in ("ue_down", "download", "down"):
                    down_map[val] = b
                else:
                    # Generic counter: check if field indicates direction
                    direction = e.get("direction")
                    if direction == "up":
                        up_map[val] = b
                    elif direction == "down":
                        down_map[val] = b
    else:
        # If empty dict or unknown structure without entries/nftables
        if not data:
            return {}
        raise MalformedSnapshotError("Snapshot missing recognized counter format")

    all_ips = set(up_map.keys()) | set(down_map.keys())
    result = {
        ip: Reading(
            ue_ip=ip,
            bytes_up_total=up_map.get(ip, 0),
            bytes_down_total=down_map.get(ip, 0),
            read_at=now,
        )
        for ip in all_ips
    }
    return result


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
