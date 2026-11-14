"""The voice stack kept in Git: no credentials, no host addresses, no SIM key material.

`tests/tooling/test_network_voice.py` guards the `scscf-acc/` fragments. This guards everything
under `network/voice/`, which since 2026-11-13 includes whole configuration files copied from the
voice VM. Those files are the reason this test exists: one of them carried the Kamailio database
password as a literal, and the redaction that removed it is only safe if something keeps checking.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "network/voice"

# The Ratelplus LAN. No host address belongs in the repository; the README names hosts by role.
HOST_NETWORK = re.compile(r"\b102\.214\.241\.\d{1,3}\b")

# A database URL with a password in it. The placeholder is what the redaction leaves behind.
CREDENTIAL_URL = re.compile(r"mysql://\w+:(?!KAMAILIO_DB_PASSWORD@)[^@\s\"']+@")

KEY_MATERIAL = re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")

# SIM key material: a value, not a variable name. `UE1_KI=CHANGEME` in env.example is fine.
SIM_KEY = re.compile(r"\b(?:KI|OPC?)\s*[=:]\s*(?!CHANGEME\b)[0-9a-fA-F]{16,}")


def files() -> list[Path]:
    return sorted(p for p in FOLDER.rglob("*") if p.is_file())


def test_the_tree_is_not_empty_and_is_all_text() -> None:
    found = files()
    assert len(found) > 50, len(found)
    for path in found:
        path.read_text(encoding="utf-8")


def test_no_file_carries_a_database_password() -> None:
    for path in files():
        match = CREDENTIAL_URL.search(path.read_text())
        assert match is None, f"{path.relative_to(ROOT)} carries a database credential"


def test_no_file_carries_a_ratelplus_host_address() -> None:
    for path in files():
        match = HOST_NETWORK.search(path.read_text())
        assert match is None, f"{path.relative_to(ROOT)} names a host address"


def test_no_file_carries_key_material() -> None:
    for path in files():
        body = path.read_text()
        assert KEY_MATERIAL.search(body) is None, path.relative_to(ROOT)
        assert SIM_KEY.search(body) is None, path.relative_to(ROOT)


def test_the_env_template_assigns_no_real_value_to_a_sim_key() -> None:
    env = (FOLDER / "stack/env.example").read_text()
    for name in ("UE1_KI", "UE1_OP"):
        assert f"{name}=CHANGEME" in env, name


def test_the_redaction_is_consistent_across_the_eight_files() -> None:
    """Both halves must agree: the URL the config opens, and the user the init script creates."""
    redacted = [
        "stack/pcscf/pcscf.cfg",
        "stack/pcscf/pcscf_init.sh",
        "stack/scscf/scscf.cfg",
        "stack/scscf/scscf_init.sh",
        "stack/icscf/icscf.cfg",
        "stack/icscf/icscf_init.sh",
        "stack/smsc/smsc.cfg",
        "stack/smsc/smsc_init.sh",
    ]
    for name in redacted:
        body = (FOLDER / name).read_text()
        assert "KAMAILIO_DB_PASSWORD" in body, name
    readme = (FOLDER / "stack/README.md").read_text()
    assert "KAMAILIO_DB_PASSWORD" in readme, "the redaction must stay documented"
