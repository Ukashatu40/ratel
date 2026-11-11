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
from services.meter_agent.main import tick_at_start
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


class KeyedPoster:
    """The API's rule: a record with the key (imsi, period_start) replaces the one already there."""

    def __init__(self) -> None:
        self.stored: dict[tuple[str, int], tuple[int, int]] = {}
        self.overwrites = 0

    def __call__(self, batch: object) -> bool:
        assert isinstance(batch, list)
        for r in batch:
            key = (str(r["imsi"]), int(r["period_start"]))  # type: ignore[call-overload]
            if key in self.stored:
                self.overwrites += 1
            self.stored[key] = (int(r["bytes_up"]), int(r["bytes_down"]))  # type: ignore[call-overload]
        return True

    def total(self) -> tuple[int, int]:
        return sum(u for u, _ in self.stored.values()), sum(d for _, d in self.stored.values())


def test_a_restart_in_the_middle_of_an_interval_loses_no_interval_and_overwrites_none(
    tmp_path: Path,
) -> None:
    """Found in the lab on 2026-11-11: the tick the agent made the moment it started, at 10:01:25,
    labelled its 85 seconds of traffic with the interval 09:55 to 10:00, which had been posted at
    10:00:00. The API replaced that record, so the interval's traffic was lost and the comparison
    with the interface counters was 9.95% off."""
    reader, api = Reader(), KeyedPoster()
    first = agent(tmp_path, reader, api, store(tmp_path))  # type: ignore[arg-type]
    reader.set(0, 0, T0)
    first.run_once(now=T0)  # baseline
    reader.set(1000, 9000, T0 + 300)
    first.run_once(now=T0 + 300 + 1)  # the boundary tick: traffic of T0 to T0 + 300
    # The service restarts 85 seconds into the next interval, and traffic goes on.
    reader.set(1100, 9800, T0 + 300 + 85)
    second = agent(tmp_path, reader, api, store(tmp_path))  # type: ignore[arg-type]
    assert second.wants_immediate_tick() is False  # it waits for the boundary
    reader.set(1600, 14000, T0 + 600)
    second.run_once(now=T0 + 600 + 1)  # the next boundary tick
    assert api.stored == {(IMSI, T0): (1000, 9000), (IMSI, T0 + 300): (600, 5000)}
    assert api.overwrites == 0
    assert api.total() == (1600, 14000)  # every byte, none twice


def test_a_tick_in_the_middle_of_an_interval_would_replace_the_interval_before_it(
    tmp_path: Path,
) -> None:
    """Why the loop must not tick at once after a restart: the same restart, ticking at once."""
    reader, api = Reader(), KeyedPoster()
    first = agent(tmp_path, reader, api, store(tmp_path))  # type: ignore[arg-type]
    reader.set(0, 0, T0)
    first.run_once(now=T0)
    reader.set(1000, 9000, T0 + 300)
    first.run_once(now=T0 + 300 + 1)
    reader.set(1100, 9800, T0 + 300 + 85)
    second = agent(tmp_path, reader, api, store(tmp_path))  # type: ignore[arg-type]
    second.run_once(now=T0 + 300 + 85)  # what the loop used to do at once
    assert api.overwrites == 1  # the interval already posted was replaced
    assert api.total() != (1100, 9800)  # and bytes were lost


def test_the_loop_ticks_at_once_only_when_there_is_nothing_to_resume_from(tmp_path: Path) -> None:
    reader, poster = Reader(), Poster()
    fresh = agent(tmp_path, reader, poster, store(tmp_path))
    assert tick_at_start(fresh, aligned=True) is True  # a baseline, which posts nothing
    reader.set(1000, 2000, T0)
    fresh.run_once(now=T0)
    resumed = agent(tmp_path, reader, poster, store(tmp_path))
    assert tick_at_start(resumed, aligned=True) is False  # waits for the boundary
    assert tick_at_start(resumed, aligned=False) is True  # not on the clock: as before
    assert tick_at_start(object(), aligned=True) is True  # call mode


def test_an_agent_without_a_store_still_ticks_at_once(tmp_path: Path) -> None:
    assert tick_at_start(agent(tmp_path, Reader(), Poster()), aligned=True) is True
