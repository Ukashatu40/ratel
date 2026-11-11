"""The deploy tool: what it copies where, and that a release that does not come up is put back.

No host is touched. `ssh` and `scp` are fakes that record what they were asked, and the host's half
runs against a temporary folder with fake `systemctl`, `journalctl`, `curl` and `systemd-run`.
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / "scripts/deploy/deploy.sh"
REMOTE = ROOT / "scripts/deploy/remote/deploy-remote.sh"
BASH = shutil.which("bash") or "bash"

SHA_WRAPPER = '#!/bin/sh\nshasum -a 256 "$@" 2>/dev/null || sha256sum "$@"\n'


def script(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---- the laptop's half ----


@pytest.fixture
def laptop(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # ssh: print a private folder for `mktemp`, record everything, fail the host's half on request.
    script(
        bin_dir / "ssh",
        'echo "ssh $*" >> "$FAKE_LOG"\n'
        'case "${@: -1}" in mktemp*) echo /tmp/ratel-deploy.TEST;; esac\n'
        'case "$*" in *"sudo bash"*) exit "${FAKE_REMOTE_STATUS:-0}";; esac\n',
    )
    script(bin_dir / "scp", 'echo "scp $*" >> "$FAKE_LOG"\nexit "${FAKE_SCP_STATUS:-0}"\n')
    releases = tmp_path / "releases"
    releases.mkdir()
    return {
        **os.environ,
        "RATEL_SSH": str(bin_dir / "ssh"),
        "RATEL_SCP": str(bin_dir / "scp"),
        "RATEL_RELEASE_DIR": str(releases),
        "FAKE_LOG": str(tmp_path / "calls.log"),
        "HOME": str(tmp_path),
    }


def tarball(env: dict[str, str], name: str) -> Path:
    path = Path(env["RATEL_RELEASE_DIR"]) / name
    path.write_bytes(b"not a real release " + name.encode())
    return path


def deploy(env: dict[str, str], *args: str, answer: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  (our own script, fake ssh and scp, fixed arguments)
        [BASH, str(LOCAL), *args],
        env=env,
        input=answer,
        capture_output=True,
        text=True,
        check=False,
    )


def calls(env: dict[str, str]) -> str:
    log = Path(env["FAKE_LOG"])
    return log.read_text() if log.exists() else ""


def test_an_unknown_target_or_no_target_prints_the_usage(laptop: dict[str, str]) -> None:
    for args in ([], ["production"]):
        result = deploy(laptop, *args)
        assert result.returncode == 2 and "deploy.sh <app|desk|meter|calls>" in result.stderr
    assert calls(laptop) == ""


def test_a_dry_run_shows_the_plan_and_touches_no_host(laptop: dict[str, str]) -> None:
    tar = tarball(laptop, "ratel-meter-abc1234.tar.gz")
    result = deploy(laptop, "meter", "--tarball", str(tar), "--dry-run")
    assert result.returncode == 0
    assert (
        "ratelplus-core-up" in result.stdout
        and sha(tar) in result.stdout
        and "Dry run" in result.stdout
    )
    assert calls(laptop) == ""


def test_each_target_goes_to_its_own_host(laptop: dict[str, str]) -> None:
    expected = {
        "app": "ratelplus-bss-app",
        "desk": "ratelplus-bss-app",
        "meter": "ratelplus-core-up",
        "calls": "ratelplus-voice",
    }
    prefix = {
        "app": "ratel-app",
        "desk": "ratel-desk",
        "meter": "ratel-meter",
        "calls": "ratel-meter",
    }
    for target, host in expected.items():
        tar = tarball(laptop, f"{prefix[target]}-abc1234.tar.gz")
        out = deploy(laptop, target, "--tarball", str(tar), "--dry-run").stdout
        assert host in out, target
    tar = tarball(laptop, "ratel-meter-abc1234.tar.gz")
    out = deploy(
        {**laptop, "RATEL_HOST_CORE_UP": "lab-core"}, "meter", "--tarball", str(tar), "--dry-run"
    ).stdout
    assert "lab-core" in out


def test_nothing_is_done_without_a_yes(laptop: dict[str, str]) -> None:
    tar = tarball(laptop, "ratel-meter-abc1234.tar.gz")
    result = deploy(laptop, "meter", "--tarball", str(tar), answer="n\n")
    assert result.returncode == 1 and "nothing was done" in result.stderr
    assert calls(laptop) == ""


def test_a_deploy_copies_the_release_the_host_script_and_the_installer_then_runs_it_with_sudo(
    laptop: dict[str, str],
) -> None:
    tar = tarball(laptop, "ratel-meter-abc1234.tar.gz")
    result = deploy(laptop, "meter", "--tarball", str(tar), "--yes")
    assert result.returncode == 0, result.stderr
    log = calls(laptop)
    assert "mktemp -d /tmp/ratel-deploy.XXXXXX" in log
    [scp] = [line for line in log.splitlines() if line.startswith("scp ")]
    assert str(tar) in scp and "deploy-remote.sh" in scp and "install-release.sh" in scp
    assert "ratelplus-core-up:/tmp/ratel-deploy.TEST/" in scp
    [run] = [line for line in log.splitlines() if "sudo bash" in line]
    assert " -t " in run
    assert (
        f"deploy-remote.sh meter ratel-meter-abc1234.tar.gz {sha(tar)} "
        "'/opt/python-3.12/bin/python3.12'" in run
    )
    entry = (Path(laptop["RATEL_RELEASE_DIR"]) / "deploy-log.tsv").read_text().split("\t")
    assert entry[1:] == ["meter", "ratelplus-core-up", "abc1234", "ok\n"]


def test_the_desk_has_no_installer_and_the_app_uses_the_system_python(
    laptop: dict[str, str],
) -> None:
    desk = tarball(laptop, "ratel-desk-abc1234.tar.gz")
    deploy(laptop, "desk", "--tarball", str(desk), "--yes")
    assert "install-release.sh" not in calls(laptop)
    app = tarball(laptop, "ratel-app-abc1234.tar.gz")
    deploy(laptop, "app", "--tarball", str(app), "--yes")
    assert "'python3.12'" in calls(laptop)


def test_a_failed_deploy_exits_non_zero_and_is_logged_as_failed(laptop: dict[str, str]) -> None:
    tar = tarball(laptop, "ratel-meter-abc1234.tar.gz")
    result = deploy({**laptop, "FAKE_REMOTE_STATUS": "1"}, "meter", "--tarball", str(tar), "--yes")
    assert result.returncode == 1 and "FAILED" in result.stderr
    assert "FAILED(1)" in (Path(laptop["RATEL_RELEASE_DIR"]) / "deploy-log.tsv").read_text()


def test_a_failed_copy_stops_before_anything_runs_on_the_host(laptop: dict[str, str]) -> None:
    tar = tarball(laptop, "ratel-meter-abc1234.tar.gz")
    result = deploy({**laptop, "FAKE_SCP_STATUS": "1"}, "meter", "--tarball", str(tar), "--yes")
    assert result.returncode == 1 and "copy to ratelplus-core-up failed" in result.stderr
    assert "sudo bash" not in calls(laptop)


def test_a_missing_tarball_is_refused(laptop: dict[str, str]) -> None:
    result = deploy(laptop, "meter", "--tarball", "/nonexistent/ratel-meter-x.tar.gz", "--yes")
    assert result.returncode == 1 and "no such file" in result.stderr


# ---- the host's half ----


class Host:
    """A fake host: folders under tmp_path, fake systemctl, journalctl, curl and systemd-run."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.work = tmp_path / "work"
        self.work.mkdir()
        self.app = tmp_path / "opt-app"
        self.meter = tmp_path / "opt-meter"
        self.www = tmp_path / "www"
        self.log = tmp_path / "deploy.log"
        self.systemctl_log = tmp_path / "systemctl.log"
        self.journal = tmp_path / "journal.txt"
        self.journal.write_text('{"event":"meter.agent.started"}\n')
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        script(bin_dir / "systemctl", 'echo "$*" >> "$SYSTEMCTL_LOG"\n')
        script(bin_dir / "journalctl", 'cat "$JOURNAL_FILE"\n')
        script(
            bin_dir / "curl",
            'case "$*" in *"-w"*) echo "${FAKE_READY_CODE:-200}";; esac\n'
            'exit "${FAKE_CURL_STATUS:-0}"\n',
        )
        script(bin_dir / "systemd-run", 'exit "${FAKE_MIGRATION_STATUS:-0}"\n')
        (bin_dir / "sha").write_text(SHA_WRAPPER)
        (bin_dir / "sha").chmod(0o755)
        self.bin = bin_dir
        self.env = {
            **os.environ,
            "RATEL_DEPLOY_APP_BASE": str(self.app),
            "RATEL_DEPLOY_METER_BASE": str(self.meter),
            "RATEL_DEPLOY_WWW": str(self.www),
            "RATEL_DEPLOY_LOG": str(self.log),
            "RATEL_DEPLOY_WAIT": "1",
            "RATEL_DEPLOY_KEEP": "1",
            "RATEL_DEPLOY_SYSTEMCTL": str(bin_dir / "systemctl"),
            "RATEL_DEPLOY_JOURNALCTL": str(bin_dir / "journalctl"),
            "RATEL_DEPLOY_CURL": str(bin_dir / "curl"),
            "RATEL_DEPLOY_SYSTEMD_RUN": str(bin_dir / "systemd-run"),
            "RATEL_DEPLOY_SHA256": str(bin_dir / "sha"),
            "SYSTEMCTL_LOG": str(self.systemctl_log),
            "JOURNAL_FILE": str(self.journal),
        }

    def running(self, base: Path, release: str = "old") -> Path:
        """A release already installed and running."""
        (base / "releases" / release).mkdir(parents=True)
        (base / "current").symlink_to(base / "releases" / release)
        return base / "releases" / release

    def installer(self, base: Path, new: str = "new") -> None:
        """What install-release.sh does: unpack, and point `current` at the new release."""
        script(
            self.work / "install-release.sh",
            f'mkdir -p "{base}/releases/{new}"\nln -sfn "{base}/releases/{new}" "{base}/current"\n',
        )

    def tarball(self, name: str, desk: bool = False, index: bool = True) -> str:
        path = self.work / name
        with tarfile.open(path, "w:gz") as tar:
            if desk and index:
                data = b"<html></html>"
                info = tarfile.TarInfo(f"{name[:-7]}/index.html")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            elif desk:
                data = b"x"
                info = tarfile.TarInfo(f"{name[:-7]}/readme.txt")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            else:
                data = b"x"
                info = tarfile.TarInfo("x")
                info.size = 1
                tar.addfile(info, io.BytesIO(data))
        return sha(path)

    def run(
        self, target: str, tar: str, checksum: str, **env: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603  (our own script, fake commands, a temporary folder)
            [BASH, str(REMOTE), target, tar, checksum, "python3.12", str(self.work)],
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )

    def current(self, base: Path) -> str:
        return os.readlink(base / "current").rsplit("/", 1)[-1]

    def restarts(self) -> list[str]:
        if not self.systemctl_log.exists():
            return []
        return self.systemctl_log.read_text().splitlines()


@pytest.fixture
def host(tmp_path: Path) -> Host:
    return Host(tmp_path)


def test_a_meter_release_that_comes_up_is_kept(host: Host) -> None:
    host.running(host.meter)
    host.installer(host.meter)
    checksum = host.tarball("ratel-meter-new.tar.gz")
    result = host.run("meter", "ratel-meter-new.tar.gz", checksum)
    assert result.returncode == 0, result.stdout + result.stderr
    assert host.current(host.meter) == "new"
    assert host.restarts() == ["restart ratel-meter.service"]
    assert "old -> new ok" in host.log.read_text()


def test_the_call_agent_is_a_different_unit(host: Host) -> None:
    host.running(host.meter)
    host.installer(host.meter)
    checksum = host.tarball("ratel-meter-new.tar.gz")
    assert host.run("calls", "ratel-meter-new.tar.gz", checksum).returncode == 0
    assert host.restarts() == ["restart ratel-meter-calls.service"]


@pytest.mark.parametrize(
    "failure", ["meter.agent.tick_error", "meter.counters.nft_failed", "Traceback"]
)
def test_an_agent_that_logs_a_failure_after_the_restart_is_rolled_back(
    host: Host, failure: str
) -> None:
    host.running(host.meter)
    host.installer(host.meter)
    host.journal.write_text('{"event":"meter.agent.started"}\n' + failure + "\n")
    checksum = host.tarball("ratel-meter-new.tar.gz")
    result = host.run("meter", "ratel-meter-new.tar.gz", checksum)
    assert result.returncode == 1 and "rolled back" in result.stdout
    assert host.current(host.meter) == "old"
    assert (
        host.restarts() == ["restart ratel-meter.service"] * 2
    )  # the new one, then the old one again
    assert "FAILED" in host.log.read_text()


def test_an_agent_that_never_says_it_started_is_rolled_back(host: Host) -> None:
    host.running(host.meter)
    host.installer(host.meter)
    host.journal.write_text("")
    checksum = host.tarball("ratel-meter-new.tar.gz")
    assert host.run("meter", "ratel-meter-new.tar.gz", checksum).returncode == 1
    assert host.current(host.meter) == "old"


def test_a_damaged_copy_is_refused_before_anything_is_installed(host: Host) -> None:
    host.running(host.meter)
    host.installer(host.meter)
    host.tarball("ratel-meter-new.tar.gz")
    result = host.run("meter", "ratel-meter-new.tar.gz", "0" * 64)
    assert result.returncode == 1 and "checksum" in result.stdout
    assert host.current(host.meter) == "old" and host.restarts() == []


def test_a_first_install_that_fails_says_there_is_nothing_to_put_back(host: Host) -> None:
    host.installer(host.meter)
    host.journal.write_text("meter.agent.tick_error\n")
    checksum = host.tarball("ratel-meter-new.tar.gz")
    result = host.run("meter", "ratel-meter-new.tar.gz", checksum)
    assert result.returncode == 1 and "no previous release" in result.stdout


def test_an_app_release_is_migrated_restarted_and_checked(host: Host) -> None:
    host.running(host.app)
    host.installer(host.app)
    checksum = host.tarball("ratel-app-new.tar.gz")
    result = host.run("app", "ratel-app-new.tar.gz", checksum)
    assert result.returncode == 0, result.stdout + result.stderr
    assert host.current(host.app) == "new" and host.restarts() == ["restart ratel-app.service"]


def test_a_failed_migration_puts_the_old_release_back_and_never_restarts(host: Host) -> None:
    host.running(host.app)
    host.installer(host.app)
    checksum = host.tarball("ratel-app-new.tar.gz")
    result = host.run("app", "ratel-app-new.tar.gz", checksum, FAKE_MIGRATION_STATUS="1")
    assert result.returncode == 1 and "migration failed" in result.stdout
    assert host.current(host.app) == "old" and host.restarts() == []


@pytest.mark.parametrize("env", [{"FAKE_CURL_STATUS": "22"}, {"FAKE_READY_CODE": "503"}])
def test_an_app_that_does_not_answer_is_rolled_back_with_a_note_about_the_migration(
    host: Host, env: dict[str, str]
) -> None:
    host.running(host.app)
    host.installer(host.app)
    checksum = host.tarball("ratel-app-new.tar.gz")
    result = host.run("app", "ratel-app-new.tar.gz", checksum, **env)
    assert result.returncode == 1 and "rolled back" in result.stdout
    assert "migration was applied and is not undone" in result.stdout
    assert host.current(host.app) == "old"
    assert host.restarts() == ["restart ratel-app.service"] * 2


def test_the_desk_is_unpacked_and_the_link_switched(host: Host) -> None:
    host.www.mkdir()
    (host.www / "desk-releases" / "ratel-desk-old").mkdir(parents=True)
    (host.www / "ratel-desk").symlink_to(host.www / "desk-releases" / "ratel-desk-old")
    checksum = host.tarball("ratel-desk-new.tar.gz", desk=True)
    result = host.run("desk", "ratel-desk-new.tar.gz", checksum)
    assert result.returncode == 0, result.stdout + result.stderr
    assert os.readlink(host.www / "ratel-desk").endswith("ratel-desk-new")
    assert (host.www / "ratel-desk" / "index.html").read_text() == "<html></html>"


def test_a_desk_without_an_index_is_put_back(host: Host) -> None:
    host.www.mkdir()
    (host.www / "desk-releases" / "ratel-desk-old").mkdir(parents=True)
    (host.www / "ratel-desk").symlink_to(host.www / "desk-releases" / "ratel-desk-old")
    checksum = host.tarball("ratel-desk-new.tar.gz", desk=True, index=False)
    result = host.run("desk", "ratel-desk-new.tar.gz", checksum)
    assert result.returncode == 1 and "no index.html" in result.stdout
    assert os.readlink(host.www / "ratel-desk").endswith("ratel-desk-old")


def test_the_host_script_never_edits_settings_nginx_or_the_firewall() -> None:
    code = [
        line
        for line in (REMOTE.read_text() + LOCAL.read_text()).splitlines()
        if not line.lstrip().startswith("#")  # the comments say what it does not do
    ]
    text = "\n".join(code)
    for forbidden in (
        "nginx",
        "nft ",
        "/etc/ratel-app/ratel-app.env",
        "ratel-meter.env",
        "rm -rf /",
        "DROP TABLE",
    ):
        assert forbidden not in text, forbidden
    assert "set -euo pipefail" in text
