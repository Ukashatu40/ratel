"""deploy/core-cp/ stays in step with the code and stays free of secrets and addresses."""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

from ratel_link.config import Settings

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy/core-cp"
ENV_EXAMPLE = DEPLOY / "ratel-link.env.example"
UNIT = DEPLOY / "ratel-link.service"


def _files() -> list[Path]:
    return [p for p in DEPLOY.rglob("*") if p.is_file()]


def test_every_setting_is_in_the_deployment_env_template() -> None:
    text = ENV_EXAMPLE.read_text()
    missing = [
        name.upper()
        for name in Settings.model_fields
        if not re.search(rf"^#?\s*{name.upper()}=", text, re.MULTILINE)
    ]
    assert missing == [], f"add these to {ENV_EXAMPLE.name}: {missing}"


def test_the_env_template_has_no_real_password() -> None:
    uri = re.search(r"^MONGO_URI=(.*)$", ENV_EXAMPLE.read_text(), re.MULTILINE)
    assert uri is not None and "<password>" in uri.group(1)


def test_the_unit_runs_the_service_the_way_the_docs_say() -> None:
    unit = UNIT.read_text()
    exec_start = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
    assert "--factory ratel_link.main:create_app" in exec_start
    assert "--host 127.0.0.1" in exec_start  # other hosts go through the proxy
    assert "--no-access-log" in exec_start  # the access log would print IMSIs
    assert "User=ratellink" in unit and "EnvironmentFile=/etc/ratel-link/ratel-link.env" in unit


def test_the_unit_keeps_its_hardening() -> None:
    unit = UNIT.read_text()
    for setting in (
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
        "ProtectHome=yes",
        "PrivateTmp=yes",
        "CapabilityBoundingSet=",
        "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX",
        "ReadOnlyPaths=/opt/ratel-link /etc/ratel-link",
    ):
        assert setting in unit, setting


def test_restart_limits_are_in_the_unit_section() -> None:
    # systemd silently ignores them anywhere else (found by systemd-analyze verify).
    unit = UNIT.read_text()
    unit_section = unit.split("[Service]")[0]
    assert "StartLimitIntervalSec=" in unit_section and "StartLimitBurst=" in unit_section


def test_the_scripts_are_executable_where_they_are_run_directly() -> None:
    mode = os.stat(DEPLOY / "install-release.sh").st_mode
    assert mode & stat.S_IXUSR


def test_the_roles_file_is_valid_json_with_the_placeholders_the_script_fills() -> None:
    text = (DEPLOY / "mongo/ratel-link-roles.json").read_text()
    assert {"RATEL_DB", "CORE_DB", "SUFFIX"} <= set(re.findall(r"\{\{(\w+)\}\}", text))
    filled = text.replace("{{RATEL_DB}}", "a").replace("{{CORE_DB}}", "b").replace("{{SUFFIX}}", "")
    assert json.loads(filled)["roles"]


def test_the_user_script_reads_the_password_from_the_environment_only() -> None:
    script = (DEPLOY / "mongo/create-ratel-link-user.js").read_text()
    assert "process.env.RATEL_LINK_DB_PASSWORD" in script
    assert not re.search(r"pwd:\s*['\"]", script)  # no literal password


def test_no_file_holds_a_secret_or_a_real_address() -> None:
    forbidden = [
        r"102\.214\.",  # the lab's public range (kept out of this public repository)
        r"BEGIN [A-Z ]*PRIVATE KEY",
        r"rlk_[a-z0-9-]+\.[A-Za-z0-9_-]{20,}",  # an API key
        r"mongodb://[^<\s]+:[^<\s@]{6,}@",  # a connection string with a real-looking password
    ]
    for path in _files():
        text = path.read_text()
        for pattern in forbidden:
            assert not re.search(pattern, text), f"{path.relative_to(ROOT)} matches {pattern}"


def test_the_proxy_template_never_logs_the_request_path() -> None:
    conf = (DEPLOY / "nginx/ratel-link.conf.example").read_text()
    log_format = next(line for line in conf.splitlines() if line.startswith("log_format"))
    for variable in ("$request ", "$request_uri", "$uri", "$http_authorization"):
        assert variable not in log_format + " ", variable
    assert "deny  all;" in conf and "client_max_body_size" in conf and "limit_req " in conf
