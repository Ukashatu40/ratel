#!/usr/bin/env python3
"""Runs ratel_prepaid.cfg in a real Kamailio against a fake ussd service.

    python3 -I test_prepaid_route.py

Needs a `kamailio` binary with the tm, sl, pv, xlog, textops, siputils, htable and http_client
modules (Debian/Ubuntu: apt install kamailio kamailio-utils-modules). Without one it says so and
exits 0, so it can sit next to the other hand-run tests. A harness config stands in for the P-CSCF:
it calls the routes as route[MO], onreply_route[MO_reply] and route[WITHINDLG] do, and reports what
they set in
headers of its replies. The P-CSCF's asserted identity ($pcscf_asserted_identity, from a module the
harness cannot load) is taken from an X-Asserted header instead.
"""

# ruff: noqa: T201, S603  (a test script run by hand: it prints its report and starts kamailio)

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIP_PORT, CLIENT_PORT, HTTP_PORT = 15099, 15098, 18648

HARNESS = r"""#!KAMAILIO
#!define DLG_TIMEOUT_AVP "i:6"
debug=2
log_stderror=yes
fork=no
children=1
listen=udp:127.0.0.1:SIP_PORT
loadmodule "tm.so"
loadmodule "sl.so"
loadmodule "pv.so"
loadmodule "xlog.so"
loadmodule "textops.so"
loadmodule "siputils.so"
loadmodule "htable.so"
loadmodule "http_client.so"
modparam("http_client", "connection_timeout", 2)
modparam("htable", "htable", "prepaid=>size=10;autoexpire=11700")
request_route {
	if (is_method("INVITE") && !has_totag()) {
		route(RATEL_PREPAID_AUTHORIZE);
		append_to_reply("X-Limit: $avp(DLG_TIMEOUT_AVP)\r\nX-M: $sht(prepaid=>m:$ci)\r\n");
		sl_send_reply("200", "authorized");
		exit;
	}
	if (is_method("OPTIONS")) {  # stands in for the 200 OK: answered X-Ago seconds ago
		$sht(prepaid=>a:$ci) = $TS - $(hdr(X-Ago){s.int});
		sl_send_reply("200", "answered");
		exit;
	}
	if (has_totag()) {
		route(RATEL_PREPAID_INDIALOG);
		append_to_reply("X-Left: $avp(DLG_TIMEOUT_AVP)\r\nX-M: $sht(prepaid=>m:$ci)\r\n");
		sl_send_reply("200", "indialog");
		exit;
	}
}
include_file "ratel_prepaid.cfg"
""".replace("SIP_PORT", str(SIP_PORT))

asked: list[tuple[str, dict[str, str]]] = []


class FakeUssd(BaseHTTPRequestHandler):
    """The ussd container's prepaid paths, as network/voice/ussd answers them."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(url.query))
        asked.append((url.path, q))
        code, body = 200, "ok"
        if url.path == "/call/authorize":
            body = "300"
            if q["dialled"].endswith("0910"):
                code, body = 402, "insufficient_balance"
            elif q["dialled"].endswith("0999"):
                time.sleep(3)  # longer than the P-CSCF waits (2 s)
            elif q["dialled"].endswith("0000"):
                body = "0"
        data = body.encode()
        try:
            self.send_response(code)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except BrokenPipeError:
            pass  # Kamailio gave up waiting, as it should


def main() -> int:
    kamailio = shutil.which("kamailio")
    if not kamailio:
        print("no kamailio binary here: skipped (apt install kamailio kamailio-utils-modules)")
        return 0
    work = Path(tempfile.mkdtemp(prefix="ratel-prepaid-"))
    route = (HERE / "ratel_prepaid.cfg").read_text()
    route = route.replace(
        "$(pcscf_asserted_identity{s.len}) > 0", "$(hdr(X-Asserted){s.len}) > 0"
    ).replace("$var(caller) = $pcscf_asserted_identity;", "$var(caller) = $hdr(X-Asserted);")
    route = route.replace("http://172.22.0.40:8647", f"http://127.0.0.1:{HTTP_PORT}")
    (work / "ratel_prepaid.cfg").write_text(route)
    (work / "k.cfg").write_text(HARNESS)
    check = subprocess.run(
        [kamailio, "-c", "-f", str(work / "k.cfg")], cwd=work, capture_output=True, text=True
    )
    if "config file ok" not in check.stdout + check.stderr:
        print("FAIL: kamailio refuses the route file:\n" + (check.stdout + check.stderr)[-1500:])
        return 1

    http = HTTPServer(("127.0.0.1", HTTP_PORT), FakeUssd)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    proc = subprocess.Popen(
        [kamailio, "-f", str(work / "k.cfg"), "-E", "-DD", "-w", str(work)],
        cwd=work,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    time.sleep(1.5)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(6)
    sock.bind(("127.0.0.1", CLIENT_PORT))

    def sip(method: str, ruri: str, call_id: str, totag: bool = False, extra: str = ""):
        to = "<sip:callee@ims>" + (";tag=t1" if totag else "")
        msg = (
            f"{method} {ruri} SIP/2.0\r\n"
            f"Via: SIP/2.0/UDP 127.0.0.1:{CLIENT_PORT};branch=z9hG4bK{time.time_ns()}\r\n"
            f"From: <sip:+2348000000905@ims>;tag=f1\r\nTo: {to}\r\nCall-ID: {call_id}\r\n"
            f"CSeq: 1 {method}\r\nMax-Forwards: 70\r\nX-Asserted: sip:+2348000000905@ims\r\n"
            f"{extra}Content-Length: 0\r\n\r\n"
        )
        sock.sendto(msg.encode(), ("127.0.0.1", SIP_PORT))
        data = sock.recv(4000).decode()
        lines = data.split("\r\n")
        hdrs = {
            k.strip(): v.strip() for k, _, v in (ln.partition(":") for ln in lines[1:] if ":" in ln)
        }
        return lines[0].split(" ", 1)[1], hdrs.get("X-Limit"), hdrs.get("X-Left"), hdrs.get("X-M")

    failures = 0

    def expect(name: str, got, want):
        nonlocal failures
        ok = all(w is None or g == w for g, w in zip(got, want, strict=True))
        print(f"   {'ok ' if ok else 'FAIL'} {name} -> {got}")
        failures += not ok

    unset = "<null>"
    try:
        expect(
            "a limited call",
            sip("INVITE", "tel:+2348000000906", "c1@10.46.0.2"),
            ("200 authorized", "300", None, "300"),
        )
        expect(
            "a refused call gets 402",
            sip("INVITE", "tel:+2348000000910", "c2"),
            ("402 Payment Required", None, None, None),
        )
        expect(
            "no limit (0)",
            sip("INVITE", "tel:+2348000000000", "c3"),
            ("200 authorized", unset, None, unset),
        )
        expect(
            "112 is not asked about",
            sip("INVITE", "tel:112", "c4"),
            ("200 authorized", unset, None, unset),
        )
        expect(
            "a USSD code is not asked about",
            sip("INVITE", "sip:*123%23@ims", "c5"),
            ("200 authorized", unset, None, unset),
        )
        started = time.monotonic()
        expect(
            "no answer in 2 s: 120 s",
            sip("INVITE", "tel:+2348000000999", "c6"),
            ("200 authorized", "120", None, "120"),
        )
        waited = time.monotonic() - started
        print(f"   {'ok ' if waited < 2.6 else 'FAIL'} the INVITE waited {waited:.1f} s")
        failures += waited >= 2.6
        sip("OPTIONS", "sip:callee@ims", "c1@10.46.0.2", extra="X-Ago: 100\r\n")
        expect(
            "a refresh 100 s in gets the 200 s left",
            sip("UPDATE", "sip:callee@ims", "c1@10.46.0.2", True),
            ("200 indialog", None, "200", "300"),
        )
        expect(
            "BYE: the call is forgotten",
            sip("BYE", "sip:callee@ims", "c1@10.46.0.2", True),
            ("200 indialog", None, None, unset),
        )
        expect(
            "an unlimited call is left alone",
            sip("UPDATE", "sip:callee@ims", "c3", True),
            ("200 indialog", None, unset, unset),
        )
        time.sleep(0.5)
        calls = [q for path, q in asked if path == "/call/authorize"]
        want = {
            "call_id": "c1@10.46.0.2",
            "caller": "sip:+2348000000905@ims",
            "dialled": "+2348000000906",
        }
        ok = calls[0] == want and not any(q["dialled"] in ("112", "*123#") for q in calls)
        print(f"   {'ok ' if ok else 'FAIL'} what is asked (call 1: {calls[0]}); never 112 or USSD")
        failures += not ok
        ends = [q for path, q in asked if path == "/call/end"]
        ok = ends == [{"call_id": "c1@10.46.0.2", "seconds": "101"}]
        print(f"   {'ok ' if ok else 'FAIL'} the end is reported once, 101 s -> {ends}")
        failures += not ok
    finally:
        proc.terminate()
        out = proc.communicate()[0]
        http.shutdown()
        http.server_close()
        sock.close()
        shutil.rmtree(work, ignore_errors=True)
        print("".join("   | " + ln + "\n" for ln in out.splitlines() if "prepaid" in ln))
        if " ERROR" in out:
            failures += 1
            print("FAIL: kamailio logged an error")
    print("ALL PASSED" if failures == 0 else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
