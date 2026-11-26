"""The script that serves RatelDesk publicly under its own name (decision 61)."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/bss-app/nginx/make-desk-public.py"
TEMPLATE = (ROOT / "deploy/bss-app/nginx/ratel-app.conf.example").read_text()
NAME = "desk.example.org"
OFFICE = "198.51.100.0/24"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("make_desk_public", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # No bytecode next to the script: the deploy folder is scanned for secrets as text.
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = keep
    return module


tool = _load()


def _live() -> str:
    """A live file: the template with its placeholders replaced by example values."""
    values = {
        "<name-of-this-host>": "bss.example.test",
        "<address-of-core-up>": "192.0.2.10",
        "<address-of-voice-vm>": "192.0.2.11",
        "<office-and-vpn-range>": OFFICE,
    }
    text = TEMPLATE
    for key, value in values.items():
        text = text.replace(key, value)
    return re.sub(r"<paystack-address-\d>", "192.0.2.50", text)


def _block(text: str, header: str) -> str:
    return tool._block(text, header).group(0)


def _blocks(text: str) -> dict[str, str]:
    headers = re.findall(r"\n    location (.+?) \{\n", text)
    return {header: _block(text, header) for header in headers}


def test_acme_adds_only_a_plain_http_server_for_the_name() -> None:
    live = _live()
    out = tool.add_acme(live, NAME)
    assert out.replace(tool.acme_block(NAME), "", 1) == live
    assert f"listen 80;\n    server_name {NAME};" in out
    assert "return 301 https://$host$request_uri;" in out
    assert "root /var/www/letsencrypt;" in out


def test_acme_twice_changes_nothing_the_second_time() -> None:
    once = tool.add_acme(_live(), NAME)
    assert tool.add_acme(once, NAME) == once


def test_public_opens_the_desk_sign_in_and_staff_api_only() -> None:
    before = _blocks(_live())
    after = _blocks(tool.make_public(_live(), NAME))
    assert before.keys() == after.keys()
    for header in ("/", "= /v1/auth/login", "/v1/"):
        assert "allow " not in after[header] and "deny " not in after[header]
        assert "decision 61" in after[header]
    for header in before.keys() - {"/", "= /v1/auth/login", "/v1/"}:
        assert after[header] == before[header], header


@pytest.mark.parametrize(
    "header", ["/v1/usage", "= /v1/calls", "= /healthz", "= /v1/pay/webhooks/paystack"]
)
def test_machine_and_local_paths_stay_closed(header: str) -> None:
    block = _block(tool.make_public(_live(), NAME), header)
    assert "deny  all;" in block


def test_the_self_care_paths_keep_the_voice_vm_only() -> None:
    out = tool.make_public(_live(), NAME)
    self_care = out[out.index('location ~ "^/v1/pay/(airtime') :]
    self_care = self_care[: self_care.index("\n    }\n")]
    assert "allow 192.0.2.11;" in self_care and "deny  all;" in self_care


def test_sign_in_keeps_its_rate_limit() -> None:
    block = _block(tool.make_public(_live(), NAME), "= /v1/auth/login")
    assert "limit_req zone=ratel_login" in block


def test_public_adds_the_name_and_the_certificate() -> None:
    out = tool.make_public(_live(), NAME)
    assert f"server_name bss.example.test {NAME};" in out
    assert f"ssl_certificate     /etc/letsencrypt/live/{NAME}/fullchain.pem;" in out
    assert f"ssl_certificate_key /etc/letsencrypt/live/{NAME}/privkey.pem;" in out


def test_public_after_acme_opens_the_desk_and_leaves_the_redirect_alone() -> None:
    with_acme = tool.add_acme(_live(), NAME)
    out = tool.make_public(with_acme, NAME)
    https = out[out.index(tool.HTTPS_SERVER) :]
    assert "allow " not in _block(https, "/")
    assert out.startswith(_live()[: _live().index(tool.HTTPS_SERVER)] + tool.acme_block(NAME))
    assert out == with_acme.replace(
        with_acme[with_acme.index(tool.HTTPS_SERVER) :],
        tool.make_public(_live(), NAME)[_live().index(tool.HTTPS_SERVER) :],
    )


def test_public_twice_changes_nothing_the_second_time() -> None:
    once = tool.make_public(_live(), NAME)
    assert tool.make_public(once, NAME) == once


def test_an_unknown_file_is_refused() -> None:
    with pytest.raises(ValueError, match="not a file this knows"):
        tool.make_public(_live().replace("    location /v1/ {", "    location /api/ {"), NAME)
    with pytest.raises(ValueError, match="exactly one HTTPS server"):
        tool.add_acme("server {\n    listen 8443 ssl;\n}\n", NAME)


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  (our own script on a temporary file)
        [sys.executable, "-B", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )


def test_public_is_refused_until_the_certificate_exists(tmp_path: Path) -> None:
    live = tmp_path / "ratel-app.conf"
    live.write_text(_live())
    certs = tmp_path / "live"
    result = _run(tmp_path, "public", str(live), "--name", NAME, "--cert-dir", str(certs))
    assert result.returncode == 1 and "no certificate yet" in result.stderr
    assert live.read_text() == _live()
    certs.mkdir()
    for name in ("fullchain.pem", "privkey.pem"):
        (certs / name).write_text("not a real certificate")
    result = _run(tmp_path, "public", str(live), "--name", NAME, "--cert-dir", str(certs))
    assert result.returncode == 0, result.stderr
    assert live.read_text() == tool.make_public(_live(), NAME)


@pytest.mark.parametrize("name", ["", "desk", "desk.example.org;", "desk example.org", "-a.org"])
def test_a_bad_name_is_refused(tmp_path: Path, name: str) -> None:
    live = tmp_path / "ratel-app.conf"
    live.write_text(_live())
    assert _run(tmp_path, "acme", str(live), f"--name={name}").returncode == 1
    assert live.read_text() == _live()
