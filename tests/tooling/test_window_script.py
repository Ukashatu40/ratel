"""The window script: three counts of one window, with fake counters, nft and journal."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "deploy/core-up/ratel-window.sh"
BASH = shutil.which("bash") or "bash"


def script(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class Core:
    """A fake core-up: the interface's counters, the counting sets, and the agent's journal."""

    def __init__(self, tmp_path: Path) -> None:
        self.stats = tmp_path / "stats"
        self.stats.mkdir()
        self.sets = tmp_path / "sets"
        self.sets.mkdir()
        self.journal = tmp_path / "journal.txt"
        self.journal.write_text("")
        # nft prints a set the way the real one does: elements on one line, a counter in each.
        script(
            tmp_path / "nft",
            'set_name="$5"\n'
            'printf "table inet ratel_meter {\\n  set %s {\\n    elements = { " "$set_name"\n'
            'cat "$SETS/$set_name" | tr "\\n" "," | sed "s/,$//"\n'
            'printf " }\\n  }\\n}\\n"\n',
        )
        script(tmp_path / "journalctl", 'cat "$JOURNAL"\n')
        self.env = {
            **os.environ,
            "RATEL_WINDOW_DIR": str(tmp_path / "window"),
            "RATEL_WINDOW_STATS": str(self.stats),
            "RATEL_WINDOW_NFT": str(tmp_path / "nft"),
            "RATEL_WINDOW_JOURNALCTL": str(tmp_path / "journalctl"),
            "RATEL_WINDOW_SUDO": "",
            "RATEL_WINDOW_NOWAIT": "1",
            "SETS": str(self.sets),
            "JOURNAL": str(self.journal),
        }

    def counters(self, rx: int, tx: int, up: dict[str, int], down: dict[str, int]) -> None:
        (self.stats / "rx_bytes").write_text(f"{rx}\n")
        (self.stats / "tx_bytes").write_text(f"{tx}\n")
        for name, addresses in (("up", up), ("down", down)):
            (self.sets / name).write_text(
                "\n".join(f"{ip} counter packets 1 bytes {n}" for ip, n in addresses.items())
            )

    def run(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603  (our own script, fake commands, a temporary folder)
            [BASH, str(SCRIPT), *args],
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )


@pytest.fixture
def core(tmp_path: Path) -> Core:
    return Core(tmp_path)


def started_ten_minutes_ago(core: Core) -> None:
    """The fake counters answer at once, so move the saved start back by 600 seconds."""
    start = Path(core.env["RATEL_WINDOW_DIR"]) / "start"
    fields = start.read_text().split()
    fields[0] = str(int(fields[0]) - 600)
    start.write_text(" ".join(fields) + "\n")


def test_a_window_reports_the_three_counts_and_the_commands_for_bss_app(core: Core) -> None:
    core.counters(
        1_000,
        5_000,
        {"10.45.128.2": 700, "10.45.0.4": 100},
        {"10.45.128.2": 4_000, "10.45.0.4": 400},
    )
    assert core.run("start").returncode == 0
    started_ten_minutes_ago(core)
    # 1,000 bytes up and 20,000 down pass the interface; the table counts 990 and 19,900 of them.
    core.counters(
        2_000,
        25_000,
        {"10.45.128.2": 1_690, "10.45.0.4": 100},
        {"10.45.128.2": 23_900, "10.45.0.4": 400},
    )
    core.journal.write_text(
        '{"event":"meter.agent.unmapped_usage","addresses":1,"bytes_up":0,"bytes_down":300}\n'
        '{"event":"meter.agent.unmapped_usage","addresses":1,"bytes_up":5,"bytes_down":95}\n'
        '{"event":"meter.poster.success","record_count":1}\n'
    )
    assert core.run("end").returncode == 0
    result = core.run("report")
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "interface (ogstun)" in out and "21000" in out  # 1,000 up and 20,000 down
    assert "990" in out and "19900" in out  # the table
    assert "395" in out  # the unmapped: 5 up and 395 down
    assert "table less unmapped" in out and "20490" in out  # 20,890 less 400
    assert "-0.52%" in out  # the table against the interface
    assert "T0=" in out and "reconcile_cli" in out and "usage_record" in out


def test_report_prints_the_stored_total_query_for_the_whole_intervals_only(core: Core) -> None:
    core.counters(0, 0, {"10.45.0.2": 0}, {"10.45.0.2": 0})
    core.run("start")
    started_ten_minutes_ago(core)
    core.counters(10, 10, {"10.45.0.2": 10}, {"10.45.0.2": 10})
    core.run("end")
    out = core.run("report").stdout
    start, end = (Path(core.env["RATEL_WINDOW_DIR"]) / n for n in ("start", "end"))
    t0 = int(start.read_text().split()[0])
    t1 = int(end.read_text().split()[0])
    assert f"to_timestamp({t0 // 300 * 300})" in out and f"to_timestamp({t1 // 300 * 300})" in out


def test_report_before_both_snapshots_is_refused(core: Core) -> None:
    core.counters(1, 1, {"10.45.0.2": 1}, {"10.45.0.2": 1})
    core.run("start")
    result = core.run("report")
    assert result.returncode == 2 and "start, then end" in result.stderr


def test_a_counter_that_went_backwards_is_refused(core: Core) -> None:
    core.counters(1_000, 1_000, {"10.45.0.2": 900}, {"10.45.0.2": 900})
    core.run("start")
    started_ten_minutes_ago(core)
    core.counters(500, 500, {"10.45.0.2": 50}, {"10.45.0.2": 50})  # the host or the table was reset
    core.run("end")
    result = core.run("report")
    assert result.returncode == 2 and "went backwards" in result.stderr


def test_an_unknown_command_prints_the_usage(core: Core) -> None:
    for args in ([], ["now"]):
        result = core.run(*args)
        assert result.returncode == 2 and "ratel-window.sh start" in result.stderr


def test_the_snapshots_are_owner_only_and_nothing_is_changed_on_the_host(core: Core) -> None:
    core.counters(1, 1, {"10.45.0.2": 1}, {"10.45.0.2": 1})
    core.run("start")
    folder = Path(core.env["RATEL_WINDOW_DIR"])
    assert folder.stat().st_mode & 0o777 == 0o700
    text = SCRIPT.read_text()
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for forbidden in (
        "systemctl",
        "nft flush",
        "nft delete",
        "nft add",
        "rm -",
        "> /sys",
        "sysctl -w",
    ):
        assert forbidden not in code, forbidden
