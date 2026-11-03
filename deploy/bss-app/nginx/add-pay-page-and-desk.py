#!/usr/bin/env python3
"""Bring a live nginx config up to the current template: the RatelPay page, RatelDesk, /v1/calls.

    sudo python3 add-pay-page-and-desk.py ratel-app.conf.example /etc/nginx/conf.d/ratel-app.conf \
        [--office RANGE]

The live config was made from an older template, with every <placeholder> filled in. This copies
the blocks it lacks from the template into it: `location = /pay` and the Desk (`location /`,
replacing the old `location / { return 404; }`), and `location = /v1/calls` for the voice VM's call
agent. The addresses come from the live file itself (the office range from `location /v1/`, the
voice VM's address from `location /v1/usage`), so none has to be typed again. Nothing else changes.

--office RANGE sets the office and VPN range on the staff blocks (/v1/usage, /v1/calls, /v1/ and
the Desk) in one go. It leaves /healthz (local only) and every other allow line alone.

It refuses a file it does not recognise, and does nothing if the blocks are there already. Make a
copy of the live file first, then run `nginx -t` before reloading.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

PAGE = re.compile(
    r"    # PUBLIC: the RatelPay page\. .*?\n    location = /pay \{.*?\n    \}\n", re.S
)
DESK = re.compile(r"    # RatelDesk, the staff site.*?\n    location / \{.*?\n    \}\n", re.S)
OLD_ROOT = "    location / {\n        return 404;\n    }\n"
CALLS = re.compile(
    r"    # The voice VM's call agent posts call records here\."
    r".*?\n    location = /v1/calls \{.*?\n    \}\n",
    re.S,
)
ANCHOR = "    # PUBLIC PATH: the RatelPay page redeems a prepaid card here."
OFFICE_PLACEHOLDER = "<office-and-vpn-range>"


def _block(text: str, header: str) -> re.Match[str]:
    found = re.search(rf"    location {re.escape(header)} \{{.*?\n    \}}\n", text, re.S)
    if found is None:
        raise ValueError(f"the live file has no `location {header}` block: not a file this knows")
    return found


def _allows(block: str) -> list[str]:
    return re.findall(r"allow ([^;]+);", block)


def patch(live: str, template: str, office: str | None = None, voice: str | None = None) -> str:
    page, desk, calls = PAGE.search(template), DESK.search(template), CALLS.search(template)
    if page is None or desk is None or calls is None:
        raise ValueError("the template lacks the RatelPay page, RatelDesk or /v1/calls block")
    out = live

    if "location = /v1/calls {" not in out:
        usage = _block(out, "/v1/usage").group(0)
        addresses = _allows(usage)  # core-up, the voice VM, the office, in that order
        voice = voice or (addresses[1] if len(addresses) >= 3 else None)
        if voice is None:
            raise ValueError(
                "the voice VM's address is not in `location /v1/usage` (it lists "
                f"{len(addresses)} addresses): give it with --voice ADDRESS"
            )
        staff = _allows(_block(out, "/v1/").group(0))
        if not staff:
            raise ValueError("`location /v1/` has no allow line")
        filled = calls.group(0).replace("<address-of-voice-vm>", voice)
        filled = filled.replace(OFFICE_PLACEHOLDER, staff[0])
        out = out.replace(usage, usage + "\n" + filled, 1)

    if not ("location = /pay {" in out and "root /var/www/ratel-desk;" in out):
        if out.count(ANCHOR) != 1 or out.count(OLD_ROOT) != 1:
            raise ValueError("the live file does not look like the older template: edit it by hand")
        current_office = _allows(_block(out, "/v1/").group(0))
        if not current_office:
            raise ValueError("`location /v1/` has no allow line")
        desk_block = desk.group(0).replace(OFFICE_PLACEHOLDER, current_office[0])
        out = out.replace(ANCHOR, page.group(0) + "\n" + ANCHOR).replace(OLD_ROOT, desk_block)

    if office:
        old = _allows(_block(out, "/v1/").group(0))[0]
        for header in ("/v1/usage", "= /v1/calls", "/v1/", "/"):
            block = _block(out, header).group(0)
            out = out.replace(block, block.replace(f"allow {old};", f"allow {office};"))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="add-pay-page-and-desk.py")
    parser.add_argument("template", type=Path)
    parser.add_argument("live", type=Path)
    parser.add_argument("--office", help="the office and VPN range for the staff blocks")
    parser.add_argument(
        "--voice", help="the voice VM's address, if `location /v1/usage` does not list it"
    )
    args = parser.parse_args(argv)
    for name in ("office", "voice"):
        value = getattr(args, name)
        if value and not re.fullmatch(r"[0-9a-fA-F:.]+(/[0-9]{1,3})?", value):
            sys.stderr.write(
                f"refused: --{name} must be an address or a range such as 192.0.2.0/24\n"
            )
            return 1
    live = args.live.read_text()
    try:
        out = patch(live, args.template.read_text(), args.office, args.voice)
    except ValueError as exc:
        sys.stderr.write(f"refused: {exc}\n")
        return 1
    if out == live:
        sys.stdout.write("nothing to change: the file is already current\n")
        return 0
    tmp = args.live.with_name(args.live.name + ".new")
    tmp.write_text(out)
    tmp.chmod(args.live.stat().st_mode & 0o777)
    os.replace(tmp, args.live)
    sys.stdout.write("done: now run `sudo nginx -t` and, if it is ok, reload nginx\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
