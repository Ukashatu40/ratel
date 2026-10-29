"""Reconciling our stored usage with the network's counters: it must be able to fail (M-28)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.meter_api.models import UsageRecordModel
from app.meter_api.reconcile_cli import main
from app.meter_api.repositories.sql import SqlUsageRepository
from app.meter_api.services.reconcile import (
    BadNetworkTotals,
    compare,
    parse_network_totals,
    reconcile,
)

A = "621000000000001"
B = "621000000000002"
START = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
END = START + timedelta(hours=1)


# --- the comparison ----------------------------------------------------------------------------


def test_equal_totals_pass() -> None:
    report = compare({A: 1_000, B: 5}, {A: 1_000, B: 5})
    assert report.ok
    assert (report.compared, report.within) == (2, 2)


def test_a_difference_within_one_percent_passes_and_over_it_is_flagged() -> None:
    assert compare({A: 10_099}, {A: 10_000}).ok  # 0.99%
    assert compare({A: 10_100}, {A: 10_000}).ok  # exactly 1%
    wrong = compare({A: 10_101}, {A: 10_000})  # 1.01%
    assert not wrong.ok
    assert wrong.flagged[0].percent == pytest.approx(1.01)


def test_a_deliberately_wrong_total_is_flagged() -> None:
    """The check is proven able to fail: a total that is 10% out cannot pass."""
    report = compare({A: 1_000_000, B: 1_100_000}, {A: 1_000_000, B: 1_000_000})
    assert [d.imsi for d in report.flagged] == [B]
    assert report.within == 1


def test_a_line_on_one_side_only_is_flagged() -> None:
    report = compare({A: 100}, {B: 100})
    assert {(d.imsi, d.ours, d.network) for d in report.flagged} == {
        (A, 100, None),
        (B, None, 100),
    }


def test_the_network_counting_nothing_while_we_stored_bytes_is_flagged() -> None:
    assert not compare({A: 1}, {A: 0}).ok
    assert compare({A: 0}, {A: 0}).ok


def test_a_tighter_tolerance_flags_what_a_looser_one_lets_through() -> None:
    assert compare({A: 10_050}, {A: 10_000}, tolerance_bps=100).ok
    assert not compare({A: 10_050}, {A: 10_000}, tolerance_bps=10).ok
    with pytest.raises(ValueError, match="negative"):
        compare({}, {}, tolerance_bps=-1)


@given(
    st.dictionaries(st.sampled_from([A, B]), st.integers(min_value=0, max_value=10**12)),
)
def test_a_total_always_agrees_with_itself(totals: dict[str, int]) -> None:
    assert compare(totals, dict(totals)).ok


def test_the_report_masks_the_imsi() -> None:
    [flagged] = compare({A: 1}, {}).flagged
    assert flagged.masked_imsi == "***********0001"
    assert A not in flagged.masked_imsi


# --- reading the network's totals --------------------------------------------------------------


def test_the_network_totals_are_read_with_a_header_blank_lines_and_comments() -> None:
    text = f"imsi,bytes\n# from the UPF\n\n{A},100\n{B}, 250 \n"
    assert parse_network_totals(text) == {A: 100, B: 250}


@pytest.mark.parametrize(
    ("text", "complaint"),
    [
        ("", "no totals"),
        (f"{A}\n", "expected imsi,bytes"),
        (f"{A},1,2\n", "expected imsi,bytes"),
        ("12345,100\n", "15-digit IMSI"),
        (f"{A},-5\n", "whole number"),
        (f"{A},1.5\n", "whole number"),
        (f"{A},100\n{A},200\n", "twice"),
    ],
)
def test_bad_network_totals_are_refused_without_echoing_the_value(
    text: str, complaint: str
) -> None:
    with pytest.raises(BadNetworkTotals, match=complaint) as caught:
        parse_network_totals(text)
    assert A not in str(caught.value)


# --- against stored usage ----------------------------------------------------------------------


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s  # type: ignore[misc]


def _store(session: Session, imsi: str, start: datetime, up: int, down: int) -> None:
    session.add(
        UsageRecordModel(
            imsi=imsi,
            period_start=start,
            period_end=start + timedelta(minutes=5),
            bytes_up=up,
            bytes_down=down,
        )
    )
    session.commit()


def test_our_total_is_up_plus_down_over_the_window_half_open(session: Session) -> None:
    _store(session, A, START, 100, 200)
    _store(session, A, START + timedelta(minutes=5), 50, 50)
    _store(session, A, END, 999, 999)  # starts at the end: outside
    _store(session, A, START - timedelta(minutes=5), 999, 999)  # before: outside
    totals = SqlUsageRepository(session).totals_by_imsi(START, END)
    assert totals == {A: 400}


def test_a_window_that_matches_passes_and_one_that_does_not_fails(session: Session) -> None:
    _store(session, A, START, 500, 500)
    repo = SqlUsageRepository(session)
    assert reconcile(repo, {A: 1_000}, START, END).ok
    assert not reconcile(repo, {A: 2_000}, START, END).ok


@pytest.mark.parametrize(
    ("start", "end"),
    [(START, START), (END, START), (START.replace(tzinfo=None), END)],  # the last has no timezone
)
def test_a_bad_window_is_refused(session: Session, start: datetime, end: datetime) -> None:
    with pytest.raises(ValueError, match=r"window|timezone"):
        reconcile(SqlUsageRepository(session), {A: 1}, start, end)


# --- the command -------------------------------------------------------------------------------


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"sqlite+pysqlite:///{tmp_path / 'bss.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        _store(s, A, START, 500, 500)
    engine.dispose()
    monkeypatch.setenv("DATABASE_URL", url)


def _argv(tmp_path: Path, content: str, **changes: str) -> list[str]:
    path = tmp_path / "network.csv"
    path.write_text(content)
    values = {
        "--from": str(int(START.timestamp())),
        "--to": str(int(END.timestamp())),
        "--network-totals": str(path),
    } | changes
    return [item for pair in values.items() for item in pair]


def test_exit_0_when_the_totals_agree(
    database: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_argv(tmp_path, f"{A},1000\n")) == 0
    assert "0 flagged" in capsys.readouterr().out


def test_exit_1_and_the_masked_line_when_a_total_is_wrong(
    database: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_argv(tmp_path, f"{A},2000\n")) == 1
    out = capsys.readouterr().out
    assert "***********0001: ours 1000, network 2000 (50.00% off)" in out
    assert A not in out


def test_exit_2_when_the_file_or_the_window_is_bad(
    database: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_argv(tmp_path, "not a csv line\n")) == 2
    assert main(_argv(tmp_path, f"{A},1000\n", **{"--network-totals": "/no/such/file"})) == 2
    assert main(_argv(tmp_path, f"{A},1000\n", **{"--to": str(int(START.timestamp()))})) == 2
    assert "cannot" in capsys.readouterr().err


def test_a_tolerance_can_be_given(database: None, tmp_path: Path) -> None:
    assert main(_argv(tmp_path, f"{A},1005\n")) == 0  # 0.5% out: within the default 1%
    assert main(_argv(tmp_path, f"{A},1005\n", **{"--tolerance-bps": "10"})) == 1  # not within 0.1%
