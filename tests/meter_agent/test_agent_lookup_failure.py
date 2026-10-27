"""When RatelLink cannot be reached, usage must be kept, not dropped.

These tests use the real `HttpAssignmentCache` (over a mock transport) with the real `Agent`: the
bug was in how the two fit together, which tests with a hand-written fake cache did not show. A
refresh that fails used to leave an empty map, every address then looked unknown, and the
intervals' bytes were discarded while the baseline moved on.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest

from services.meter_agent.agent import Agent, AgentConfig
from services.meter_agent.assignments import HttpAssignmentCache
from services.meter_agent.domain.records import Reading
from services.meter_agent.spool.spool import Spool

T0 = 1791820800  # aligned to the clock
IMSI = "621000000000001"


class Reader:
    def __init__(self) -> None:
        self.readings: dict[str, Reading] = {}

    def read(self) -> dict[str, Reading]:
        return self.readings


class Poster:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def __call__(self, batch: object) -> bool:
        assert isinstance(batch, list)
        # What the real API accepts: usage records, never raw counter readings.
        for item in batch:
            assert set(item) == {"imsi", "period_start", "period_end", "bytes_up", "bytes_down"}
        self.records.extend(batch)
        return True


class RatelLink:
    """A RatelLink that can be switched off."""

    def __init__(self, assignments: list[dict[str, str]]) -> None:
        self.up = False
        self.assignments = assignments

    def handler(self, request: httpx.Request) -> httpx.Response:
        if not self.up:
            raise httpx.ConnectError("unreachable")
        return httpx.Response(200, json={"assignments": self.assignments})


def _agent(tmp_path: Path, link: RatelLink) -> tuple[Agent, Reader, Poster, Spool]:
    cache = HttpAssignmentCache(
        base_url="http://fake-link",
        api_key="placeholder-key",
        client=httpx.Client(transport=httpx.MockTransport(link.handler)),
    )
    reader, poster, spool = Reader(), Poster(), Spool(tmp_path / "spool")
    agent = Agent(reader, cache, poster, spool, AgentConfig(spool_dir=str(tmp_path / "spool")))
    return agent, reader, poster, spool


def _read(reader: Reader, up: int, down: int, at: int, ip: str = "10.45.0.2") -> None:
    reader.readings = {ip: Reading(ip, up, down, at)}


def test_usage_is_kept_when_ratellink_is_down_and_posted_once_it_is_back(tmp_path: Path) -> None:
    link = RatelLink([{"ue_ip": "10.45.0.2", "imsi": IMSI}])
    agent, reader, poster, spool = _agent(tmp_path, link)

    _read(reader, 1000, 2000, T0)
    agent.run_once(now=T0)  # baseline
    _read(reader, 1500, 2600, T0 + 300)
    agent.run_once(now=T0 + 300)  # RatelLink is down for this interval

    assert poster.records == []
    assert len(spool.pending()) == 1  # kept, not dropped

    link.up = True
    _read(reader, 1500, 2600, T0 + 600)  # no new traffic
    agent.run_once(now=T0 + 600)

    assert spool.pending() == []
    assert poster.records == [
        {
            "imsi": IMSI,
            "period_start": T0 + 300,
            "period_end": T0 + 600,
            "bytes_up": 500,
            "bytes_down": 600,
        }
    ]


def test_kept_usage_stays_on_disk_while_ratellink_is_still_down(tmp_path: Path) -> None:
    link = RatelLink([{"ue_ip": "10.45.0.2", "imsi": IMSI}])
    agent, reader, poster, spool = _agent(tmp_path, link)

    _read(reader, 0, 0, T0)
    agent.run_once(now=T0)
    for tick in (1, 2, 3):
        _read(reader, tick * 100, tick * 100, T0 + tick * 300)
        agent.run_once(now=T0 + tick * 300)

    assert poster.records == []
    assert len(spool.pending()) == 3  # one file per interval, nothing lost


def test_kept_usage_for_an_address_that_has_no_line_is_not_sent_and_does_not_block(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    link = RatelLink([{"ue_ip": "10.45.0.9", "imsi": "621000000000009"}])
    agent, reader, poster, spool = _agent(tmp_path, link)

    _read(reader, 0, 0, T0)
    agent.run_once(now=T0)
    _read(reader, 400, 800, T0 + 300)
    agent.run_once(now=T0 + 300)  # down: kept
    assert len(spool.pending()) == 1

    link.up = True
    caplog.set_level(logging.WARNING)
    agent.run_once(now=T0 + 600)  # up: nobody owns 10.45.0.2

    assert poster.records == []
    assert spool.pending() == []  # it does not wedge the spool forever
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "meter.agent.unmapped_usage" in messages
    assert "10.45.0.2" not in messages  # counts only, no address


def test_usage_from_an_unmapped_address_is_reported_in_the_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    link = RatelLink([{"ue_ip": "10.45.0.9", "imsi": "621000000000009"}])
    link.up = True
    agent, reader, poster, _ = _agent(tmp_path, link)

    _read(reader, 0, 0, T0)
    agent.run_once(now=T0)
    caplog.set_level(logging.WARNING)
    _read(reader, 400, 800, T0 + 300)
    agent.run_once(now=T0 + 300)

    assert poster.records == []
    event = next(r for r in caplog.records if r.getMessage() == "meter.agent.unmapped_usage")
    assert (event.addresses, event.bytes_up, event.bytes_down) == (1, 400, 800)  # type: ignore[attr-defined]
