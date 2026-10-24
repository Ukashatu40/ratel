"""The meter release builder carries its dependencies, only builds reviewed code, and the install
script uses them without the network."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash") or "bash"
GIT = shutil.which("git") or "git"
BUILD = ROOT / "scripts/release/build-meter-release.sh"
BUILD_ANY = ROOT / "scripts/release/build-release.sh"
INSTALL = ROOT / "deploy/core-up/install-release.sh"

# A pip that downloads nothing: it records its arguments and writes one fake wheel.
FAKE_PIP = """#!/usr/bin/env bash
set -eu
echo "$@" > "$FAKE_PIP_ARGS"
dest=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--dest" ]; then dest="$2"; fi
  shift
done
echo "not a real wheel" > "$dest/example-1.0-py3-none-any.whl"
"""


def _run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  (our own script and fixed arguments)
        [BASH, str(BUILD), *args],
        cwd=ROOT,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )


def _git(*args: str) -> str:
    return subprocess.run(  # noqa: S603  (git with fixed arguments)
        [GIT, *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def fake_pip(tmp_path: Path) -> tuple[Path, Path]:
    pip = tmp_path / "pip"
    pip.write_text(FAKE_PIP)
    pip.chmod(0o755)
    return pip, tmp_path / "pip-args.txt"


def test_the_release_holds_the_code_and_prebuilt_linux_wheels_and_nothing_else(
    tmp_path: Path, fake_pip: tuple[Path, Path]
) -> None:
    pip, args_file = fake_pip
    out = tmp_path / "out"
    result = _run(
        ["HEAD", str(out)],
        {"RATEL_PIP": str(pip), "FAKE_PIP_ARGS": str(args_file), "RATEL_RELEASE_BRANCH": "HEAD"},
    )
    assert result.returncode == 0, result.stderr
    [tarball] = out.glob("ratel-meter-*.tar.gz")
    assert re.search(r"[0-9a-f]{64}  ratel-meter-", result.stdout)

    with tarfile.open(tarball) as tar:
        names = tar.getnames()
    name = tarball.name.removesuffix(".tar.gz")
    assert f"{name}/services/meter_agent/main.py" in names
    assert f"{name}/requirements/constraints.txt" in names
    assert f"{name}/wheels/example-1.0-py3-none-any.whl" in names
    assert f"{name}/wheels.sha256" in names
    allowed = ("services/meter_agent", "services/common", "requirements", "wheels")
    for member in names:
        relative = member.removeprefix(name).lstrip("/")
        assert relative in ("", "services", "requirements") or relative.startswith(allowed), member
        assert "/._" not in member and not member.endswith(".env"), member

    # Only prebuilt wheels, for the Python and CPU core-up has, held to the pinned versions.
    args = args_file.read_text()
    for expected in ("--only-binary=:all:", "--python-version 3.12", "--abi cp312", "-c "):
        assert expected in args, expected
    assert "manylinux" in args and "x86_64" in args


def test_the_app_release_holds_the_app_and_installs_from_the_app_requirements(
    tmp_path: Path, fake_pip: tuple[Path, Path]
) -> None:
    pip, args_file = fake_pip
    out = tmp_path / "out"
    result = subprocess.run(  # noqa: S603  (our own script and fixed arguments)
        [BASH, str(BUILD_ANY), "app", "HEAD", str(out)],
        cwd=ROOT,
        env={
            **os.environ,
            "RATEL_PIP": str(pip),
            "FAKE_PIP_ARGS": str(args_file),
            "RATEL_RELEASE_BRANCH": "HEAD",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    [tarball] = out.glob("ratel-app-*.tar.gz")
    with tarfile.open(tarball) as tar:
        names = tar.getnames()
    name = tarball.name.removesuffix(".tar.gz")
    assert f"{name}/services/app/main.py" in names
    assert f"{name}/services/app/alembic.ini" in names
    assert not any(n.startswith(f"{name}/services/meter_agent") for n in names)
    assert f"{name}/wheels/example-1.0-py3-none-any.whl" in names
    assert "requirements/app.txt" in args_file.read_text()


def test_the_builder_refuses_an_unknown_component(tmp_path: Path) -> None:
    result = subprocess.run(  # noqa: S603  (our own script and fixed arguments)
        [BASH, str(BUILD_ANY), "ledger", "HEAD", str(tmp_path / "out")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Unknown component" in result.stderr
    assert not (tmp_path / "out").exists()


def test_the_builder_refuses_code_that_is_not_on_the_reviewed_branch(
    tmp_path: Path, fake_pip: tuple[Path, Path]
) -> None:
    pip, args_file = fake_pip
    root_commit = _git("rev-list", "--max-parents=0", "HEAD").split()[-1]
    head = _git("rev-parse", "HEAD").strip()
    if head == root_commit:
        pytest.skip("HEAD is the first commit: nothing older to compare against")
    result = _run(
        ["HEAD", str(tmp_path / "out")],
        {
            "RATEL_PIP": str(pip),
            "FAKE_PIP_ARGS": str(args_file),
            "RATEL_RELEASE_BRANCH": root_commit,
        },
    )
    assert result.returncode != 0
    assert "not on" in result.stderr
    assert not (tmp_path / "out").exists()
    assert not args_file.exists()  # it stopped before downloading anything


def test_the_install_script_uses_the_wheels_without_the_network_when_the_release_has_them() -> None:
    text = INSTALL.read_text()
    assert 'if [ -d "$release/wheels" ]; then' in text
    assert '--no-index --find-links "$release/wheels"' in text
    # Both ways still install only what the pinned requirements name.
    assert text.count('-c "$release/requirements/constraints.txt"') == 1
    assert "requirements/agent.txt" in text


def test_the_release_scripts_hold_no_secret_or_real_address() -> None:
    for script in (BUILD, BUILD_ANY, INSTALL, ROOT / "deploy/bss-app/install-release.sh"):
        text = script.read_text()
        assert script.stat().st_mode & 0o100, f"{script.name} must be executable"
        for pattern in (r"102\.214\.", r"172\.22\.", r"BEGIN [A-Z ]*PRIVATE KEY"):
            assert not re.search(pattern, text), f"{script.name} matches {pattern}"
