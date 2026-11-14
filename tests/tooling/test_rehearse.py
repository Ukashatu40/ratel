"""The rehearsal runner: it reads and times the steps and writes the sheet, and touches no host."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/demo/rehearse.sh"
BASH = shutil.which("bash") or "bash"
STEPS = 24


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    # Anything that could touch a host is a fake that records it was called.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("ssh", "scp", "sudo", "systemctl", "curl"):
        tool = bin_dir / name
        tool.write_text(f'#!/usr/bin/env bash\necho {name} >> "{tmp_path}/touched.log"\n')
        tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}


def rehearse(
    env: dict[str, str], tmp_path: Path, answers: list[str], *args: str
) -> tuple[subprocess.CompletedProcess[str], str]:
    out = tmp_path / "record.md"
    stdin = "y\ny\n" + "".join(a + "\n" for a in answers)
    result = subprocess.run(  # noqa: S603  (our own script, fake host tools, scripted answers)
        [BASH, str(SCRIPT), "--out", str(out), *args],
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, out.read_text() if out.exists() else ""


def test_a_clean_run_of_three_people_counts_towards_the_gate(
    env: dict[str, str], tmp_path: Path
) -> None:
    result, record = rehearse(env, tmp_path, [""] * STEPS, "--people", "Ana, Bo, Chi")
    assert result.returncode == 0, result.stderr
    assert f"Steps done | {STEPS} of {STEPS}" in record
    assert "Steps marked R | 0" in record and "Steps marked F | 0" in record
    assert "Counts towards the Week 8 gate | yes" in record
    assert record.count("| ✓ |") == STEPS


def test_a_run_alone_is_recorded_but_does_not_count(env: dict[str, str], tmp_path: Path) -> None:
    _, record = rehearse(env, tmp_path, [""] * STEPS)
    assert "People | 1 (alone)" in record
    assert "Counts towards the Week 8 gate | no (fewer than three people)" in record


def test_a_repeated_step_is_marked_r_and_the_run_does_not_count(
    env: dict[str, str], tmp_path: Path
) -> None:
    answers = ["r", ""] + [""] * (STEPS - 1)
    _, record = rehearse(env, tmp_path, answers, "--people", "Ana, Bo, Chi")
    assert "Steps marked R | 1" in record
    first = next(line for line in record.splitlines() if line.startswith("| 1.1 "))
    assert "| R |" in first
    assert "Counts towards the Week 8 gate | no (1 step(s) repeated)" in record


def test_a_failed_step_keeps_what_happened_and_the_fallback(
    env: dict[str, str], tmp_path: Path
) -> None:
    answers = (
        [""] * 7 + ["f", "the call never rang; played the other direction"] + [""] * (STEPS - 8)
    )
    _, record = rehearse(env, tmp_path, answers, "--people", "Ana, Bo, Chi")
    assert "Steps marked F | 1" in record
    failed = next(line for line in record.splitlines() if "| F |" in line)
    assert "the call never rang; played the other direction" in failed
    assert "Counts towards the Week 8 gate | no (1 step(s) failed)" in record


def test_a_note_is_kept_on_its_step(env: dict[str, str], tmp_path: Path) -> None:
    answers = ["n", "page was slow", ""] + [""] * (STEPS - 1)
    _, record = rehearse(env, tmp_path, answers)
    first = next(line for line in record.splitlines() if line.startswith("| 1.1 "))
    assert "page was slow" in first and "| ✓ |" in first


def test_stopping_early_saves_what_there_is_and_never_counts(
    env: dict[str, str], tmp_path: Path
) -> None:
    result, record = rehearse(env, tmp_path, ["", "", "q"], "--people", "Ana, Bo, Chi")
    assert result.returncode == 0
    assert "Steps done | 2 of" in record and "stopped" in record
    assert "Counts towards the Week 8 gate | no (stopped early)" in record


def test_the_commands_are_shown_to_type_and_never_run(env: dict[str, str], tmp_path: Path) -> None:
    result, _ = rehearse(env, tmp_path, [""] * STEPS)
    assert "./ratel-window.sh start" in result.stdout  # shown as text
    assert "sudo systemctl start ratel-rating.service" in result.stdout
    assert not (
        tmp_path / "touched.log"
    ).exists()  # no ssh, scp, sudo, systemctl or curl was called


def test_every_step_of_the_sheet_is_in_the_runner() -> None:
    sheet = (SCRIPT.parents[2] / "docs/runbooks/rehearsal-sheet.md").read_text()
    runner = SCRIPT.read_text()
    ids = [
        f"{a}.{b}"
        for a, n in ((1, 6), (2, 3), (3, 4), (4, 4), (5, 4), (6, 3))
        for b in range(1, n + 1)
    ]
    for step in ids:
        assert f"| {step} |" in sheet, step
        assert f"S|{step}|" in runner, step
