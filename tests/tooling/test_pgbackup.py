"""The nightly PostgreSQL dump: only good dumps are kept, none deleted before a good one exists."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy/bss-app"
SCRIPT = DEPLOY / "ratel-pgbackup.sh"
BASH = shutil.which("bash") or "bash"

# A pg_dump that writes a tiny file (or fails), and a pg_restore that accepts it (or refuses).
FAKE_PG_DUMP = """#!/usr/bin/env bash
[ "${FAKE_DUMP_FAILS:-0}" = 1 ] && exit 1
for arg in "$@"; do case "$arg" in --file=*) out="${arg#--file=}";; esac; done
echo "not a real dump" > "$out"
"""
FAKE_PG_RESTORE = """#!/usr/bin/env bash
[ "${FAKE_RESTORE_FAILS:-0}" = 1 ] && exit 1
exit 0
"""


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("pg_dump", FAKE_PG_DUMP), ("pg_restore", FAKE_PG_RESTORE)):
        tool = bin_dir / name
        tool.write_text(body)
        tool.chmod(0o755)
    backups = tmp_path / "backups"
    backups.mkdir()
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "RATEL_BACKUP_DIR": str(backups),
    }


def run(env: dict[str, str], **extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  (our own script, fake tools, fixed arguments)
        [BASH, str(SCRIPT)], env={**env, **extra}, capture_output=True, text=True, check=False
    )


def dumps(env: dict[str, str]) -> list[str]:
    return sorted(p.name for p in Path(env["RATEL_BACKUP_DIR"]).iterdir())


def old_dump(env: dict[str, str], name: str, age_days: int) -> None:
    path = Path(env["RATEL_BACKUP_DIR"]) / name
    path.write_text("old")
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))


def test_a_good_dump_is_written_under_its_final_name_with_no_partial_left(
    env: dict[str, str],
) -> None:
    result = run(env)
    assert result.returncode == 0, result.stderr
    [name] = dumps(env)
    assert re.fullmatch(r"ratel_bss-\d{8}T\d{6}Z\.dump", name)
    assert "wrote" in result.stdout and "1 kept" in result.stdout
    mode = (Path(env["RATEL_BACKUP_DIR"]) / name).stat().st_mode & 0o777
    assert mode == 0o600  # owner only


def test_only_the_newest_n_dumps_are_kept(env: dict[str, str]) -> None:
    for days, name in enumerate(
        [
            "ratel_bss-20261030T000000Z.dump",
            "ratel_bss-20261029T000000Z.dump",
            "ratel_bss-20261028T000000Z.dump",
            "ratel_bss-20261027T000000Z.dump",
        ],
        start=1,
    ):
        old_dump(env, name, days)  # fmt: skip
    result = run(env, RATEL_BACKUP_KEEP="3")
    assert result.returncode == 0, result.stderr
    kept = dumps(env)
    assert len(kept) == 3
    assert (
        "ratel_bss-20261027T000000Z.dump" not in kept
        and "ratel_bss-20261028T000000Z.dump" not in kept
    )
    assert "ratel_bss-20261030T000000Z.dump" in kept and "ratel_bss-20261029T000000Z.dump" in kept


@pytest.mark.parametrize("failure", ["FAKE_DUMP_FAILS", "FAKE_RESTORE_FAILS"])
def test_a_failed_or_unreadable_dump_is_not_kept_and_deletes_nothing(
    env: dict[str, str], failure: str
) -> None:
    old_dump(env, "ratel_bss-20261030T000000Z.dump", 1)
    old_dump(env, "ratel_bss-20261029T000000Z.dump", 2)
    result = run(env, **{failure: "1"}, RATEL_BACKUP_KEEP="1")
    assert result.returncode != 0
    assert dumps(env) == [
        "ratel_bss-20261029T000000Z.dump",
        "ratel_bss-20261030T000000Z.dump",
    ]  # no .partial, no deletion


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("RATEL_DB", "bss; drop table x"),
        ("RATEL_DB", "../etc"),
        ("RATEL_BACKUP_KEEP", "0"),
        ("RATEL_BACKUP_KEEP", "many"),
    ],
)
def test_odd_settings_are_refused_before_anything_runs(
    env: dict[str, str], setting: str, value: str
) -> None:
    result = run(env, **{setting: value})
    assert result.returncode == 1 and "refused" in result.stderr
    assert dumps(env) == []


def test_a_missing_folder_is_refused(env: dict[str, str], tmp_path: Path) -> None:
    result = run(env, RATEL_BACKUP_DIR=str(tmp_path / "nowhere"))
    assert result.returncode == 1 and "does not exist" in result.stderr


def test_the_script_prints_no_data_and_dumps_the_whole_database_in_one_command() -> None:
    text = SCRIPT.read_text()
    assert SCRIPT.stat().st_mode & 0o100, "must be executable"
    assert "set -euo pipefail" in text and "umask 077" in text
    assert text.count("pg_dump ") == 1 and "psql" not in text and "SELECT" not in text
    assert "--format=custom" in text and "pg_restore --list" in text
    # Old dumps are deleted only after the new one is in place.
    assert text.index("mv --") < text.index('then rm -f -- "$old"')


def test_the_service_runs_the_installed_script_as_postgres_with_one_writable_folder() -> None:
    service = (DEPLOY / "ratel-pgbackup.service").read_text()
    assert "\nType=oneshot\n" in service and "\nUser=postgres\n" in service
    assert "ExecStart=/usr/local/sbin/ratel-pgbackup\n" in service
    assert "ReadWritePaths=/var/backups/ratel-bss" in service
    assert "\nCapabilityBoundingSet=\n" in service and "\nAmbientCapabilities=\n" in service
    assert "ProtectSystem=strict" in service and "RestrictAddressFamilies=AF_UNIX" in service
    app_unit = (DEPLOY / "ratel-app.service").read_text()
    for line in (
        ln for ln in app_unit.splitlines() if re.match(r"^(Protect|Private|Restrict)\w+=", ln)
    ):
        key = line.split("=")[0]
        assert key + "=" in service, f"the backup unit lacks {key}, which the app unit has"


def test_the_timer_catches_up_after_a_power_cut_and_the_readme_installs_it() -> None:
    timer = (DEPLOY / "ratel-pgbackup.timer").read_text()
    assert "Unit=ratel-pgbackup.service" in timer and "OnCalendar=daily" in timer
    assert "\nPersistent=true\n" in timer and "WantedBy=timers.target" in timer
    readme = (DEPLOY / "README.md").read_text()
    for needle in (
        "ratel-pgbackup.sh",
        "ratel-pgbackup.service",
        "ratel-pgbackup.timer",
        "systemctl enable --now ratel-pgbackup.timer",
        "/var/backups/ratel-bss",
    ):
        assert needle in readme, needle
    assert "same VM" in readme and "restore" in readme.lower()
