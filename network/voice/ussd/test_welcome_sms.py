#!/usr/bin/env python3
"""Tests for welcome_sms.py: a fake bss-app over HTTP and a fake `docker`. `python3 -I test_welcome_sms.py`."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import welcome_sms  # noqa: E402

# Real output of `kamcmd ulscscf.showimpu` on the voice VM, 25 Nov 2026 (iPhone line 454).
REGISTERED = """{
	impu: tel:2342064730454
	state: registered
	barring: 0
	subscription: {
		impi: 621002064730454@ims.mnc000.mcc621.3gppnetwork.org
		service profiles: {
			1: {
				impus: {
					1: sip:621002064730454@ims.mnc000.mcc621.3gppnetwork.org
					3: tel:2342064730454
				}
			}
		}
	}
	contacts: {
		sip:10.46.0.23:5060;alias=10.46.0.23~5060~1: {
			expires: 3149
			client: iOS/27.0.1 iPhone
		}
"""
UNKNOWN = ""  # an unknown number prints nothing and exits 0
NOT_REGISTERED = "{\n\timpu: tel:2348000000002\n\tstate: not registered\n\tbarring: 0\n\tcontacts: {\n\t}\n"
NO_CONTACT = "{\n\timpu: tel:2348000000002\n\tstate: registered\n\tcontacts: {\n\t}\n"

TEXT = "Welcome to Ratelplus! Your number is 08000000001. Text MENU to 647 for balance, bundles and top-up."


class FakeBss(BaseHTTPRequestHandler):
    due: list[dict] = []
    marked: list[int] = []
    fail_mark = False

    def log_message(self, *a):
        pass

    def _json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/v1/pay/welcome-sms"):
            return self._json(200, {"items": [d for d in FakeBss.due if d["line_id"] not in FakeBss.marked]})
        self._json(404, {})

    def do_POST(self):
        parts = self.path.split("/")
        if FakeBss.fail_mark:
            return self._json(503, {})
        if self.path.startswith("/v1/pay/welcome-sms/") and parts[-1] == "sent":
            FakeBss.marked.append(int(parts[-2]))
            return self._json(200, {"line_id": int(parts[-2]), "sent_at": 1})
        self._json(404, {})


class FakeDocker:
    """Plays `docker exec scscf kamcmd ...` and `docker exec -i ussd ... --send-sms`."""

    def __init__(self, showimpu: dict[str, str], send_ok: bool = True):
        self.showimpu, self.send_ok, self.sent = showimpu, send_ok, []

    def __call__(self, cmd, **kw):
        if "kamcmd" in cmd:
            number = cmd[-1].removeprefix("tel:")
            return subprocess.CompletedProcess(cmd, 0, self.showimpu.get(number, UNKNOWN), "")
        if "--send-sms" in cmd:
            if self.send_ok:
                self.sent.append((cmd[-1], kw["input"]))
            return subprocess.CompletedProcess(cmd, 0 if self.send_ok else 1, "", "")
        raise AssertionError(cmd)


def sender(state: Path, docker: FakeDocker) -> welcome_sms.Sender:
    conf = {"RATEL_PAY_URL": "http://127.0.0.1:18081", "WELCOME_CA_FILE": "/nonexistent",
            "WELCOME_STATE_FILE": str(state), "WELCOME_SCSCF": "scscf", "WELCOME_USSD": "ussd"}
    return welcome_sms.Sender(conf, run=docker)


def check(name, ok):
    print(f"   {'ok ' if ok else 'FAIL'} {name}")
    return 0 if ok else 1


def main() -> int:
    httpd = HTTPServer(("127.0.0.1", 18081), FakeBss)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    failures = 0
    print("== reading the S-CSCF")
    failures += check("a registered number with a contact", welcome_sms.is_registered(REGISTERED))
    failures += check("an unknown number (empty output)", not welcome_sms.is_registered(UNKNOWN))
    failures += check("a number not registered", not welcome_sms.is_registered(NOT_REGISTERED))
    failures += check("registered but no contact", not welcome_sms.is_registered(NO_CONTACT))

    one = {"line_id": 7, "msisdn": "2348000000001", "text": TEXT}
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "sent.txt"
        print("== sending")
        FakeBss.due, FakeBss.marked = [one], []
        docker = FakeDocker({})
        failures += sender(state, docker).one_pass()
        failures += check("not registered yet: nothing sent, nothing marked",
                          docker.sent == [] and FakeBss.marked == [])

        docker = FakeDocker({"2348000000001": REGISTERED}, send_ok=False)
        bad = sender(state, docker).one_pass()
        failures += check("the SMS centre refuses: counted, not marked, not remembered",
                          bad == 1 and FakeBss.marked == [] and not state.exists())

        FakeBss.fail_mark = True
        docker = FakeDocker({"2348000000001": REGISTERED})
        bad = sender(state, docker).one_pass()
        failures += check("sent once, bss-app not told yet: remembered",
                          docker.sent == [("2348000000001", TEXT)] and bad == 1 and state.read_text() == "7\n")
        FakeBss.fail_mark = False
        docker2 = FakeDocker({"2348000000001": REGISTERED})
        failures += sender(state, docker2).one_pass()
        failures += check("the next pass tells bss-app without a second SMS",
                          docker2.sent == [] and FakeBss.marked == [7])
        docker3 = FakeDocker({"2348000000001": REGISTERED})
        failures += sender(state, docker3).one_pass()
        failures += check("once marked, nothing more happens", docker3.sent == [] and FakeBss.marked == [7])

        print("== what bss-app sends is checked")
        FakeBss.due, FakeBss.marked = [{"line_id": 8, "msisdn": "0800000001", "text": TEXT},
                                       {"line_id": 9, "msisdn": "2348000000009", "text": "x" * 161}], []
        docker = FakeDocker({"0800000001": REGISTERED, "2348000000009": REGISTERED})
        bad = sender(state, docker).one_pass()
        failures += check("a bad number or a text over one SMS is not sent",
                          bad == 2 and docker.sent == [] and FakeBss.marked == [])

    print("== bss-app not answering")
    conf = {"RATEL_PAY_URL": "http://127.0.0.1:1", "WELCOME_CA_FILE": "/nonexistent",
            "WELCOME_STATE_FILE": "/nonexistent/x", "WELCOME_SCSCF": "s", "WELCOME_USSD": "u"}
    docker = FakeDocker({})
    failures += check("counted as a failure, nothing sent",
                      welcome_sms.Sender(conf, run=docker).one_pass() == 1 and docker.sent == [])
    httpd.shutdown()
    print("ALL PASSED" if not failures else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
