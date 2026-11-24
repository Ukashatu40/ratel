#!/usr/bin/env python3
"""Add the SMS 647 and USSD self-care paths to a live nginx config (docs/catalogue.md).

    sudo python3 add-selfcare-paths.py ratel-app.conf.example /etc/nginx/conf.d/ratel-app.conf

Copies the template's self-care block (`location ~ ^/v1/pay/(airtime|bundles|lines/...)$`) into the
live file, before the staff sign-in block, with the voice VM's address taken from the live
`location = /v1/calls` (its first allow line), so nothing has to be typed. Nothing else changes.

It refuses a file it does not recognise and does nothing if the block is there already. Make a
copy of the live file first, then run `nginx -t` before reloading.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BLOCK = re.compile(
    r"    # The SMS short number 647 and USSD.*?\n    location ~ \^/v1/pay/\(airtime.*?\n    \}\n",
    re.S,
)
ANCHOR = "    # Staff sign-in: office and VPN only, and slow."
CALLS = re.compile(r"    location = /v1/calls \{(.*?)\n    \}\n", re.S)


def patch(live: str, template: str) -> str:
    if "location ~ ^/v1/pay/(airtime" in live:
        return live
    block = BLOCK.search(template)
    if block is None:
        raise ValueError("the template has no self-care block")
    if live.count(ANCHOR) != 1:
        raise ValueError("the live file has no staff sign-in block to put it before")
    calls = CALLS.search(live)
    allows = re.findall(r"allow ([^;]+);", calls.group(1)) if calls else []
    if not allows or "<" in allows[0]:
        raise ValueError("no voice VM address in the live `location = /v1/calls`")
    filled = block.group(0).replace("<address-of-voice-vm>", allows[0])
    return live.replace(ANCHOR, filled + "\n" + ANCHOR, 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("template", type=Path)
    parser.add_argument("live", type=Path)
    args = parser.parse_args(argv)
    live = args.live.read_text()
    try:
        out = patch(live, args.template.read_text())
    except ValueError as exc:
        print(f"nothing changed: {exc}", file=sys.stderr)  # noqa: T201
        return 1
    if out == live:
        print("the self-care block is there already; nothing changed")  # noqa: T201
        return 0
    args.live.write_text(out)
    print(f"added the self-care block to {args.live}; now run: nginx -t && systemctl reload nginx")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
