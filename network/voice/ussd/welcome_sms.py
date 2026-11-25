#!/usr/bin/env python3
"""Welcome SMS sender: one pass, run every minute by ratel-welcome-sms.timer (docs/welcome-sms.md).

1. Ask bss-app which welcome SMS are due (GET /v1/pay/welcome-sms, through bss-app's nginx, which
   lets only this VM in and adds the payments key).
2. For each, ask the S-CSCF whether the number is registered on the IMS
   (`docker exec scscf kamcmd ulscscf.showimpu tel:<number>`). Not registered: leave it for a
   later pass. The SMS centre gives up on an unreachable phone after about a minute, so sending
   before the phone is on the network would lose the SMS.
3. Send it from 647 through the ussd container (`ussd_as.py --send-sms`), the only address the
   SMS centre takes requests from.
4. Tell bss-app it was sent (POST /v1/pay/welcome-sms/<line>/sent).

A welcome handed to the SMS centre is written to the state file before bss-app is told, so a
failure to tell bss-app never sends a second SMS: the next pass only tells bss-app again.

Settings, from the environment or from ussd.env next to this file:
    RATEL_PAY_URL          bss-app's address, as for the ussd service
    WELCOME_CA_FILE        certificates to trust for it (default: bss-ca.pem next to this file)
    WELCOME_STATE_FILE     the state file (default: welcome-sent.txt next to this file)
    WELCOME_SCSCF          the S-CSCF container (default scscf)
    WELCOME_USSD           the ussd container (default ussd)
Standard library only. `python3 -I welcome_sms.py` runs one pass; exit 0 unless something failed.
"""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MSISDN = re.compile(r"^234[0-9]{10}$")
log = logging.getLogger("welcome-sms")


def settings() -> dict[str, str]:
    values: dict[str, str] = {}
    env_file = HERE / "ussd.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("RATEL_PAY_URL", "WELCOME_CA_FILE", "WELCOME_STATE_FILE", "WELCOME_SCSCF", "WELCOME_USSD"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    values.setdefault("WELCOME_CA_FILE", str(HERE / "bss-ca.pem"))
    values.setdefault("WELCOME_STATE_FILE", str(HERE / "welcome-sent.txt"))
    values.setdefault("WELCOME_SCSCF", "scscf")
    values.setdefault("WELCOME_USSD", "ussd")
    return values


def is_registered(showimpu: str) -> bool:
    """True when `ulscscf.showimpu` shows the number registered with at least one contact.

    An unknown number prints nothing and still exits 0, so the output decides, not the exit code.
    """
    if not re.search(r"^\s*state:\s*registered\s*$", showimpu, re.M):
        return False
    contacts = re.search(r"^\s*contacts:\s*\{(.*)", showimpu, re.M | re.S)
    return contacts is not None and re.search(r"^\s*sip:\S+:\s*\{", contacts.group(1), re.M) is not None


class Sender:
    def __init__(self, conf: dict[str, str], run=subprocess.run):  # run: injected by the tests
        self.base = conf["RATEL_PAY_URL"].rstrip("/")
        ca = conf["WELCOME_CA_FILE"]
        self.tls = ssl.create_default_context(cafile=ca if Path(ca).exists() else None)
        self.state = Path(conf["WELCOME_STATE_FILE"])
        self.scscf = conf["WELCOME_SCSCF"]
        self.ussd = conf["WELCOME_USSD"]
        self.run = run

    def _api(self, method: str, path: str) -> dict:
        req = urllib.request.Request(self.base + path, method=method, headers={"Accept": "application/json"})
        if method == "POST":
            req.add_header("Content-Length", "0")
        with urllib.request.urlopen(req, timeout=10, context=self.tls) as r:
            return json.loads(r.read() or b"{}")

    def _handed_over(self) -> set[int]:
        if not self.state.exists():
            return set()
        return {int(x) for x in self.state.read_text().split() if x.isdigit()}

    def _remember(self, line_id: int) -> None:
        with self.state.open("a") as f:
            f.write(f"{line_id}\n")
            f.flush()
            os.fsync(f.fileno())

    def registered(self, msisdn: str) -> bool:
        cmd = ["docker", "exec", self.scscf, "kamcmd", "ulscscf.showimpu", f"tel:{msisdn}"]
        done = self.run(cmd, capture_output=True, text=True, timeout=15)
        return done.returncode == 0 and is_registered(done.stdout)

    def send(self, msisdn: str, text: str) -> bool:
        cmd = ["docker", "exec", "-i", self.ussd, "python", "-I", "/app/ussd_as.py", "--send-sms", msisdn]
        done = self.run(cmd, input=text, capture_output=True, text=True, timeout=30)
        return done.returncode == 0

    def one_pass(self) -> int:
        """Handle what is due. Returns the number of failures."""
        try:
            due = self._api("GET", "/v1/pay/welcome-sms?limit=50")["items"]
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            log.warning("bss-app did not answer the welcome list: %s", type(e).__name__)
            return 1
        handed = self._handed_over()
        failures = sent = waiting = 0
        for item in due:
            line_id, msisdn, text = int(item["line_id"]), str(item["msisdn"]), str(item["text"])
            if not MSISDN.match(msisdn) or not text or len(text) > 160:
                log.warning("line %s: bss-app sent a welcome this cannot send", line_id)
                failures += 1
                continue
            try:
                if line_id not in handed:
                    if not self.registered(msisdn):
                        waiting += 1
                        continue
                    if not self.send(msisdn, text):
                        log.warning("line %s: the SMS centre did not take the welcome", line_id)
                        failures += 1
                        continue
                    self._remember(line_id)
                    sent += 1
                    log.info("line %s: welcome sent to %s", line_id, msisdn)
                self._api("POST", f"/v1/pay/welcome-sms/{line_id}/sent")
            except (urllib.error.URLError, OSError, subprocess.SubprocessError, ValueError) as e:
                log.warning("line %s: %s, will retry on the next pass", line_id, type(e).__name__)
                failures += 1
        if due:
            log.info("pass: %d due, %d sent, %d not registered yet, %d failed", len(due), sent, waiting, failures)
        return failures


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conf = settings()
    if not conf.get("RATEL_PAY_URL"):
        log.error("RATEL_PAY_URL is not set (ussd.env next to this file)")
        return 2
    return 1 if Sender(conf).one_pass() else 0


if __name__ == "__main__":
    sys.exit(main())
