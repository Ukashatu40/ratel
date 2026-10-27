"""deploy/firewall/ stays free of real addresses and keeps the properties that make it safe."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy/firewall"
RULES = [
    DEPLOY / "core-cp.nft",
    DEPLOY / "core-up.nft",
    DEPLOY / "voice.nft",
    DEPLOY / "bss-app.nft",
]
ADDRESSES = DEPLOY / "addresses.nft.example"
UNIT = DEPLOY / "ratel-fw.service"

# The documentation ranges (RFC 5737) are the only addresses allowed in the repository.
# Loopback names no host, so it may appear too.
DOCUMENTATION = ("192.0.2.", "198.51.100.", "203.0.113.", "127.0.0.1")


def _code(path: Path) -> str:
    return "\n".join(
        line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")
    )


def test_only_documentation_addresses_are_in_the_firewall_files() -> None:
    for path in [*RULES, ADDRESSES, UNIT, DEPLOY / "README.md"]:
        for address in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", path.read_text()):
            assert address.startswith(DOCUMENTATION), f"{path.name} has the address {address}"


def test_the_rules_drop_by_default_and_own_only_their_table() -> None:
    for path in RULES:
        code = _code(path)
        assert "policy drop" in code
        assert "flush ruleset" not in code  # would delete the NAT table
        assert code.count("delete table inet ratel_fw") == 1  # a reload replaces, never stacks
        assert 'include "/etc/ratel-fw/addresses.nft"' in code
        assert "tcp dport 22 accept" in code  # key-only SSH stays reachable
        assert "ssh_new4" in code and "ssh_new6" in code  # and is rate limited


def test_every_name_the_rules_use_is_defined_in_the_address_template() -> None:
    defined = set(re.findall(r"^define (\w+) =", ADDRESSES.read_text(), re.MULTILINE))
    for path in RULES:
        used = set(re.findall(r"\$(\w+)", _code(path)))
        assert used <= defined, f"{path.name} uses {used - defined}"


def test_the_unit_loads_the_rules_before_the_network() -> None:
    text = UNIT.read_text()
    assert "ExecStart=/usr/sbin/nft -f /etc/ratel-fw/ratel-fw.nft" in text
    assert "Before=network-pre.target" in text
    assert "WantedBy=multi-user.target" in text


def test_the_voice_vm_protects_the_port_docker_publishes_in_the_forward_path() -> None:
    code = _code(DEPLOY / "voice.nft")
    assert "hook forward" in code  # a published port never reaches the input chain
    assert "ct status dnat tcp dport 8080 ip saddr != $pyhss_clients drop" in code
    assert (
        code.count("policy accept") == 1
    )  # only the forward chain: all other routing is untouched


def test_bss_app_opens_https_to_everyone_and_nothing_else_but_ssh() -> None:
    code = _code(DEPLOY / "bss-app.nft")
    assert "tcp dport 443 accept" in code
    ports = re.findall(r"dport (\d+)", code)
    assert sorted(ports) == [
        "22",
        "22",
        "22",
        "443",
    ]  # ssh (limited twice, then accepted) and https
