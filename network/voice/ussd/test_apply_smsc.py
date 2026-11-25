#!/usr/bin/env python3
"""Tests for apply-smsc-shortcode.py. `python3 -I test_apply_smsc.py`."""

from __future__ import annotations

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(HERE, name))
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    return module


tool = load("apply-smsc-shortcode.py")

# The lines the script anchors on, as they are in docker_open5gs' kamailio_smsc.cfg.
FRESH = (
    "route[SMS_FROM_3GPP] {\n\tif (isRPDATA()) {\n"
    "\t\t$avp(to) = $tpdu(destination);\n\t}\n}\n"
    "event_route[xhttp:request] {\n\tif ($hu =~ \"^/\") {\n"
    "\t\t$avp(from_outbound) = 1;\n\t}\n}\n"
    "route[SEND_SMS] {\n\t$rpdata(originator) = $avp(from);\n\t$tpdu(type) = 4; // SMS-Deliver\n"
    "\t$tpdu(origen) = $avp(from); // The Destination becomes the originator of the SMS\n"
    "\t$tpdu(payload) = $avp(text);\n}\n"
)

# What apply-smsc-647.py made of it (24 Nov): its three blocks, as the old script wrote them.
OLD = (
    FRESH.replace(tool.FROM_3GPP_ANCHOR, tool.FROM_3GPP_ANCHOR + tool.OLD_FROM_3GPP)
    .replace(tool.XHTTP_ANCHOR, tool.XHTTP_ANCHOR + tool.OLD_XHTTP)
    .replace(tool.DCS_ANCHOR, tool.DCS_ANCHOR + tool.OLD_DCS)
)


def check(name, ok):
    print(f"   {'ok ' if ok else 'FAIL'} {name}")
    return 0 if ok else 1


def refused(text):
    try:
        tool.patch(text)
    except ValueError:
        return True
    return False


def main() -> int:
    failures = 0
    new = tool.patch(FRESH)
    failures += check("a fresh config gets the three changes for 555",
                      new.count("RATEL SHORT") >= 3 and '"^[+]?555$"' in new and "?647" not in new)
    failures += check("a short number goes out with address type 0x81 (129)",
                      "$tpdu(origen_flags) = 129;" in new and "$rpdata(originator_flags) = 129;" in new
                      and new.index("origen_flags") > new.index("$tpdu(origen) = $avp(from)"))
    failures += check("the 647 version is replaced by exactly the same result",
                      "RATEL 647" in OLD and tool.patch(OLD) == new)
    failures += check("this version is not applied twice", refused(new))
    failures += check("a 647 version that was edited by hand is refused",
                      refused(OLD.replace("SMSC: text to 647", "SMSC: text to six-four-seven")))
    failures += check("a config without the anchors is refused", refused("route[X] {\n}\n"))
    print("ALL PASSED" if not failures else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
