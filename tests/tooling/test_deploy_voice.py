"""The voice VM's call agent: numbers-only export, an exact sudo rule, a wired unit."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy/voice"
EXPORT = DEPLOY / "ratel-call-export.sh"
BASH = shutil.which("bash") or "bash"

# A docker that records the SQL it was given and prints one tab-separated row per table.
FAKE_DOCKER = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$FAKE_DOCKER_ARGS"
printf 'acc\\t1\\tINVITE\\t200\\tc1\\ttag\\t2348000000001\\t08000000002\\t1794700006\\t0\\n'
"""


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FAKE_DOCKER_ARGS": str(tmp_path / "args.txt"),
    }


def export(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  (our own script, a fake docker, fixed arguments)
        [BASH, str(EXPORT), *args], env=env, capture_output=True, text=True, check=False
    )


def test_the_export_asks_for_rows_after_the_ids_and_older_than_the_settle_time(
    env: dict[str, str],
) -> None:
    result = export(env, "--after-acc", "41", "--after-missed", "12", "--settle", "10")
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(
        "acc\t1\tINVITE\t200\tc1\t"
    )  # the database's rows, passed on as they are
    args = Path(env["FAKE_DOCKER_ARGS"]).read_text()
    assert "id > 41" in args and "id > 12" in args and "INTERVAL 10 SECOND" in args
    assert args.count("LIMIT 5000") == 2 and "FROM acc" in args and "FROM missed_calls" in args


@pytest.mark.parametrize(
    "bad",
    [
        [],
        ["--after-acc", "1", "--after-missed", "2"],
        ["--after-acc", "1", "--after-missed", "2", "--settle", "3", "--extra", "4"],
        ["--after-acc", "1; DROP TABLE acc", "--after-missed", "2", "--settle", "3"],
        ["--after-acc", "1", "--after-missed", "2 OR 1=1", "--settle", "3"],
        ["--after-acc", "-1", "--after-missed", "2", "--settle", "3"],
        ["--after-acc", "", "--after-missed", "2", "--settle", "3"],
        ["--after-acc", "1", "--after-missed", "2", "--settle", "0x10"],
        ["--after-missed", "1", "--after-acc", "2", "--settle", "3"],  # wrong order
        ["--after-acc", "1234567890123", "--after-missed", "2", "--settle", "3"],  # too long
    ],
)
def test_anything_but_three_whole_numbers_is_refused_before_the_database_is_touched(
    env: dict[str, str], bad: list[str]
) -> None:
    result = export(env, *bad)
    assert result.returncode == 2 and "usage" in result.stderr
    assert not Path(env["FAKE_DOCKER_ARGS"]).exists()  # docker was never run


def test_the_export_reads_only_the_two_tables_and_only_by_name_of_column() -> None:
    text = EXPORT.read_text()
    assert EXPORT.stat().st_mode & 0o100, "must be executable"
    assert "set -euo pipefail" in text and "SELECT *" not in text and text.count("SELECT ") == 2
    assert not re.search(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT)\b", text.split("exec docker")[1]
    )


def test_the_sudo_rule_names_one_script_and_has_no_wildcard() -> None:
    rules = [
        ln
        for ln in (DEPLOY / "sudoers-ratel-meter.example").read_text().splitlines()
        if ln and not ln.startswith("#")
    ]
    assert rules == ["ratelmeter ALL=(root) NOPASSWD: /usr/local/sbin/ratel-call-export"]


def test_the_unit_runs_call_mode_as_the_service_user_and_says_why_it_is_less_hardened() -> None:
    unit = (DEPLOY / "ratel-meter-calls.service").read_text()
    assert (
        "\nUser=ratelmeter\n" in unit
        and "EnvironmentFile=/etc/ratel-meter/ratel-meter-calls.env" in unit
    )
    assert "meter_agent.main --mode call\n" in unit
    assert "\nNoNewPrivileges=no\n" in unit and "no new privileges" in unit  # and why
    assert "ReadWritePaths=/var/spool/ratel-meter" in unit and "ProtectSystem=full" in unit
    # Options that make `sudo` refuse on the voice VM (tested 2026-11-03) must not come back.
    for option in (
        "PrivateDevices", "ProtectKernelTunables", "ProtectKernelModules", "ProtectKernelLogs",
        "ProtectClock", "ProtectHostname", "RestrictNamespaces", "RestrictRealtime",
        "LockPersonality",
    ):  # fmt: skip
        assert f"\n{option}=" not in unit, option
    assert "WantedBy=multi-user.target" in unit


def test_the_env_example_holds_placeholders_and_the_settings_the_agent_reads() -> None:
    text = (DEPLOY / "ratel-meter-calls.env.example").read_text()
    assert "METER_AGENT_API_KEY=CHANGE_ME" in text and "SSL_CERT_FILE=" in text
    from services.meter_agent.config import CallSettings

    names = {f"METER_AGENT_{n.upper()}" for n in CallSettings.model_fields}
    active = {ln.split("=")[0] for ln in text.splitlines() if ln and not ln.startswith("#")}
    assert (active - {"SSL_CERT_FILE"}) <= names, "an env line the agent does not read"
    assert {
        "METER_AGENT_CALL_EXPORT_COMMAND",
        "METER_AGENT_CALL_OPEN_MAX_SECONDS",
        "METER_AGENT_API_KEY",
    } <= active


def test_the_readme_covers_the_install_and_the_failures() -> None:
    readme = (DEPLOY / "README.md").read_text()
    for needle in (
        "visudo -cf",
        "meter.calls.assembled",
        "location = /v1/calls",
        "python3.12",
        "--mode call --once",
        "DROP TABLE",
    ):
        assert needle in readme, needle


def test_nothing_in_the_folder_holds_a_secret_or_a_real_address() -> None:
    for path in DEPLOY.iterdir():
        body = path.read_text()
        assert not re.search(
            r"BEGIN [A-Z ]*PRIVATE KEY|rlk_[a-z0-9-]+\.[A-Za-z0-9_-]{20,}", body
        ), path.name
        assert not re.search(r"\b(?:102\.214|172\.22)\.", body), path.name
        assert not re.search(
            r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", body.replace("127.0.0.1", "")
        ), path.name
