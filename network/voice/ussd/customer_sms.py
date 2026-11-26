#!/usr/bin/env python3
"""Customer SMS sender: one pass, run every minute by ratel-customer-sms.timer.

See docs/customer-sms.md.

The welcome after an activation and the summary after each charged call, queued by bss-app.

1. Ask bss-app which SMS are due (GET /v1/pay/customer-sms, through bss-app's nginx, which lets
   only this VM in and adds the payments key).
2. For each, ask the S-CSCF whether the number is registered on the IMS
   (`docker exec scscf kamcmd ulscscf.showimpu tel:<number>`). Not registered: leave it for a
   later pass. The SMS centre gives up on an unreachable phone after about a minute, so sending
   before the phone is on the network would lose the SMS.
3. Send it from 555 through the ussd container (`ussd_as.py --send-sms`), the only address the
   SMS centre takes requests from.
4. Tell bss-app it was sent (POST /v1/pay/customer-sms/<sms_id>/sent).

An SMS handed to the SMS centre is written to the state file before bss-app is told, so a
failure to tell bss-app never sends a second SMS: the next pass only tells bss-app again.

Settings, from the environment or from ussd.env next to this file:
    RATEL_PAY_URL          bss-app's address, as for the ussd service
    SMS_CA_FILE            certificates to trust for it (default: bss-ca.pem next to this file)
    SMS_STATE_FILE         the state file (default: customer-sms-sent.txt next to this file)
    SMS_SCSCF              the S-CSCF container (default scscf)
    SMS_USSD               the ussd container (default ussd)
Standard library only. `python3 -I customer_sms.py` runs one pass; exit 0 unless something failed.
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
log = logging.getLogger("customer-sms")


def settings() -> dict[str, str]:
    values: dict[str, str] = {}
    env_file = HERE / "ussd.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("RATEL_PAY_URL", "SMS_CA_FILE", "SMS_STATE_FILE", "SMS_SCSCF", "SMS_USSD"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    values.setdefault("SMS_CA_FILE", str(HERE / "bss-ca.pem"))
    values.setdefault("SMS_STATE_FILE", str(HERE / "customer-sms-sent.txt"))
    values.setdefault("SMS_SCSCF", "scscf")
    values.setdefault("SMS_USSD", "ussd")
    return values


def is_registered(showimpu: str) -> bool:
    """True when `ulscscf.showimpu` shows the number registered with at least one contact.

    An unknown number prints nothing and still exits 0, so the output decides, not the exit code.
    """
    if not re.search(r"^\s*state:\s*registered\s*$", showimpu, re.M):
        return False
    contacts = re.search(r"^\s*contacts:\s*\{(.*)", showimpu, re.M | re.S)
    return (
        contacts is not None
        and re.search(r"^\s*sip:\S+:\s*\{", contacts.group(1), re.M) is not None
    )


class Sender:
    def __init__(self, conf: dict[str, str], run=subprocess.run):  # run: injected by the tests
        self.base = conf["RATEL_PAY_URL"].rstrip("/")
        ca = conf["SMS_CA_FILE"]
        self.tls = ssl.create_default_context(cafile=ca if Path(ca).exists() else None)
        self.state = Path(conf["SMS_STATE_FILE"])
        self.scscf = conf["SMS_SCSCF"]
        self.ussd = conf["SMS_USSD"]
        self.run = run

    def _api(self, method: str, path: str) -> dict:
        req = urllib.request.Request(  # noqa: S310  (RATEL_PAY_URL from the service's own settings, http or https)
            self.base + path, method=method, headers={"Accept": "application/json"}
        )
        if method == "POST":
            req.add_header("Content-Length", "0")
        with urllib.request.urlopen(req, timeout=10, context=self.tls) as r:  # noqa: S310  (RATEL_PAY_URL from the service's own settings, http or https)
            return json.loads(r.read() or b"{}")

    def _handed_over(self) -> set[int]:
        if not self.state.exists():
            return set()
        return {int(x) for x in self.state.read_text().split() if x.isdigit()}

    def _remember(self, sms_id: int) -> None:
        with self.state.open("a") as f:
            f.write(f"{sms_id}\n")
            f.flush()
            os.fsync(f.fileno())

    def registered(self, msisdn: str) -> bool:
        cmd = ["docker", "exec", self.scscf, "kamcmd", "ulscscf.showimpu", f"tel:{msisdn}"]
        done = self.run(cmd, capture_output=True, text=True, timeout=15)
        return done.returncode == 0 and is_registered(done.stdout)

    def send(self, msisdn: str, text: str) -> bool:
        cmd = [
            "docker",
            "exec",
            "-i",
            self.ussd,
            "python",
            "-I",
            "/app/ussd_as.py",
            "--send-sms",
            msisdn,
        ]
        done = self.run(cmd, input=text, capture_output=True, text=True, timeout=30)
        return done.returncode == 0

    def one_pass(self) -> int:
        """Handle what is due. Returns the number of failures."""
        try:
            due = self._api("GET", "/v1/pay/customer-sms?limit=50")["items"]
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            log.warning("bss-app did not answer the SMS list: %s", type(e).__name__)
            return 1
        handed = self._handed_over()
        failures = sent = waiting = 0
        for item in due:
            sms_id, msisdn, text = int(item["sms_id"]), str(item["msisdn"]), str(item["text"])
            kind = str(item.get("kind", "?"))
            if not MSISDN.match(msisdn) or not text or len(text) > 160:
                log.warning("sms %s: bss-app sent an SMS this cannot send", sms_id)
                failures += 1
                continue
            try:
                if sms_id not in handed:
                    if not self.registered(msisdn):
                        waiting += 1
                        continue
                    if not self.send(msisdn, text):
                        log.warning("sms %s: the SMS centre did not take it", sms_id)
                        failures += 1
                        continue
                    self._remember(sms_id)
                    sent += 1
                    log.info("sms %s: %s sent to ...%s", sms_id, kind, msisdn[-4:])
                self._api("POST", f"/v1/pay/customer-sms/{sms_id}/sent")
            except (urllib.error.URLError, OSError, subprocess.SubprocessError, ValueError) as e:
                log.warning("sms %s: %s, will retry on the next pass", sms_id, type(e).__name__)
                failures += 1
        if due:
            log.info(
                "pass: %d due, %d sent, %d not registered yet, %d failed",
                len(due),
                sent,
                waiting,
                failures,
            )
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
