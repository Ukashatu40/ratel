"""The script that brings a live nginx config up to the template changes only what it should."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/bss-app/nginx/add-pay-page-and-desk.py"
TEMPLATE = (ROOT / "deploy/bss-app/nginx/ratel-app.conf.example").read_text()


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("add_pay_page_and_desk", SCRIPT)
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


def _older(template: str) -> str:
    """The template as it was before the page and the Desk: no /pay block, a 404 at the root."""
    without_calls = tool.CALLS.sub("", template, count=1).replace("\n\n\n", "\n\n")
    without_page = tool.PAGE.sub("", without_calls, count=1).replace("\n\n\n", "\n\n")
    return tool.DESK.sub("    location / {\n        return 404;\n    }\n", without_page)


def _filled(text: str) -> str:
    """A live file: the placeholders replaced by example values."""
    values = {
        "<name-of-this-host>": "bss.example.test",
        "<address-of-core-up>": "192.0.2.10",
        "<address-of-voice-vm>": "192.0.2.11",
        "<office-and-vpn-range>": "127.0.0.1",
    }
    for key, value in values.items():
        text = text.replace(key, value)
    return re.sub(r"<paystack-address-\d>", "192.0.2.50", text)


def test_the_older_file_gets_exactly_the_new_blocks() -> None:
    old = _filled(_older(TEMPLATE))
    assert "location = /pay" not in old and "return 404" in old
    new = tool.patch(old, TEMPLATE)
    assert new == _filled(TEMPLATE)  # nothing else changed, and nothing had to be typed again


def test_the_desk_block_takes_the_office_range_the_live_file_already_uses() -> None:
    old = _filled(_older(TEMPLATE))
    staff = re.search(r"    location /v1/ \{.*?\n    \}", old, re.S)
    assert staff is not None
    old = old.replace(
        staff.group(0), staff.group(0).replace("allow 127.0.0.1;", "allow 198.51.100.0/24;")
    )
    new = tool.patch(old, TEMPLATE)
    desk = re.search(r"location / \{.*?\n    \}", new, re.S)
    assert desk is not None and "allow 198.51.100.0/24;" in desk.group(0)


def test_running_it_twice_changes_nothing() -> None:
    once = tool.patch(_filled(_older(TEMPLATE)), TEMPLATE)
    assert tool.patch(once, TEMPLATE) == once


def test_an_office_range_is_set_on_the_staff_blocks_only() -> None:
    new = tool.patch(_filled(_older(TEMPLATE)), TEMPLATE, office="203.0.113.0/24")
    for header in ("/v1/usage", "= /v1/calls", "/v1/", "/"):
        block = re.search(rf"    location {re.escape(header)} \{{.*?\n    \}}", new, re.S)
        assert block is not None and "allow 203.0.113.0/24;" in block.group(0), header
    health = re.search(r"location = /healthz \{.*?\n    \}", new, re.S)
    assert health is not None and "allow 127.0.0.1;" in health.group(0)  # local only, untouched
    usage = re.search(r"location /v1/usage \{.*?\n    \}", new, re.S)
    assert usage is not None and "allow 192.0.2.10;" in usage.group(0)  # the agents' addresses stay


def test_a_file_it_does_not_know_is_refused() -> None:
    with pytest.raises(ValueError, match=r"not a file this knows|does not look like"):
        tool.patch("server { listen 443; }\n", TEMPLATE)


def test_the_command_writes_the_file_and_refuses_a_bad_range(tmp_path: Path) -> None:
    live = tmp_path / "ratel-app.conf"
    template = tmp_path / "template"
    live.write_text(_filled(_older(TEMPLATE)))
    template.write_text(TEMPLATE)
    assert tool.main([str(template), str(live), "--office", "not a range; rm"]) == 1
    assert "location = /pay" not in live.read_text()
    assert tool.main([str(template), str(live), "--office", "203.0.113.0/24"]) == 0
    assert "location = /pay" in live.read_text()
    assert tool.main([str(template), str(live)]) == 0  # already current


def test_a_host_that_already_has_the_page_and_the_desk_only_gains_the_calls_path() -> None:
    """The state of bss-app today: patched once for /pay and the Desk, not yet for /v1/calls."""
    current = _filled(TEMPLATE)
    without_calls = tool.CALLS.sub("", current, count=1).replace("\n\n\n", "\n\n")
    assert "location = /v1/calls" not in without_calls and "location = /pay" in without_calls
    assert tool.patch(without_calls, TEMPLATE) == current


def test_the_calls_path_lets_in_the_voice_vm_and_the_office_and_nobody_else() -> None:
    new = tool.patch(_filled(_older(TEMPLATE)), TEMPLATE)
    block = re.search(r"location = /v1/calls \{.*?\n    \}", new, re.S)
    assert block is not None
    body = block.group(0)
    assert re.findall(r"allow ([^;]+);", body) == ["192.0.2.11", "127.0.0.1"]
    assert "deny  all;" in body and "ratel-pay-key" not in body
