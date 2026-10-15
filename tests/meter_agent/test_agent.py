"""Tests for the W2-09 loop skeleton, with fakes. No network, no lab.

The real CounterReader, AssignmentCache and MeterPoster are wired in
when W2-08, W2-03 and W2-12 land. This test proves the loop's logic and
its spool-on-failure behavior.
"""

from __future__ import annotations

from pathlib import Path

from services.meter_agent.agent import Agent, AgentConfig
from services.meter_agent.domain.records import Reading
from services.meter_agent.spool.spool import Spool


class FakeReader:
    def __init__(self, readings: dict[str, Reading]) -> None:
        self.readings = readings

    def read(self) -> dict[str, Reading]:
        return self.readings


class FakeCache:
    def __init__(self, mapping: dict[str, str], fail: bool = False) -> None:
        self._mapping = mapping
        self._fail = fail

    def refresh(self) -> None:
        if self._fail:
            raise RuntimeError("assignments unreachable")

    def imsi_for(self, ue_ip: str) -> str | None:
        return self._mapping.get(ue_ip)


class FakePoster:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.batches: list[list[dict[str, object]]] = []

    def __call__(self, batch: object) -> bool:
        if not self.ok:
            return False
        # The caller passes a list of record dicts; keep the type
        # honest for the assertions below.
        assert isinstance(batch, list)
        self.batches.append(batch)
        return True


def test_successful_interval_posts_a_record(tmp_path: Path) -> None:
    reader = FakeReader({"10.45.0.5": Reading("10.45.0.5", 1000, 2000, 1791820801)})
    cache = FakeCache({"10.45.0.5": "621000000000001"})
    poster = FakePoster(ok=True)
    spool = Spool(tmp_path)
    agent = Agent(reader, cache, poster, spool, AgentConfig(spool_dir=str(tmp_path)))

    # First pass is the baseline: zero increase, so no record.
    agent.run_once()
    assert poster.batches == []

    # Second pass has an increase.
    reader.readings = {"10.45.0.5": Reading("10.45.0.5", 1500, 2500, 1791821101)}
    agent.run_once()
    assert len(poster.batches) == 1
    record = poster.batches[0][0]
    assert record["imsi"] == "621000000000001"
    assert record["bytes_up"] == 500
    assert record["bytes_down"] == 500


def test_failed_poster_spools_the_batch(tmp_path: Path) -> None:
    reader = FakeReader({"10.45.0.5": Reading("10.45.0.5", 1000, 2000, 1791820801)})
    cache = FakeCache({"10.45.0.5": "621000000000001"})
    poster = FakePoster(ok=False)
    spool = Spool(tmp_path)
    agent = Agent(reader, cache, poster, spool, AgentConfig(spool_dir=str(tmp_path)))

    # Baseline tick: zero increase, nothing posted, nothing spooled.
    agent.run_once()
    assert poster.batches == []
    assert len(spool.pending()) == 0

    # Second tick has an increase; the poster fails; the batch spools.
    reader.readings = {"10.45.0.5": Reading("10.45.0.5", 1500, 2500, 1791821101)}
    agent.run_once()
    assert len(spool.pending()) == 1


def test_failed_cache_spools_raw_readings(tmp_path: Path) -> None:
    reader = FakeReader({"10.45.0.5": Reading("10.45.0.5", 1000, 2000, 1791820801)})
    cache = FakeCache({"10.45.0.5": "621000000000001"}, fail=True)
    poster = FakePoster(ok=True)
    spool = Spool(tmp_path)
    agent = Agent(reader, cache, poster, spool, AgentConfig(spool_dir=str(tmp_path)))

    # Baseline tick: zero increase, so nothing is spooled even though
    # the cache is failing.
    agent.run_once()
    assert poster.batches == []
    assert len(spool.pending()) == 0

    # Second tick has an increase; the cache still fails; the raw
    # reading is spooled, and the poster is never called.
    reader.readings = {"10.45.0.5": Reading("10.45.0.5", 1500, 2500, 1791821101)}
    agent.run_once()
    assert len(spool.pending()) == 1
    assert poster.batches == []
