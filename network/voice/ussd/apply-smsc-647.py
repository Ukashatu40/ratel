#!/usr/bin/env python3
"""Adds the SMS short number 647 to the SMSC (voice VM, ~/docker_open5gs/smsc/kamailio_smsc.cfg).

Two changes, both marked "RATEL 647":
  1. route[SMS_FROM_3GPP]: a text addressed to 647 is not queued for a subscriber. It goes to the
     647 service in the ussd container (http://172.22.0.40:8647/sms) with the sender's number and
     the text hex encoded. The handset already got its RP-ACK before this point.
  2. event_route[xhttp:request]: the SMSC's HTTP entry point, which the 647 service uses to send
     its answers, now only accepts requests from the ussd container (it accepted anyone before and
     nothing else in Ratelplus uses it), and sets the coding (dcs 0) that the queue insert needs.

Usage (in ~/docker_open5gs/smsc):
  python3 apply-smsc-647.py kamailio_smsc.cfg            dry run: shows the result, changes nothing
  python3 apply-smsc-647.py kamailio_smsc.cfg --apply    backs up, writes, then: docker restart smsc
Rollback: copy the backup it names over kamailio_smsc.cfg and docker restart smsc.
"""

import shutil
import sys
import time

MARK = "RATEL 647"

FROM_3GPP_ANCHOR = "\t\t$avp(to) = $tpdu(destination);\n"
FROM_3GPP_BLOCK = r"""		# RATEL 647 (2026-11-24): a text to the short number 647 goes to the self-care service
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
"""

XHTTP_ANCHOR = "event_route[xhttp:request] {\n"
XHTTP_BLOCK = """	# RATEL 647 (2026-11-24): only the 647 service in the ussd container may submit texts here.
	if ($si != "172.22.0.40") {
		xlog("L_WARN", "SMSC: HTTP submit refused from $si\\n");
		xhttp_reply("403", "Forbidden", "text/plain", "forbidden");
		exit;
	}
"""

DCS_ANCHOR = "\t\t$avp(from_outbound) = 1;\n"
DCS_LINE = "\t\t$avp(dcs) = 0; # RATEL 647: the queue insert needs a coding\n"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path, apply = sys.argv[1], "--apply" in sys.argv[2:]
    text = open(path).read()
    if MARK in text:
        print("647 is already in this file, nothing changed")
        return 1
    for anchor in (FROM_3GPP_ANCHOR, XHTTP_ANCHOR, DCS_ANCHOR):
        if text.count(anchor) != 1:
            print(f"expected exactly one line {anchor.strip()!r}, found {text.count(anchor)}; nothing changed")
            return 1
    new = text.replace(FROM_3GPP_ANCHOR, FROM_3GPP_ANCHOR + FROM_3GPP_BLOCK)
    new = new.replace(XHTTP_ANCHOR, XHTTP_ANCHOR + XHTTP_BLOCK)
    new = new.replace(DCS_ANCHOR, DCS_ANCHOR + DCS_LINE)
    lines = new.splitlines()
    for i, line in enumerate(lines):
        if MARK in line and "#" in line.split(MARK)[0]:
            print("\n".join(f"{n + 1:4} {lines[n]}" for n in range(max(0, i - 2), min(len(lines), i + 12))))
            print("     ...")
    if not apply:
        print("\ndry run: nothing written. Run again with --apply to write it.")
        return 0
    backup = f"{path}.bak-647-{time.strftime('%Y%m%d%H%M')}"
    shutil.copy2(path, backup)
    open(path, "w").write(new)
    print(f"\nwritten. backup: {backup}\nnext: docker restart smsc")
    return 0


if __name__ == "__main__":
    sys.exit(main())
