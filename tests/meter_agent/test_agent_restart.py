"""A restart of the data agent loses no traffic and counts none twice (W2-14).

Until this was built the previous readings lived in memory only, so the first tick after a
restart was a baseline and the traffic since the last tick was never counted. Found in the lab
on 2026-11-09, when two restarts in five minutes made a comparison with the interface unusable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.meter_agent.agent import Agent, AgentConfig
from services.meter_agent.domain.records import Reading
from services.meter_agent.spool import ReadingStore, Spool

T0 = 1_791_820_800  # aligned to the clock
IP = "10.45.128.2"
IMSI = "621000000000451"


class Reader:
    def __init__(self) -> None:
        self.readings: dict[str, Reading] = {}

    def read(self) -> dict[str, Reading]:
        return self.readings

    def set(self, up: int, down: int, at: int, ip: str = IP) -> None:
        self.readings = {**self.readings, ip: Reading(ip, up, down, at)}


class Cache:
    def refresh(self) -> bool:
        return True

    def imsi_for(self, ue_ip: str) -> str | None:
        return IMSI if ue_ip == IP else None


class Poster:
    def __init__(self, ok: bool = True, raises: bool = False) -> None:
        self.ok = ok
        self.raises = raises
        self.records: list[dict[str, object]] = []

    def __call__(self, batch: object) -> bool:
        if self.raises:
            raise RuntimeError("the API call blew up")
        assert isinstance(batch, list)
        if self.ok:
            self.records.extend(batch)
        return self.ok


class BrokenStore(ReadingStore):
    def save(self, readings: object) -> None:  # type: ignore[override]
        raise OSError("disk full")


def agent(
    tmp_path: Path, reader: Reader, poster: Poster, store: ReadingStore | None = None
) -> Agent:
    spool = Spool(tmp_path / "spool")
    config = AgentConfig(spool_dir=str(tmp_path / "spool"))
    return Agent(reader, Cache(), poster, spool, config, store)


def store(tmp_path: Path, max_age: int = 10**9) -> ReadingStore:
    # The tests use 2026-10-13 as "now" for the ticks, so the age limit is widened here; the
    # limit itself is tested in spool/test_readings.py and below.
    return ReadingStore(tmp_path / "spool" / "readings", max_age_seconds=max_age)


def test_the_first_tick_after_a_restart_counts_the_traffic_since_the_last_tick(
    tmp_path: Path,
) -> None:
    reader, poster = Reader(), Poster()
    first = agent(tmp_path, reader, poster, store(tmp_path))
    reader.set(1000, 2000, T0)
    first.run_once(now=T0)  # baseline
    reader.set(1500, 2600, T0 + 300)
    first.run_once(now=T0 + 300 + 1)
    # The service restarts: a new object, the same folders. Traffic goes on during the gap.
    second = agent(tmp_path, reader, poster, store(tmp_path))
    reader.set(2300, 3900, T0 + 600)
    second.run_once(now=T0 + 600 + 1)
    assert [(r["period_start"], r["bytes_up"], r["bytes_down"]) for r in poster.records] == [
        (T0, 500, 600),
        (T0 + 300, 800, 1300),  # not lost, and not counted again
    ]


def test_without_a_store_a_restart_starts_over_as_before(tmp_path: Path) -> None:
    reader, poster = Reader(), Poster()
    first = agent(tmp_path, reader, poster)
    reader.set(1000, 2000, T0)
    first.run_once(now=T0)
    second = agent(tmp_path, reader, poster)  # no store: the old behaviour, still supported
    reader.set(2300, 3900, T0 + 600)
    second.run_once(now=T0 + 601)
    assert poster.records == []  # a baseline


def test_a_restart_after_the_counters_were_reset_counts_the_new_reading_from_zero(
    tmp_path: Path,
) -> None:
    reader, poster = Reader(), Poster()
    first = agent(tmp_path, reader, poster, store(tmp_path))
    reader.set(9_000_000, 9_000_000, T0)
    first.run_once(now=T0)
    # The host rebooted: the counting table starts at zero again.
    second = agent(tmp_path, reader, poster, store(tmp_path))
    reader.set(700, 1200, T0 + 300)
    second.run_once(now=T0 + 301)
    assert [(r["bytes_up"], r["bytes_down"]) for r in poster.records] == [(700, 1200)]


def test_the_readings_are_saved_before_the_batch_is_delivered(tmp_path: Path) -> None:
    """If the process dies in the delivery, the next run must not count the same bytes again."""
    reader = Reader()
    first = agent(tmp_path, reader, Poster(raises=True), store(tmp_path))
    reader.set(1000, 2000, T0)
    first.run_once(now=T0)
    reader.set(1500, 2600, T0 + 300)
    with pytest.raises(RuntimeError):
        first.run_once(now=T0 + 301)  # the post blows up mid-tick
    poster = Poster()
    second = agent(tmp_path, reader, poster, store(tmp_path))
    reader.set(1500, 2600, T0 + 600)  # no new traffic
    second.run_once(now=T0 + 601)
    assert poster.records == []  # the lost interval is not added to this one


def test_an_unwritable_store_does_not_stop_the_counting(tmp_path: Path) -> None:
    reader, poster = Reader(), Poster()
    only = agent(tmp_path, reader, poster, BrokenStore(tmp_path / "spool" / "readings"))
    reader.set(1000, 2000, T0)
    only.run_once(now=T0)
    reader.set(1500, 2600, T0 + 300)
    only.run_once(now=T0 + 301)
    assert [(r["bytes_up"], r["bytes_down"]) for r in poster.records] == [(500, 600)]


def test_a_reading_older_than_the_address_hold_is_not_resumed_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader, poster = Reader(), Poster()
    first = agent(tmp_path, reader, poster, store(tmp_path, max_age=23 * 3600))
    reader.set(1000, 2000, T0)
    first.run_once(now=T0)
    monkeypatch.setattr("services.meter_agent.agent.utc_epoch_now", lambda: T0 + 2 * 86400)
    second = agent(tmp_path, reader, poster, store(tmp_path, max_age=23 * 3600))
    reader.set(9000, 9000, T0 + 2 * 86400)
    second.run_once(now=T0 + 2 * 86400 + 1)
    assert (
        poster.records == []
    )  # a fresh baseline, so nothing is charged to a line that may not own it


def test_a_restart_while_the_api_is_down_keeps_both_the_batch_and_the_readings(
    tmp_path: Path,
) -> None:
    reader, down = Reader(), Poster(ok=False)
    first = agent(tmp_path, reader, down, store(tmp_path))
    reader.set(1000, 2000, T0)
    first.run_once(now=T0)
    reader.set(1500, 2600, T0 + 300)
    first.run_once(now=T0 + 301)  # spooled
    up = Poster()
    second = agent(tmp_path, reader, up, store(tmp_path))
    reader.set(1500, 2600, T0 + 600)
    second.run_once(now=T0 + 601)
    assert [(r["period_start"], r["bytes_up"], r["bytes_down"]) for r in up.records] == [
        (T0, 500, 600)
    ]
