"""The export command: what it is asked, what it may print, and that a failure carries no data."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from meter_agent.calls import CallSourceError, CommandCallSource
from meter_agent.calls.source import parse_rows

GOOD = "acc\t7\tINVITE\t200\tc1\ttagA\t2348000000001\t08000000002\t1794700006\t1794700000\n"
MISSED = "missed\t3\tINVITE\t603\tc2\ttagB\t2348000000001\t08000000002\t1794700011\t1794700000\n"


def test_rows_are_read_with_their_types() -> None:
    rows, skipped = parse_rows(GOOD + MISSED)
    assert skipped == 0 and [(r.table, r.row_id, r.sip_code) for r in rows] == [
        ("acc", 7, 200),
        ("missed", 3, 603),
    ]
    assert rows[0].call_id == "c1" and rows[0].start_ts == 1794700000 and rows[0].time == 1794700006


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "\n",
        "acc\t1\tINVITE\n",
        "other\t" + "x\t" * 8 + "x\n",
        GOOD.replace("\t200\t", "\tab\t"),
    ],
)
def test_a_line_that_is_not_a_row_is_skipped_and_counted(bad: str) -> None:
    rows, skipped = parse_rows(GOOD + bad)
    assert len(rows) == 1 and skipped == (0 if bad.strip() == "" else 1)


def command(tmp_path: Path, body: str) -> CommandCallSource:
    script = tmp_path / "export"
    script.write_text("#!/usr/bin/env bash\n" + body)
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return CommandCallSource(str(script))


def test_the_command_gets_three_whole_numbers_and_nothing_else(tmp_path: Path) -> None:
    log = tmp_path / "args.txt"
    source = command(tmp_path, f'echo "$@" > {log}\nprintf %s "{GOOD}"')
    rows, _ = source.fetch(41, 12, 10)
    assert log.read_text().split() == [
        "--after-acc",
        "41",
        "--after-missed",
        "12",
        "--settle",
        "10",
    ]
    assert len(rows) == 1


def test_a_command_that_fails_raises_without_its_own_message(tmp_path: Path) -> None:
    source = command(tmp_path, 'echo "ERROR 1045 password for root 2348000000001" >&2\nexit 3')
    with pytest.raises(CallSourceError) as caught:
        source.fetch(0, 0, 10)
    assert "2348000000001" not in str(caught.value) and "password" not in str(caught.value)
    assert str(caught.value) == "exit 3"


def test_a_command_that_is_missing_or_slow_raises(tmp_path: Path) -> None:
    with pytest.raises(CallSourceError):
        CommandCallSource(str(tmp_path / "nope")).fetch(0, 0, 10)
    slow = command(tmp_path, "sleep 5")
    slow._timeout = 0.2  # a short timeout for the test
    with pytest.raises(CallSourceError):
        slow.fetch(0, 0, 10)
