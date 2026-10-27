"""Unit tests for core-up CounterReader and snapshot parsers (M-07)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from services.meter_agent.counters import (
    MalformedSnapshotError,
    SnapshotCounterReader,
    parse_conntrack_dump,
    parse_nftables_json,
)

FIXTURES = Path(__file__).parent / "fixtures"
# Real `nft -j list table` output from core-up (nftables 1.0.2); synthetic addresses and counts.
REAL_TABLE = (FIXTURES / "nft_table_core_up.json").read_text()


def _table(up: dict | None = None, down: dict | None = None) -> dict:
    def make(name: str, elems: dict | None) -> dict:
        body: dict = {"family": "inet", "name": name, "table": "t", "type": "ipv4_addr"}
        if elems is not None:
            body["elem"] = [
                {"elem": {"val": ip, "counter": {"packets": 1, "bytes": n}}}
                for ip, n in elems.items()
            ]
        return {"set": body}

    return {"nftables": [{"metainfo": {"version": "1.0.2"}}, make("up", up), make("down", down)]}


def test_real_nft_output_is_read_into_readings() -> None:
    readings = parse_nftables_json(REAL_TABLE, read_at=1791820800)
    assert set(readings) == {"192.0.2.2", "192.0.2.3"}
    first = readings["192.0.2.2"]
    assert (first.bytes_up_total, first.bytes_down_total) == (102800, 102800)
    assert first.read_at == 1791820800
    # Counted going up only: the download side is zero, not missing.
    second = readings["192.0.2.3"]
    assert (second.bytes_up_total, second.bytes_down_total) == (700, 0)


def test_sets_with_no_traffic_yet_are_valid_and_empty() -> None:
    assert parse_nftables_json(_table(up=None, down=None)) == {}
    assert parse_nftables_json(_table(up={}, down={})) == {}


def test_the_big_numbers_survive() -> None:
    readings = parse_nftables_json(
        _table(up={"10.45.0.2": 52428800}, down={"10.45.0.2": 2684354560})
    )
    assert readings["10.45.0.2"].bytes_down_total == 2684354560


def test_many_addresses() -> None:
    ups = {f"10.45.0.{n}": n * 1000 for n in range(1, 4)}
    downs = {f"10.45.0.{n}": n * 4000 for n in range(1, 4)}
    readings = parse_nftables_json(_table(up=ups, down=downs))
    assert {ip: (r.bytes_up_total, r.bytes_down_total) for ip, r in readings.items()} == {
        "10.45.0.1": (1000, 4000),
        "10.45.0.2": (2000, 8000),
        "10.45.0.3": (3000, 12000),
    }


def test_conntrack_many_short_flows() -> None:
    # Conntrack text format with multiple flows across UEs
    line1 = (
        "ipv4 2 tcp 6 431999 ESTABLISHED src=10.45.0.5 dst=93.184.216.34 "
        "sport=54321 dport=80 packets=5 bytes=500 src=93.184.216.34 dst=10.45.0.5 "
        "sport=80 dport=54321 packets=10 bytes=1200 [ASSURED] mark=0 use=1"
    )
    line2 = (
        "ipv4 2 tcp 6 431999 ESTABLISHED src=10.45.0.5 dst=1.1.1.1 "
        "sport=54322 dport=443 packets=8 bytes=800 src=1.1.1.1 dst=10.45.0.5 "
        "sport=443 dport=54322 packets=15 bytes=1800 [ASSURED] mark=0 use=1"
    )
    line3 = (
        "ipv4 2 udp 17 29 src=10.45.0.9 dst=8.8.8.8 sport=5353 dport=53 "
        "packets=2 bytes=150 src=8.8.8.8 dst=10.45.0.9 sport=53 dport=5353 "
        "packets=2 bytes=250 mark=0 use=1"
    )
    dump = f"\n{line1}\n{line2}\n{line3}\n"
    readings = parse_conntrack_dump(dump)
    assert len(readings) == 2
    # 10.45.0.5: up = 500 + 800 = 1300, down = 1200 + 1800 = 3000
    assert readings["10.45.0.5"].bytes_up_total == 1300
    assert readings["10.45.0.5"].bytes_down_total == 3000
    # 10.45.0.9: up = 150, down = 250
    assert readings["10.45.0.9"].bytes_up_total == 150
    assert readings["10.45.0.9"].bytes_down_total == 250


def test_malformed_snapshots_raise_error_and_never_return_zero() -> None:
    # Invalid JSON
    with pytest.raises(MalformedSnapshotError):
        parse_nftables_json("this is not json")

    # Malformed conntrack line
    bad_conntrack = "ipv4 src=10.45.0.5 bytes=broken"
    with pytest.raises(MalformedSnapshotError, match="Malformed conntrack line"):
        parse_conntrack_dump(bad_conntrack)


def _without(doc: dict, name: str) -> dict:
    return {"nftables": [i for i in doc["nftables"] if i.get("set", {}).get("name") != name]}


@pytest.mark.parametrize(
    "bad",
    [
        {},  # an empty object is not "no usage": it is not nftables output
        {"nftables": []},  # no sets at all: the counting table is not loaded
        {"nftables": "x"},
        {"unrelated": 1},
        [],
        "[]",
        "",
        "null",
        _without(_table(up={}, down={}), "down"),
        _without(_table(up={}, down={}), "up"),
        {"nftables": [5]},
        {"nftables": [{"set": 5}]},
    ],
    ids=lambda v: repr(v)[:40],
)
def test_anything_that_is_not_the_counting_table_is_an_error_never_empty(bad: object) -> None:
    with pytest.raises(MalformedSnapshotError):
        parse_nftables_json(bad)  # type: ignore[arg-type]


def test_bad_elements_are_errors() -> None:
    good = _table(up={"10.45.0.2": 1}, down={})
    for mutate in (
        lambda s: s["elem"][0]["elem"].pop("counter"),
        lambda s: s["elem"][0]["elem"].update(counter={"packets": 1, "bytes": -1}),
        lambda s: s["elem"][0]["elem"].update(counter={"packets": 1, "bytes": "9"}),
        lambda s: s["elem"][0]["elem"].update(counter={"packets": 1, "bytes": True}),
        lambda s: s["elem"][0]["elem"].update(val="999.1.1.1"),
        lambda s: s["elem"][0]["elem"].update(val="2001:db8::1"),  # the table is ipv4_addr
        lambda s: s["elem"][0]["elem"].pop("val"),
        lambda s: s["elem"].append(dict(s["elem"][0])),  # the same address twice
        lambda s: s.update(elem="oops"),
        lambda s: s.update(elem=[{"val": "10.45.0.2"}]),  # not wrapped in {"elem": ...}
    ):
        doc = json.loads(json.dumps(good))
        mutate(doc["nftables"][1]["set"])
        with pytest.raises(MalformedSnapshotError):
            parse_nftables_json(doc)


def test_the_same_set_twice_is_an_error() -> None:
    doc = _table(up={}, down={})
    doc["nftables"].append(doc["nftables"][1])
    with pytest.raises(MalformedSnapshotError, match="more than once"):
        parse_nftables_json(doc)


def test_snapshot_file_reader(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    snapshot_file = tmp_path / "recorded.json"
    snapshot_file.write_text(REAL_TABLE)

    caplog.set_level(logging.DEBUG)
    readings = SnapshotCounterReader(snapshot_file).read()

    assert readings["192.0.2.2"].bytes_up_total == 102800
    assert readings["192.0.2.2"].bytes_down_total == 102800

    # Verify no IP address appears in log messages
    for record in caplog.records:
        assert "192.0.2.2" not in record.getMessage()


def test_a_missing_snapshot_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(MalformedSnapshotError, match="does not exist"):
        SnapshotCounterReader(tmp_path / "nope.json").read()
