"""Unit tests for core-up CounterReader and snapshot parsers (M-07)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from services.meter_agent.counters import (
    MalformedSnapshotError,
    SnapshotCounterReader,
    parse_conntrack_dump,
    parse_nftables_json,
)


def test_empty_snapshot_returns_empty_dict() -> None:
    empty_nftables = {"nftables": []}
    assert parse_nftables_json(empty_nftables) == {}
    assert parse_nftables_json({}) == {}
    assert parse_conntrack_dump("") == {}


def test_nftables_one_long_transfer() -> None:
    # A single UE performs a large 2.5 GB download and 50 MB upload
    snapshot = {
        "nftables": [
            {
                "element": {
                    "family": "inet",
                    "table": "ratel_meter",
                    "name": "ue_up",
                    "elem": {
                        "val": "10.45.0.2",
                        "counter": {"packets": 35000, "bytes": 52428800},
                    },
                }
            },
            {
                "element": {
                    "family": "inet",
                    "table": "ratel_meter",
                    "name": "ue_down",
                    "elem": {
                        "val": "10.45.0.2",
                        "counter": {"packets": 1750000, "bytes": 2684354560},
                    },
                }
            },
        ]
    }
    readings = parse_nftables_json(snapshot, read_at=1791820800)
    assert len(readings) == 1
    assert "10.45.0.2" in readings
    r = readings["10.45.0.2"]
    assert r.ue_ip == "10.45.0.2"
    assert r.bytes_up_total == 52428800
    assert r.bytes_down_total == 2684354560
    assert r.read_at == 1791820800


def test_nftables_many_short_flows() -> None:
    # Multiple UEs with element lists
    snapshot = {
        "nftables": [
            {
                "element": {
                    "family": "inet",
                    "table": "ratel_meter",
                    "name": "ue_up",
                    "elem": [
                        {"val": "10.45.0.1", "counter": {"packets": 10, "bytes": 1000}},
                        {"val": "10.45.0.2", "counter": {"packets": 20, "bytes": 2000}},
                        {"val": "10.45.0.3", "counter": {"packets": 30, "bytes": 3000}},
                    ],
                }
            },
            {
                "element": {
                    "family": "inet",
                    "table": "ratel_meter",
                    "name": "ue_down",
                    "elem": [
                        {"val": "10.45.0.1", "counter": {"packets": 40, "bytes": 4000}},
                        {"val": "10.45.0.2", "counter": {"packets": 50, "bytes": 5000}},
                        {"val": "10.45.0.3", "counter": {"packets": 60, "bytes": 6000}},
                    ],
                }
            },
        ]
    }
    readings = parse_nftables_json(snapshot)
    assert len(readings) == 3
    assert readings["10.45.0.1"].bytes_up_total == 1000
    assert readings["10.45.0.1"].bytes_down_total == 4000
    assert readings["10.45.0.2"].bytes_up_total == 2000
    assert readings["10.45.0.2"].bytes_down_total == 5000
    assert readings["10.45.0.3"].bytes_up_total == 3000
    assert readings["10.45.0.3"].bytes_down_total == 6000


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

    # Negative bytes
    bad_bytes = {"entries": [{"ue_ip": "10.45.0.5", "bytes_up": -100, "bytes_down": 200}]}
    with pytest.raises(MalformedSnapshotError, match="non-negative"):
        parse_nftables_json(bad_bytes)

    # Invalid IP address
    bad_ip = {"entries": [{"ue_ip": "999.999.999.999", "bytes_up": 100, "bytes_down": 200}]}
    with pytest.raises(MalformedSnapshotError, match="Invalid IP address"):
        parse_nftables_json(bad_ip)

    # Malformed conntrack line
    bad_conntrack = "ipv4 src=10.45.0.5 bytes=broken"
    with pytest.raises(MalformedSnapshotError, match="Malformed conntrack line"):
        parse_conntrack_dump(bad_conntrack)


def test_snapshot_file_reader(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    snapshot_file = tmp_path / "nftables_snapshot.json"
    snapshot_file.write_text(
        """{
        "entries": [
            {"ue_ip": "10.45.0.10", "bytes_up": 4096, "bytes_down": 8192}
        ]
    }"""
    )

    caplog.set_level(logging.DEBUG)
    reader = SnapshotCounterReader(snapshot_file)
    readings = reader.read()

    assert len(readings) == 1
    assert readings["10.45.0.10"].bytes_up_total == 4096
    assert readings["10.45.0.10"].bytes_down_total == 8192

    # Verify no IP address appears in log messages
    for record in caplog.records:
        assert "10.45.0.10" not in record.getMessage()
