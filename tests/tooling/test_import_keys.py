"""The laptop script that imports chosen SIMs' keys into RatelLink.

Right rows, nothing shown, nothing on a command line. `ssh` is a fake that runs the remote
command here, and `curl` a fake that records what RatelLink would have received, so the quoting
of the remote command is tested as it runs. Every key below is made up for the test.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/sims/import-keys.sh"
BASH = shutil.which("bash") or "bash"
TOKEN = "test-caller-key-not-real-0123456789abcdef"
HEADER = "INDEX,IMSI,UeAMRDL(bps),UeAMRUL(bps),AMF,USIMKI,USIMOPC,Status"


def sim(index: int, last_four: str) -> tuple[str, str, str]:
    imsi = f"62100000000{last_four}"
    return imsi, f"{index:02d}" * 16, f"{index + 50:02d}" * 16


def row(index: int, last_four: str) -> str:
    imsi, ki, opc = sim(index, last_four)
    return f"{index},{imsi},0,0,8000,{ki},{opc},0"


@pytest.fixture
def lab(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tools = {
        # ssh -T <host> <remote command>: run the remote command here, as a login shell would.
        "ssh": (
            "#!/usr/bin/env bash\n"
            f'printf "%s\\n" "$*" >> "{tmp_path}/ssh-args.log"\n'
            'shift 2\nexec bash -c "$1"\n'
        ),
        # curl: keep the header from --config and the body from stdin; answer with FAKE_CODE.
        "curl": (
            "#!/usr/bin/env bash\n"
            "while [ $# -gt 0 ]; do\n"
            '  if [ "$1" = --config ]; then cfg="$(cat "$2")"; shift; fi; shift\n'
            "done\n"
            f'printf "%s\\t%s\\n" "$cfg" "$(cat)" >> "{tmp_path}/received.log"\n'
            'printf "%s\\n" "${FAKE_CODE:-200}"\n'
        ),
    }
    for name, body in tools.items():
        tool = bin_dir / name
        tool.write_text(body)
        tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    (tmp_path / "sims.csv").write_text(
        "\n".join([HEADER, row(1, "0454"), row(2, "0455"), row(3, "0456")]) + "\n"
    )
    return tmp_path


def run(
    lab: Path, *fours: str, code: str = "200", token: str = TOKEN, **extra: str
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{lab / 'bin'}:{os.environ['PATH']}",
        "RATEL_SIMS_FILE": str(lab / "sims.csv"),
        "FAKE_CODE": code,
        **extra,
    }
    return subprocess.run(  # noqa: S603  (our own script, fake ssh and curl, made-up keys)
        [BASH, str(SCRIPT), *fours],
        env=env,
        input=token + "\n",
        capture_output=True,
        text=True,
        check=False,
    )


def received(lab: Path) -> list[tuple[str, dict[str, str]]]:
    log = lab / "received.log"
    if not log.exists():
        return []
    out = []
    for line in log.read_text().splitlines():
        header, body = line.split("\t")
        out.append((header, json.loads(body)))
    return out


def test_one_sim_reaches_ratellink_with_the_caller_key(lab: Path) -> None:
    result = run(lab, "0455")
    assert result.returncode == 0, result.stderr
    assert "…0455  imported (200)" in result.stdout
    imsi, ki, opc = sim(2, "0455")
    assert received(lab) == [
        (f'header = "Authorization: Bearer {TOKEN}"', {"imsi": imsi, "ki": ki, "opc": opc})
    ]


def test_no_key_and_no_caller_key_is_shown_or_on_a_command_line(lab: Path) -> None:
    result = run(lab, "0455", "0456")
    shown = result.stdout + result.stderr
    ssh_args = (lab / "ssh-args.log").read_text()
    for value in (TOKEN, *sim(2, "0455"), *sim(3, "0456")):
        assert value not in shown
        assert value not in ssh_args


def test_several_sims_are_reported_in_order(lab: Path) -> None:
    result = run(lab, "0456", "0454")
    assert result.returncode == 0
    assert result.stdout.index("…0456") < result.stdout.index("…0454")
    assert [body["imsi"] for _, body in received(lab)] == [sim(3, "0456")[0], sim(1, "0454")[0]]


def test_a_sim_with_no_row_stops_everything_before_anything_is_sent(lab: Path) -> None:
    result = run(lab, "0455", "9999")
    assert result.returncode == 1
    assert "9999 matches 0 rows" in result.stderr
    assert received(lab) == [] and not (lab / "ssh-args.log").exists()


def test_two_rows_for_the_same_last_four_are_refused(lab: Path) -> None:
    with (lab / "sims.csv").open("a") as f:
        f.write(row(4, "0455").replace("621000000000455", "621009999990455") + "\n")
    result = run(lab, "0455")
    assert result.returncode == 1 and "0455 matches 2 rows" in result.stderr
    assert received(lab) == []


def test_a_malformed_key_is_refused_before_anything_is_sent(lab: Path) -> None:
    text = (lab / "sims.csv").read_text().replace(sim(2, "0455")[1], "not-hex")
    (lab / "sims.csv").write_text(text)
    result = run(lab, "0455")
    assert result.returncode == 1 and "not 32 hex characters" in result.stderr
    assert received(lab) == []


def test_windows_line_endings_in_the_key_file_are_read(lab: Path) -> None:
    (lab / "sims.csv").write_text((lab / "sims.csv").read_text().replace("\n", "\r\n"))
    result = run(lab, "0455")
    assert result.returncode == 0, result.stderr
    assert received(lab)[0][1]["opc"] == sim(2, "0455")[2]


@pytest.mark.parametrize(
    ("code", "word"), [("409", "REFUSED (409)"), ("401", "REFUSED (401)"), ("500", "FAILED (500)")]
)
def test_a_refusal_is_reported_and_the_exit_code_says_so(lab: Path, code: str, word: str) -> None:
    result = run(lab, "0455", code=code)
    assert result.returncode == 1
    assert word in result.stdout


def test_no_caller_key_sends_nothing(lab: Path) -> None:
    result = run(lab, "0455", token="")
    assert result.returncode == 2 and "no caller key" in result.stderr
    assert received(lab) == []


def test_only_a_local_ratellink_address_is_accepted(lab: Path) -> None:
    result = run(lab, "0455", RATEL_LINK_URL="https://example.test")
    assert result.returncode == 2 and received(lab) == []


def test_a_bad_argument_is_refused(lab: Path) -> None:
    assert run(lab, "455").returncode == 2
    assert run(lab, "04555").returncode == 2
