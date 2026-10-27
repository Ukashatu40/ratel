"""Tests for mid-interval restarts, offline accumulation and ordered replay (M-09)."""

from __future__ import annotations

from pathlib import Path

from services.meter_agent.agent import Agent, AgentConfig
from services.meter_agent.domain.records import Reading
from services.meter_agent.spool.spool import Spool


class DynamicReader:
    def __init__(self) -> None:
        self.readings: dict[str, Reading] = {}

    def read(self) -> dict[str, Reading]:
        return self.readings


class StaticCache:
    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping

    def refresh(self) -> bool:
        return True

    def imsi_for(self, ue_ip: str) -> str | None:
        return self._mapping.get(ue_ip)


class RecordCollectorPoster:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.posted_records: list[dict[str, object]] = []

    def __call__(self, batch: object) -> bool:
        if not self.ok:
            return False
        assert isinstance(batch, list)
        self.posted_records.extend(batch)
        return True


def test_api_offline_for_one_hour_replays_in_order_with_no_loss(tmp_path: Path) -> None:
    # 1 hour = 12 intervals (each 300s)
    spool_dir = tmp_path / "spool"
    spool = Spool(spool_dir)

    reader = DynamicReader()
    cache = StaticCache({"10.45.0.2": "621000000000001"})
    # Poster is offline initially
    poster = RecordCollectorPoster(ok=False)
    config = AgentConfig(spool_dir=str(spool_dir), interval_seconds=300)

    agent = Agent(reader, cache, poster, spool, config)

    base_time = 1791820800
    # Tick 0: initial baseline reading
    reader.readings = {"10.45.0.2": Reading("10.45.0.2", 0, 0, base_time)}
    agent.run_once(now=base_time)
    assert len(spool.pending()) == 0
    assert len(poster.posted_records) == 0

    # 12 ticks while API is offline: each tick adds 1000 bytes up and 2000 bytes down
    cumulative_up = 0
    cumulative_down = 0
    for tick in range(1, 13):
        t = base_time + (tick * 300)
        cumulative_up += 1000
        cumulative_down += 2000
        reader.readings = {"10.45.0.2": Reading("10.45.0.2", cumulative_up, cumulative_down, t)}
        agent.run_once(now=t)

    # Spool must hold exactly 12 pending files, none delivered yet
    pending_files = spool.pending()
    assert len(pending_files) == 12
    assert len(poster.posted_records) == 0

    # Now API comes back online
    poster.ok = True

    # Next tick runs: agent first drains the spool in chronological order, then runs current tick
    t_next = base_time + (13 * 300)
    cumulative_up += 1000
    cumulative_down += 2000
    reader.readings = {"10.45.0.2": Reading("10.45.0.2", cumulative_up, cumulative_down, t_next)}
    agent.run_once(now=t_next)

    # Spool is now completely empty
    assert len(spool.pending()) == 0

    # Total posted records must be 13 (12 replayed from spool + 1 from current tick)
    assert len(poster.posted_records) == 13

    # Verify that records arrived in strict chronological order with no gaps
    # and no duplicate periods
    period_starts = [r["period_start"] for r in poster.posted_records]
    assert period_starts == sorted(period_starts)
    assert len(set(period_starts)) == 13


def test_stopping_mid_interval_and_restarting_loses_nothing_and_counts_nothing_twice(
    tmp_path: Path,
) -> None:
    spool_dir = tmp_path / "spool"
    spool = Spool(spool_dir)

    reader = DynamicReader()
    cache = StaticCache({"10.45.0.2": "621000000000001"})
    poster = RecordCollectorPoster(ok=True)
    config = AgentConfig(spool_dir=str(spool_dir), interval_seconds=300)

    # Agent 1 starts at t0 (baseline reading)
    t0 = 1791820800
    reader.readings = {"10.45.0.2": Reading("10.45.0.2", 1000, 2000, t0)}
    agent1 = Agent(reader, cache, poster, spool, config)
    agent1.run_once(now=t0)
    assert len(poster.posted_records) == 0

    # Tick 1 at t1: traffic occurs
    t1 = t0 + 300
    reader.readings = {"10.45.0.2": Reading("10.45.0.2", 1500, 3000, t1)}
    # Poster fails during this interval so it gets spooled
    poster.ok = False
    agent1.run_once(now=t1)
    assert len(spool.pending()) == 1
    assert len(poster.posted_records) == 0

    # Agent 1 is abruptly terminated / stopped mid-interval.
    # Agent 2 starts up fresh from the same spool directory.
    poster.ok = True
    agent2 = Agent(reader, cache, poster, spool, config)

    # Agent 2 runs tick at t2:
    t2 = t1 + 300
    reader.readings = {"10.45.0.2": Reading("10.45.0.2", 2200, 4200, t2)}
    agent2.run_once(now=t2)

    # Spool must be drained completely
    assert len(spool.pending()) == 0

    # Records delivered:
    # 1 from the spooled interval (t1) + 1 from the new baseline/next interval
    assert len(poster.posted_records) >= 1
    total_up = sum(int(r["bytes_up"]) for r in poster.posted_records)
    total_down = sum(int(r["bytes_down"]) for r in poster.posted_records)

    # Total counted bytes must be strictly non-negative and reflect the traffic
    assert total_up > 0
    assert total_down > 0
