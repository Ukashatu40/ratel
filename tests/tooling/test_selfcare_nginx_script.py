"""The script that adds the SMS 647 and USSD self-care block to a live nginx config."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/bss-app/nginx/add-selfcare-paths.py"
TEMPLATE = (ROOT / "deploy/bss-app/nginx/ratel-app.conf.example").read_text()
VOICE = "192.0.2.11"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("add_selfcare_paths", SCRIPT)
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


def _filled(text: str) -> str:
    """A live file: the placeholders replaced by example values."""
    values = {
        "<name-of-this-host>": "bss.example.test",
        "<address-of-core-up>": "192.0.2.10",
        "<address-of-voice-vm>": VOICE,
        "<office-and-vpn-range>": "127.0.0.1",
    }
    for key, value in values.items():
        text = text.replace(key, value)
    return re.sub(r"<paystack-address-\d>", "192.0.2.50", text)


def _without_block(text: str) -> str:
    block = tool.BLOCK.search(text)
    assert block is not None
    return text.replace(block.group(0) + "\n", "", 1)


def test_a_live_file_without_the_block_gets_exactly_the_template_block() -> None:
    old = _filled(_without_block(TEMPLATE))
    assert "/v1/pay/(airtime" not in old
    assert tool.patch(old, TEMPLATE) == _filled(TEMPLATE)


def test_the_block_takes_the_voice_vm_address_from_the_live_calls_block() -> None:
    new = tool.patch(_filled(_without_block(TEMPLATE)), TEMPLATE)
    block = tool.BLOCK.search(new)
    assert block is not None
    assert re.findall(r"allow ([^;]+);", block.group(0)) == [VOICE]


def test_running_it_twice_changes_nothing() -> None:
    once = tool.patch(_filled(_without_block(TEMPLATE)), TEMPLATE)
    assert tool.patch(once, TEMPLATE) == once


def test_a_file_it_does_not_know_is_refused() -> None:
    with pytest.raises(ValueError):
        tool.patch("server {\n}\n", TEMPLATE)


def test_an_older_self_care_block_is_replaced_with_the_voice_address_from_calls() -> None:
    current = _filled(TEMPLATE)
    older = current.replace("|welcome-sms(/[0-9]+/sent)?", "", 1)
    assert older != current
    older = older.replace(
        f"allow {VOICE};\n        deny  all;\n        limit_req zone=ratel_pay",
        "allow 192.0.2.99;\n        deny  all;\n        limit_req zone=ratel_pay",
    )
    new = tool.patch(older, TEMPLATE)
    block = tool.BLOCK.search(new)
    assert block is not None and "welcome-sms" in block.group(0)
    # the address comes from `location = /v1/calls`, the voice VM's other path
    assert re.findall(r"allow ([^;]+);", block.group(0)) == [VOICE]
    assert new.replace(block.group(0), "") == older.replace(tool.BLOCK.search(older).group(0), "")  # type: ignore[union-attr]
