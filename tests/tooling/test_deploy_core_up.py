"""deploy/core-up/ stays in step with the code and stays free of secrets and addresses."""

from __future__ import annotations

import re
from pathlib import Path

from services.meter_agent.config import Settings

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy/core-up"
ENV_EXAMPLE = DEPLOY / "ratel-meter.env.example"
UNIT = DEPLOY / "ratel-meter.service"


def _files() -> list[Path]:
    return [p for p in DEPLOY.rglob("*") if p.is_file()]


def test_every_setting_is_in_the_core_up_env_template() -> None:
    text = ENV_EXAMPLE.read_text()
    missing = [
        f"METER_AGENT_{name.upper()}"
        for name in Settings.model_fields
        if not re.search(rf"^#?\s*METER_AGENT_{name.upper()}=", text, re.MULTILINE)
    ]
    assert missing == [], f"add these to {ENV_EXAMPLE.name}: {missing}"


def test_the_unit_runs_the_service_as_expected() -> None:
    unit = UNIT.read_text()
    assert "ExecStart=/opt/ratel-meter/current/venv/bin/python -m meter_agent.main" in unit
    assert "User=ratelmeter" in unit
    assert "EnvironmentFile=/etc/ratel-meter/ratel-meter.env" in unit


def test_the_unit_keeps_its_hardening() -> None:
    unit = UNIT.read_text()
    for setting in (
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
        "ProtectHome=yes",
        "PrivateTmp=yes",
        "CapabilityBoundingSet=",
        "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX",
        "ReadOnlyPaths=/opt/ratel-meter /etc/ratel-meter",
        "ReadWritePaths=/var/spool/ratel-meter",
    ):
        assert setting in unit, setting


def test_restart_limits_are_in_the_unit_section() -> None:
    unit = UNIT.read_text()
    unit_section = unit.split("[Service]")[0]
    assert "StartLimitIntervalSec=" in unit_section and "StartLimitBurst=" in unit_section


def test_no_file_in_core_up_holds_a_secret_or_real_address() -> None:
    forbidden = [
        r"102\.214\.",
        r"BEGIN [A-Z ]*PRIVATE KEY",
        r"rlk_[a-z0-9-]+\.[A-Za-z0-9_-]{20,}",
    ]
    for path in _files():
        text = path.read_text()
        for pattern in forbidden:
            assert not re.search(pattern, text), f"{path.relative_to(ROOT)} matches {pattern}"
