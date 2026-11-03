"""One pass of call mode with a fake source and poster: posting, spooling, replay and restart."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from meter_agent.calls import CallAgent, CallAgentConfig, CallRow, StateStore
from meter_agent.spool import Spool

T = 1_794_700_000
NOW = T + 1_000


def row(
    table: str, row_id: int, method: str, code: int, call: str, time: int, start: int = 0
) -> CallRow:
    return CallRow(
        table, row_id, method, code, call, "tag", "2348000000001", "08000000002", time, start
    )


class FakeSource:
    def __init__(self, *passes: list[CallRow]) -> None:
        self.passes = list(passes)
        self.asked: list[tuple[int, int, int]] = []

    def fetch(self, after_acc: int, after_missed: int, settle: int) -> tuple[list[CallRow], int]:
        self.asked.append((after_acc, after_missed, settle))
        return (self.passes.pop(0) if self.passes else []), 0


class FakePoster:
    def __init__(self, up: bool = True) -> None:
        self.up = up
        self.batches: list[object] = []

    def __call__(self, batch: object) -> bool:
        if self.up:
            self.batches.append(batch)
        return self.up


def agent(tmp_path: Path, source: FakeSource, poster: FakePoster) -> CallAgent:
    return CallAgent(
        source, poster, Spool(tmp_path / "spool"), StateStore(tmp_path / "state"),
        CallAgentConfig(settle_seconds=10, open_max_seconds=21_600),
    )  # fmt: skip


def calls(poster: FakePoster) -> list[dict[str, object]]:
    return [r for batch in poster.batches for r in batch["records"]]  # type: ignore[index]


def test_a_finished_call_is_posted_once_and_the_spool_is_empty(tmp_path: Path) -> None:
    source = FakeSource([row("missed", 1, "INVITE", 603, "c1", T + 11, T)])
    poster = FakePoster()
    agent(tmp_path, source, poster).run_once(NOW)
    assert [(r["call_id"], r["end_reason"]) for r in calls(poster)] == [("c1", "declined")]
    assert Spool(tmp_path / "spool").pending() == []


def test_the_next_pass_asks_from_where_the_last_one_stopped(tmp_path: Path) -> None:
    source = FakeSource(
        [row("acc", 7, "INVITE", 200, "c1", T + 6, T), row("missed", 3, "INVITE", 603, "c2", T + 9)]
    )
    a = agent(tmp_path, source, FakePoster())
    a.run_once(NOW)
    a.run_once(NOW + 60)
    assert source.asked == [(0, 0, 10), (7, 3, 10)]


def test_an_answered_call_is_posted_when_its_bye_arrives_even_across_a_restart(
    tmp_path: Path,
) -> None:
    poster = FakePoster()
    agent(tmp_path, FakeSource([row("acc", 1, "INVITE", 200, "c1", T + 6, T)]), poster).run_once(
        NOW
    )
    assert calls(poster) == []  # still talking
    # The service restarts: a new object, the same folders.
    agent(tmp_path, FakeSource([row("acc", 2, "BYE", 200, "c1", T + 66)]), poster).run_once(
        NOW + 120
    )
    [record] = calls(poster)
    assert (
        record["end_reason"],
        record["started_at"],
        record["answered_at"],
        record["ended_at"],
    ) == ("completed", T, T + 6, T + 66)


def test_when_the_api_is_down_the_calls_wait_on_disk_and_go_when_it_is_back(tmp_path: Path) -> None:
    source = FakeSource([row("missed", 1, "INVITE", 486, "c1", T + 5, T)], [], [])
    down = FakePoster(up=False)
    a = agent(tmp_path, source, down)
    a.run_once(NOW)
    assert len(Spool(tmp_path / "spool").pending()) == 1 and down.batches == []
    down.up = True
    a.run_once(NOW + 60)
    assert [r["end_reason"] for r in calls(down)] == ["not_answered"]
    assert Spool(tmp_path / "spool").pending() == []


def test_a_crash_between_the_spool_and_the_state_posts_the_call_again_under_the_same_call_id(
    tmp_path: Path,
) -> None:
    rows = [row("missed", 1, "INVITE", 603, "c1", T + 11, T)]
    poster = FakePoster(up=False)
    store = StateStore(tmp_path / "state")

    class Dies(StateStore):
        def save(self, state: object) -> None:  # type: ignore[override]
            raise OSError("disk full")

    first = CallAgent(
        FakeSource(rows),
        poster,
        Spool(tmp_path / "spool"),
        Dies(tmp_path / "state"),
        CallAgentConfig(),
    )
    with pytest.raises(OSError):
        first.run_once(NOW)
    assert store.load().missed_id == 0  # the watermark did not move
    poster.up = True
    CallAgent(
        FakeSource(rows), poster, Spool(tmp_path / "spool"), store, CallAgentConfig()
    ).run_once(NOW + 60)
    assert {r["call_id"] for r in calls(poster)} == {
        "c1"
    }  # posted twice at most, one row in the store


def test_more_than_a_batch_of_calls_goes_in_several_batches_in_order(tmp_path: Path) -> None:
    rows = [row("missed", n, "INVITE", 603, f"c{n:04d}", T + 5, T) for n in range(1, 2501)]
    poster = FakePoster()
    agent(tmp_path, FakeSource(rows), poster).run_once(NOW)
    assert [len(b["records"]) for b in poster.batches] == [1000, 1000, 500]  # type: ignore[index]


def test_a_failing_source_leaves_the_state_and_the_spool_alone(tmp_path: Path) -> None:
    class Broken:
        def fetch(self, *_: int) -> tuple[list[CallRow], int]:
            raise RuntimeError("export failed")

    poster = FakePoster()
    a = CallAgent(
        Broken(),
        poster,
        Spool(tmp_path / "spool"),
        StateStore(tmp_path / "state"),
        CallAgentConfig(),
    )
    with pytest.raises(RuntimeError):
        a.run_once(NOW)
    assert Spool(tmp_path / "spool").pending() == [] and poster.batches == []


def test_nothing_is_logged_that_is_a_number_or_a_call_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    rows = [row("missed", 1, "INVITE", 603, "secret-call-id", T + 11, T)]
    agent(tmp_path, FakeSource(rows), FakePoster()).run_once(NOW)
    ours = [r for r in caplog.records if r.name.startswith("ratel")]
    assert ours
    text = " ".join(r.getMessage() + str(r.__dict__) for r in ours)
    for secret in ("secret-call-id", "2348000000001", "08000000002", "2348000000002"):
        assert secret not in text
