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
BUILD_DESK = ROOT / "scripts/release/build-desk.sh"
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


# An npm that downloads and builds nothing: it records how it was called and writes a tiny site.
FAKE_NPM = """#!/usr/bin/env bash
set -eu
echo "$1 ${2:-} mock=${VITE_USE_MOCK:-unset} api=${VITE_API_BASE_URL:-unset}" >> "$FAKE_NPM_LOG"
if [ "$1" = "run" ]; then
  mkdir -p dist/assets
  echo "<html></html>" > dist/index.html
  echo "body{}" > dist/assets/app.css
  mkdir -p dist/samples && echo "iccid" > dist/samples/sim-batch-ok.csv
fi
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
    assert f"{name}/web/pay/index.html" in names  # the page nginx serves at /pay
    assert not any(n.startswith(f"{name}/web/desk") for n in names)
    assert not any(n.startswith(f"{name}/services/meter_agent") for n in names)
    assert f"{name}/wheels/example-1.0-py3-none-any.whl" in names
    assert "requirements/app.txt" in args_file.read_text()


def test_the_link_release_holds_ratellink_and_its_requirements(
    tmp_path: Path, fake_pip: tuple[Path, Path]
) -> None:
    pip, args_file = fake_pip
    out = tmp_path / "out"
    result = subprocess.run(  # noqa: S603  (our own script and fixed arguments)
        [BASH, str(BUILD_ANY), "link", "HEAD", str(out)],
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
    [tarball] = out.glob("ratel-link-*.tar.gz")
    with tarfile.open(tarball) as tar:
        names = tar.getnames()
    name = tarball.name.removesuffix(".tar.gz")
    assert f"{name}/services/ratel_link/main.py" in names
    assert f"{name}/wheels/example-1.0-py3-none-any.whl" in names
    assert not any(n.startswith(f"{name}/services/meter_agent") for n in names)
    assert "requirements/link.txt" in args_file.read_text()


def test_the_core_cp_install_script_uses_the_wheels_without_the_network() -> None:
    text = (ROOT / "deploy/core-cp/install-release.sh").read_text()
    assert 'if [ -d "$release/wheels" ]; then' in text
    assert '--no-index --find-links "$release/wheels"' in text
    assert text.count('-c "$release/requirements/constraints.txt"') == 1


def _desk(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  (our own script and fixed arguments)
        [BASH, str(BUILD_DESK), *args],
        cwd=ROOT,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def fake_npm(tmp_path: Path) -> tuple[Path, Path]:
    npm = tmp_path / "npm"
    npm.write_text(FAKE_NPM)
    npm.chmod(0o755)
    return npm, tmp_path / "npm-calls.txt"


def test_the_desk_build_holds_only_the_built_files_and_is_made_for_the_real_api(
    tmp_path: Path, fake_npm: tuple[Path, Path]
) -> None:
    npm, log = fake_npm
    out = tmp_path / "out"
    # A developer's shell could carry these; the build must not.
    env = {
        "RATEL_NPM": str(npm),
        "FAKE_NPM_LOG": str(log),
        "RATEL_RELEASE_BRANCH": "HEAD",
        "VITE_USE_MOCK": "true",
        "VITE_API_BASE_URL": "http://elsewhere.invalid",
    }
    result = _desk(["HEAD", str(out)], env)
    assert result.returncode == 0, result.stderr
    [tarball] = out.glob("ratel-desk-*.tar.gz")
    assert re.search(r"[0-9a-f]{64}  ratel-desk-", result.stdout)
    with tarfile.open(tarball) as tar:
        names = tar.getnames()
    name = tarball.name.removesuffix(".tar.gz")
    assert f"{name}/index.html" in names and f"{name}/assets/app.css" in names
    for member in names:
        relative = member.removeprefix(name).lstrip("/")
        assert not relative.startswith(("src", "node_modules", "tests", ".env", "samples")), member
        assert "/._" not in member, member
    calls = log.read_text().splitlines()
    assert calls[0].startswith("ci ")  # locked packages, not a fresh resolve
    assert calls[1] == "run build mock=false api=unset"


def test_the_desk_build_refuses_code_that_is_not_on_the_reviewed_branch(
    tmp_path: Path, fake_npm: tuple[Path, Path]
) -> None:
    npm, log = fake_npm
    root_commit = _git("rev-list", "--max-parents=0", "HEAD").split()[-1]
    if _git("rev-parse", "HEAD").strip() == root_commit:
        pytest.skip("HEAD is the first commit: nothing older to compare against")
    result = _desk(
        ["HEAD", str(tmp_path / "out")],
        {"RATEL_NPM": str(npm), "FAKE_NPM_LOG": str(log), "RATEL_RELEASE_BRANCH": root_commit},
    )
    assert result.returncode != 0 and "not on" in result.stderr
    assert not (tmp_path / "out").exists() and not log.exists()  # it stopped before building


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
    for script in (
        BUILD,
        BUILD_ANY,
        BUILD_DESK,
        INSTALL,
        ROOT / "deploy/bss-app/install-release.sh",
        ROOT / "deploy/core-cp/install-release.sh",
    ):
        text = script.read_text()
        assert script.stat().st_mode & 0o100, f"{script.name} must be executable"
        for pattern in (r"102\.214\.", r"172\.22\.", r"BEGIN [A-Z ]*PRIVATE KEY"):
            assert not re.search(pattern, text), f"{script.name} matches {pattern}"
