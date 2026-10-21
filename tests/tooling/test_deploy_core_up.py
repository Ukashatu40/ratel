"""deploy/core-up/ stays in step with the code and stays free of secrets and addresses."""

from __future__ import annotations

import re
from pathlib import Path

from services.meter_agent.config import Settings

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy/core-up"
ENV_EXAMPLE = DEPLOY / "ratel-meter.env.example"
UNIT = DEPLOY / "ratel-meter.service"
NFT_UNIT = DEPLOY / "ratel-meter-nft.service"
NFT_TABLE = DEPLOY / "ratel-meter.nft"


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
        "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK",
        "ReadOnlyPaths=/opt/ratel-meter /etc/ratel-meter",
        "ReadWritePaths=/var/spool/ratel-meter",
    ):
        assert setting in unit, setting


def test_the_agent_has_exactly_one_capability_and_never_runs_as_root() -> None:
    unit = UNIT.read_text()
    # nft talks to the kernel over netlink and needs CAP_NET_ADMIN, nothing more.
    assert re.search(r"^CapabilityBoundingSet=CAP_NET_ADMIN$", unit, re.MULTILINE)
    assert re.search(r"^AmbientCapabilities=CAP_NET_ADMIN$", unit, re.MULTILINE)
    assert re.search(r"^User=ratelmeter$", unit, re.MULTILINE)
    assert "NoNewPrivileges=yes" in unit
    assert "CAP_SYS_ADMIN" not in unit and "CAP_NET_RAW" not in unit


def test_the_agent_needs_the_counting_table_loaded_first() -> None:
    unit = UNIT.read_text()
    assert "Requires=ratel-meter-nft.service" in unit
    assert re.search(r"^After=.*ratel-meter-nft\.service", unit, re.MULTILINE)


def test_the_table_loader_runs_only_nft_on_the_one_table_with_one_capability() -> None:
    loader = NFT_UNIT.read_text()
    assert "ExecStart=/usr/sbin/nft -f /etc/ratel-meter/ratel-meter.nft" in loader
    assert "ExecStop=/usr/sbin/nft delete table inet ratel_meter" in loader
    assert "CapabilityBoundingSet=CAP_NET_ADMIN" in loader
    assert "Type=oneshot" in loader and "RemainAfterExit=yes" in loader


def test_the_counting_table_only_counts_and_matches_what_the_agent_reads() -> None:
    rules = NFT_TABLE.read_text()
    code = [line for line in rules.splitlines() if not line.lstrip().startswith("#")]
    text = "\n".join(code)
    settings = Settings.model_fields
    assert f"table inet {settings['nft_table'].default}" in text
    assert f"set {settings['nft_up_set'].default} " in text
    assert f"set {settings['nft_down_set'].default} " in text
    assert "policy accept" in text  # counting must never drop traffic
    for verb in ("drop", "reject", "queue", "dnat", "snat", "masquerade", "redirect", "mark set"):
        assert verb not in text, verb
    assert 'iifname "ogstun" update @up   { ip saddr counter }' in text
    assert 'oifname "ogstun" update @down { ip daddr counter }' in text
    # Re-loading replaces the table instead of stacking a second copy of the rules.
    assert text.index("delete table inet ratel_meter") < text.index("table inet ratel_meter {")


def test_the_env_template_defaults_match_the_code_defaults() -> None:
    text = ENV_EXAMPLE.read_text()
    for name in ("nft_path", "nft_family", "nft_table", "nft_up_set", "nft_down_set"):
        match = re.search(rf"^METER_AGENT_{name.upper()}=(.*)$", text, re.MULTILINE)
        assert match and match.group(1) == str(Settings.model_fields[name].default), name


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
