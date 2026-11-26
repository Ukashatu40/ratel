#!/usr/bin/env python3
"""Adds the self-care short number to the SMSC (voice VM, ~/docker_open5gs/smsc/kamailio_smsc.cfg).

The short number is 555 (SHORT below). Three changes, all marked "RATEL SHORT":
  1. route[SMS_FROM_3GPP]: a text addressed to 555 is not queued for a subscriber. It goes to the
     self-care service in the ussd container (http://172.22.0.40:8647/sms) with the sender's number
     and the text hex encoded. The handset already got its RP-ACK before this point.
  2. event_route[xhttp:request]: the SMSC's HTTP entry point, which the service uses to send its
     answers and the customer SMS, only accepts requests from the ussd container, sets the coding
     (dcs 0) that the queue insert needs, and takes the text hex encoded (parameter hex), since the
     URL decoder refuses newlines.
  3. route[SEND_SMS]: an SMS from a short number (3 to 6 digits) is sent with the address type
     "unknown" (0x81) instead of "international" (0x91), so phones show 555 and not +555. With the
     international type, 647 showed as +64 7. Only the sender address inside the SMS (TP-OA, what
     the phone shows) has a type setting in Kamailio's smsops: $tpdu(origen_flags). $rpdata has
     none; `$rpdata(originator_flags)` made the SMSC refuse to start (26 Nov 2026).

Before it writes, it has the smsc container's own Kamailio check the new file (`kamailio -c`), and
refuses when that fails, so a file the SMSC would not load is never written. The dry run shows the
same check. `--no-check` skips it (only where the container is not running).

A file that has the earlier 647 version (apply-smsc-647.py, "RATEL 647") gets it replaced by this
one. A file that has this version already is left alone.

Usage (in ~/docker_open5gs/smsc):
  python3 apply-smsc-shortcode.py kamailio_smsc.cfg
      dry run: shows the result and the Kamailio check, changes nothing
  python3 apply-smsc-shortcode.py kamailio_smsc.cfg --apply
      checks, backs up, writes, then: docker restart smsc
Rollback: copy the backup it names over kamailio_smsc.cfg and docker restart smsc.
"""

# ruff: noqa: T201  (a command-line tool: printing is its output)

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from collections.abc import Callable

SHORT = "555"
MARK = "RATEL SHORT"

FROM_3GPP_ANCHOR = "\t\t$avp(to) = $tpdu(destination);\n"
FROM_3GPP_BLOCK = r"""		# RATEL SHORT (2026-11-25): a text to the short number 555 goes to the self-care service
		# (network/voice/ussd in the ratel repository), which answers by SMS from 555.
		if ($avp(to) =~ "^[+]?555$") {
			xnotice("SMSC: text to 555 from $(ai{uri.user})\n");
			$var(url) = "http://172.22.0.40:8647/sms?from=" + $(ai{uri.user}) + "&hex=" + $(tpdu(payload){s.encode.hexa});
			http_client_query("$var(url)", "$var(res)");
			if ($retcode != 200) {
				xlog("L_ERR", "SMSC: the 555 service answered $retcode\n");
			}
			exit;
		}
""".replace("555", SHORT)  # noqa: E501  (config text that must match the live file byte for byte)

XHTTP_ANCHOR = "event_route[xhttp:request] {\n"
XHTTP_BLOCK = """	# RATEL SHORT (2026-11-25): only the self-care service in the ussd container may submit texts here.
	if ($si != "172.22.0.40") {
		xlog("L_WARN", "SMSC: HTTP submit refused from $si\\n");
		xhttp_reply("403", "Forbidden", "text/plain", "forbidden");
		exit;
	}
"""  # noqa: E501  (config text that must match the live file byte for byte)

DCS_ANCHOR = "\t\t$avp(from_outbound) = 1;\n"
DCS_BLOCK = r"""		$avp(dcs) = 0; # RATEL SHORT: the queue insert needs a coding
		# RATEL SHORT hex: texts from the self-care service come hex encoded, because the URL decoder
		# above refuses control characters such as the newlines in the menu.
		if ($(hu{url.querystring}{param.value,hex,&}{s.len}) > 0) {
			$avp(text) = $(hu{url.querystring}{param.value,hex,&}{s.decode.hexa});
		}
"""  # noqa: E501  (config text that must match the live file byte for byte)

ORIGEN_ANCHOR = (
    "\t$tpdu(origen) = $avp(from); // The Destination becomes the originator of the SMS\n"
)
ORIGEN_BLOCK = r"""	# RATEL SHORT: a short number goes out with the address type "unknown" (0x81), not
	# "international" (0x91), so phones show 555 and not +555 (647 showed as +64 7).
	if ($avp(from) =~ "^[0-9]{3,6}$") {
		$tpdu(origen_flags) = 129;
	}
"""  # noqa: E501  (config text that must match the live file byte for byte)

# What apply-smsc-647.py wrote (24 Nov 2026): removed exactly, then this version is added.
OLD_FROM_3GPP = r"""		# RATEL 647 (2026-11-24): a text to the short number 647 goes to the self-care service
		# (network/voice/ussd in the ratel repository), which answers by SMS from 647.
		if ($avp(to) =~ "^[+]?647$") {
			xnotice("SMSC: text to 647 from $(ai{uri.user})\n");
			$var(url) = "http://172.22.0.40:8647/sms?from=" + $(ai{uri.user}) + "&hex=" + $(tpdu(payload){s.encode.hexa});
			http_client_query("$var(url)", "$var(res)");
			if ($retcode != 200) {
				xlog("L_ERR", "SMSC: the 647 service answered $retcode\n");
			}
			exit;
		}
"""  # noqa: E501  (config text that must match the live file byte for byte)
OLD_XHTTP = """	# RATEL 647 (2026-11-24): only the 647 service in the ussd container may submit texts here.
	if ($si != "172.22.0.40") {
		xlog("L_WARN", "SMSC: HTTP submit refused from $si\\n");
		xhttp_reply("403", "Forbidden", "text/plain", "forbidden");
		exit;
	}
"""  # noqa: E501  (config text that must match the live file byte for byte)
OLD_DCS = r"""		$avp(dcs) = 0; # RATEL 647: the queue insert needs a coding
		# RATEL 647 hex: answers from the 647 service come hex encoded, because the URL decoder
		# above refuses control characters such as the newlines in the menu.
		if ($(hu{url.querystring}{param.value,hex,&}{s.len}) > 0) {
			$avp(text) = $(hu{url.querystring}{param.value,hex,&}{s.decode.hexa});
		}
"""


def patch(text: str) -> str:
    """The config with this version in it. ValueError when the file is not one this knows."""
    if MARK in text:
        raise ValueError("this version is already in the file")
    if "RATEL 647" in text:
        for old in (OLD_FROM_3GPP, OLD_XHTTP, OLD_DCS):
            if text.count(old) != 1:
                raise ValueError(
                    "found the 647 version, but not exactly as apply-smsc-647.py wrote it"
                )
            text = text.replace(old, "", 1)
        if "RATEL 647" in text:
            raise ValueError("a 647 change is left that this does not know")
    for anchor in (FROM_3GPP_ANCHOR, XHTTP_ANCHOR, DCS_ANCHOR, ORIGEN_ANCHOR):
        if text.count(anchor) != 1:
            raise ValueError(
                f"expected exactly one line {anchor.strip()!r}, found {text.count(anchor)}"
            )
    text = text.replace(FROM_3GPP_ANCHOR, FROM_3GPP_ANCHOR + FROM_3GPP_BLOCK, 1)
    text = text.replace(XHTTP_ANCHOR, XHTTP_ANCHOR + XHTTP_BLOCK, 1)
    text = text.replace(DCS_ANCHOR, DCS_ANCHOR + DCS_BLOCK, 1)
    return text.replace(ORIGEN_ANCHOR, ORIGEN_ANCHOR + ORIGEN_BLOCK, 1)


CONTAINER = "smsc"
CHECK_FILE = "/etc/kamailio_smsc/.ratel-short-check.cfg"  # next to the live file, for its includes


def kamailio_check(
    text: str, run: Callable[..., subprocess.CompletedProcess[str]]
) -> tuple[bool, str]:
    """Has the smsc container's Kamailio parse `text` (kamailio -c). (ok, what it said when not)."""
    try:
        put = run(
            ["docker", "exec", "-i", CONTAINER, "sh", "-c", f"cat > {CHECK_FILE}"],
            input=text,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if put.returncode != 0:
            return (
                False,
                f"could not copy the file into the {CONTAINER} container: {put.stderr.strip()}",
            )
        done = run(
            ["docker", "exec", CONTAINER, "kamailio", "-c", "-f", CHECK_FILE],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"could not run the check: {type(e).__name__}"
    finally:
        try:
            run(
                ["docker", "exec", CONTAINER, "rm", "-f", CHECK_FILE],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    said = (done.stdout + done.stderr).strip()
    errors = [line for line in said.splitlines() if "ERROR" in line or "CRITICAL" in line]
    if done.returncode != 0 or errors:
        return False, "\n".join(errors[-8:]) or said[-800:]
    return True, ""


def main(argv: list[str] | None = None, run=subprocess.run) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(__doc__)
        return 2
    path, apply, checked = args[0], "--apply" in args[1:], "--no-check" not in args[1:]
    try:
        new = patch(open(path).read())
    except ValueError as e:
        print(f"{e}; nothing changed")
        return 1
    lines = new.splitlines()
    for i, line in enumerate(lines):
        if MARK in line and "#" in line.split(MARK)[0]:
            print(
                "\n".join(
                    f"{n + 1:4} {lines[n]}" for n in range(max(0, i - 1), min(len(lines), i + 9))
                )
            )
            print("     ...")
    if checked:
        ok, said = kamailio_check(new, run)
        if not ok:
            print(f"\nthe {CONTAINER} container's Kamailio refuses the new file:\n{said}")
            print("nothing written" if apply else "dry run: nothing written")
            return 1
        print(f"\nthe {CONTAINER} container's Kamailio accepts the new file (kamailio -c)")
    if not apply:
        print("\ndry run: nothing written. Run again with --apply to write it.")
        return 0
    backup = f"{path}.bak-short-{time.strftime('%Y%m%d%H%M')}"
    shutil.copy2(path, backup)
    open(path, "w").write(new)
    print(f"\nwritten. backup: {backup}\nnext: docker restart smsc")
    return 0


if __name__ == "__main__":
    sys.exit(main())
