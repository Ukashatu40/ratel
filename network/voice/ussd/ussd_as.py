#!/usr/bin/env python3
"""RatelPlus USSD service: USSD over IMS (USSI), 3GPP TS 24.390, user-initiated sessions.

The S-CSCF forwards an INVITE whose Request-URI is a dial string (*123#) to this service. The
session then runs like this:

    phone                    S-CSCF / P-CSCF                  this service
      INVITE *123#  (SDP with port 0, ussd-data)  ------------->  200 OK (SDP with port 0)
      ACK  ---------------------------------------------------->
      <-------------------------------------- INFO (ussd-data: the menu, Info-Package g.3gpp.ussd)
      200 OK  -------------------------------------------------->
      INFO (ussd-data: the user's choice)  ---------------------->  200 OK
      <------------------------------- BYE (ussd-data: the final answer) or INFO (the next menu)
      200 OK  -------------------------------------------------->

Standard library only, so it runs in a plain python image. UDP towards the S-CSCF, with the
retransmissions SIP requires on UDP. One process, one thread, asyncio.

Configuration, from the environment:
    USSD_BIND_IP        address to listen on (default 0.0.0.0)
    USSD_PUBLIC_IP      address written in Via and Contact (required: the container's own IP)
    USSD_PORT           default 5060
    USSD_LOG_LEVEL      default INFO
    RATEL_PAY_URL       base URL of ratel-app's payments API, for example https://bss-app/...
    RATEL_PAY_KEY_FILE  optional file holding the payments API key (never in the environment);
                        not needed through bss-app's nginx, which adds the key on the public paths
    SSL_CERT_FILE       certificates to trust for RATEL_PAY_URL (bss-app's is self-signed)
    SMS_PORT            TCP port for the 555 SMS service (off when unset)
    SMS_SMSC_URL        the SMSC's HTTP entry point (default http://172.22.0.33:7090)
    SMS_ALLOWED         comma-separated addresses allowed to post texts (default 172.22.0.33)
Without RATEL_PAY_URL the menu still works and answers that the option is not available yet.

The same process also serves the SMS short number 555 (SmsService below), because USSD over IMS
only works on some Android phones: iPhones need Apple's carrier bundle and feature phones dial the
code as a call. Text messages reach every phone.

`python -I ussd_as.py --send-sms 234XXXXXXXXXX` (text on standard input) sends one SMS from 555
and exits: 0 when the SMSC took it. The customer SMS sender (customer_sms.py) runs it inside this
container with `docker exec`, because the SMSC takes requests from this address only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import ssl
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

log = logging.getLogger("ussd")

T1 = 0.5  # SIP timer T1 (s)
T2 = 4.0  # SIP timer T2 (s)
TIMEOUT = 32.0  # 64 * T1: give up on a transaction
SESSION_IDLE = 120.0  # a USSD session with no traffic for this long is closed
USSD_MAX = 182  # characters in one USSD string

ALLOW = "INVITE, ACK, BYE, CANCEL, INFO, OPTIONS"
USSD_TYPE = "application/vnd.3gpp.ussd+xml"
COMPACT = {
    "i": "call-id",
    "m": "contact",
    "e": "content-encoding",
    "l": "content-length",
    "c": "content-type",
    "f": "from",
    "s": "subject",
    "k": "supported",
    "t": "to",
    "v": "via",
}


def last_four(msisdn: str | None) -> str:
    """A phone number as the logs show it: the last four digits only (customer data stays out)."""
    digits = "".join(c for c in (msisdn or "") if c.isdigit())
    return "..." + digits[-4:] if len(digits) >= 4 else "unknown"


def masked_code(code: str) -> str:
    """A dialled USSD code with any run of five digits or more hidden (it may carry a card)."""
    return re.sub(r"[0-9]{5,}", lambda m: "*" * len(m.group(0)), code)


def first_word(data: bytes) -> str:
    """The SIP method of a request, or `SIP/2.0` for a response: nothing that names anyone."""
    return data.split(b" ", 1)[0][:16].decode("ascii", "replace")


def token(n: int = 10) -> str:
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(n))


# ---------------------------------------------------------------------------------------------
# SIP message parsing and building
# ---------------------------------------------------------------------------------------------


@dataclass
class Msg:
    first: str
    headers: list[tuple[str, str]]  # (lower-case name, value) in order, one entry per value line
    body: bytes = b""

    @property
    def is_request(self) -> bool:
        return not self.first.startswith("SIP/2.0")

    @property
    def method(self) -> str:
        return self.first.split(" ", 1)[0] if self.is_request else self.cseq_method

    @property
    def ruri(self) -> str:
        return self.first.split(" ")[1]

    @property
    def status(self) -> int:
        return int(self.first.split(" ")[1])

    def get(self, name: str) -> str | None:
        for n, v in self.headers:
            if n == name:
                return v
        return None

    def all(self, name: str) -> list[str]:
        return [v for n, v in self.headers if n == name]

    @property
    def call_id(self) -> str:
        return self.get("call-id") or ""

    @property
    def cseq_num(self) -> int:
        return int((self.get("cseq") or "0 X").split()[0])

    @property
    def cseq_method(self) -> str:
        return (self.get("cseq") or "0 X").split()[1]

    @property
    def branch(self) -> str:
        m = re.search(r";branch=([^;,\s]+)", self.get("via") or "")
        return m.group(1) if m else ""


def split_list(value: str) -> list[str]:
    """Split a comma-separated header value, ignoring commas inside <...> or quotes."""
    out, cur, depth, quoted = [], "", 0, False
    for ch in value:
        if ch == '"':
            quoted = not quoted
        elif not quoted and ch == "<":
            depth += 1
        elif not quoted and ch == ">":
            depth -= 1
        if ch == "," and depth == 0 and not quoted:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


MULTI = {"via", "route", "record-route", "contact"}


def parse(data: bytes) -> Msg | None:
    head, sep, body = data.partition(b"\r\n\r\n")
    if not sep:
        return None
    lines = head.decode("utf-8", "replace").split("\r\n")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if line[:1] in (" ", "\t") and headers:  # folded line
            n, v = headers[-1]
            headers[-1] = (n, v + " " + line.strip())
            continue
        name, _, value = line.partition(":")
        name = name.strip().lower()
        name = COMPACT.get(name, name)
        value = value.strip()
        if name in MULTI:
            headers.extend((name, v) for v in split_list(value))
        else:
            headers.append((name, value))
    msg = Msg(lines[0], headers)
    length = msg.get("content-length")
    msg.body = body[: int(length)] if length is not None and length.isdigit() else body
    return msg


def build(first: str, headers: list[tuple[str, str]], body: bytes = b"") -> bytes:
    lines = [first] + [f"{n}: {v}" for n, v in headers] + [f"Content-Length: {len(body)}", "", ""]
    return "\r\n".join(lines).encode() + body


def uri_of(nameaddr: str) -> str:
    m = re.search(r"<([^>]+)>", nameaddr)
    return m.group(1) if m else nameaddr.split(";")[0].strip()


def user_digits(nameaddr: str) -> str | None:
    """The phone number in sip:2348000000901@... or tel:2348000000901, if it is one."""
    m = re.search(r"(?:sip:|tel:)\+?([0-9]{10,15})(?:[@;>]|$)", nameaddr or "")
    return m.group(1) if m else None


def body_parts(msg: Msg) -> dict[str, bytes]:
    """Parts of the body by content type (multipart/mixed is split, anything else is one part)."""
    ctype = msg.get("content-type") or ""
    if not ctype.lower().startswith("multipart/"):
        return {ctype.split(";")[0].strip().lower(): msg.body} if msg.body else {}
    m = re.search(r'boundary="?([^";]+)"?', ctype, re.I)
    if not m:
        return {}
    parts: dict[str, bytes] = {}
    for chunk in msg.body.split(b"--" + m.group(1).encode())[1:]:
        if chunk.startswith(b"--"):
            break
        chunk = chunk.lstrip(b"\r\n")
        phead, _, pbody = chunk.partition(b"\r\n\r\n")
        pt = re.search(rb"content-type:\s*([^\r\n;]+)", phead, re.I)
        if pt:
            parts[pt.group(1).decode().strip().lower()] = pbody.rstrip(b"\r\n")
    return parts


def ussd_string(xml: bytes) -> str | None:
    m = re.search(rb"<ussd-string>(.*?)</ussd-string>", xml, re.S)
    return m.group(1).decode("utf-8", "replace").strip() if m else None


def ussd_xml(text: str | None = None, error_code: int | None = None) -> bytes:
    out = '<?xml version="1.0" encoding="UTF-8"?>\n<ussd-data>\n <language>en</language>\n'
    if text is not None:
        out += f" <ussd-string>{escape(text[:USSD_MAX])}</ussd-string>\n"
    if error_code is not None:
        out += f" <error-code>{error_code}</error-code>\n"
    return (out + "</ussd-data>\n").encode()


def sdp_answer(offer: bytes | None, ip: str) -> bytes | None:
    """Answer every media line of the offer with port 0: USSD carries no media."""
    if not offer:
        return None
    media = [ln for ln in offer.decode("utf-8", "replace").splitlines() if ln.startswith("m=")]
    sess = str(int(time.time()))
    lines = ["v=0", f"o=ratel-ussd {sess} {sess} IN IP4 {ip}", "s=-", f"c=IN IP4 {ip}", "t=0 0"]
    for m in media:
        parts = m.split()
        parts[1] = "0"
        lines.append(" ".join(parts))
    return ("\r\n".join(lines) + "\r\n").encode()


# ---------------------------------------------------------------------------------------------
# The menu
# ---------------------------------------------------------------------------------------------

MAIN_MENU = "Ratelplus\n1. My balance\n2. Buy airtime\n3. Buy a bundle\n4. Recharge card"
AMOUNTS = [100, 200, 500, 1000]  # naira, used only when the payments API is not configured


@dataclass
class Reply:
    text: str
    end: bool  # True: final answer (BYE), False: expect another choice (INFO)


class Menu:
    """What to answer. Pure logic plus calls to ratel-app; no SIP in here."""

    def __init__(self, pay: PayApi):
        self.pay = pay

    def start(self, s: Session, code: str) -> Reply:
        code = code.replace("%23", "#")
        m = re.fullmatch(r"\*123\*([0-9]{20})\*([0-9]{14})#", code)
        if m:  # *123*CARD*PIN#: recharge in one go
            return self.recharge(s, m.group(1), m.group(2))
        if code == "*123#":
            s.state = "main"
            return Reply(MAIN_MENU, False)
        return Reply("Unknown service code. Dial *123# for the Ratelplus menu.", True)

    def answer(self, s: Session, text: str) -> Reply:
        text = text.strip()
        if s.state == "main":
            if text == "1":
                return Reply(self.pay.balance_text(s.msisdn), True)
            if text == "2":
                s.state = "airtime"
                s.choices = [str(a) for a in self.pay.airtime_amounts()]
                opts = "\n".join(f"{i}. N{a}" for i, a in enumerate(s.choices, 1))
                return Reply("Buy airtime\n" + opts, False)
            if text == "3":
                offers = self.pay.bundles("ussd")
                if not offers:
                    return Reply(self.pay.bundles_text("ussd"), True)
                s.state = "bundle"
                s.choices = [str(b["bundle_id"]) for b in offers]
                return Reply(bundle_menu(offers), False)
            if text == "4":
                s.state = "card"
                return Reply("Enter the 20 digit card number, a star, then the 14 digit PIN", False)
            return Reply("Invalid choice. Dial *123# to start again.", True)
        if s.state == "airtime":
            if text.isdigit() and 1 <= int(text) <= len(s.choices):
                return Reply(self.pay.payment_text(s.msisdn, int(s.choices[int(text) - 1])), True)
            return Reply("Invalid choice. Dial *123# to start again.", True)
        if s.state == "bundle":
            if text.isdigit() and 1 <= int(text) <= len(s.choices):
                bundle_id = int(s.choices[int(text) - 1])
                return Reply(self.pay.buy_bundle_text(s.msisdn, bundle_id, "ussd", s.call_id), True)
            return Reply("Invalid choice. Dial *123# to start again.", True)
        if s.state == "card":
            m = re.fullmatch(r"([0-9]{20})\*([0-9]{14})", text.replace(" ", ""))
            if not m:
                return Reply("That is not a card number and PIN. Dial *123# to try again.", True)
            return self.recharge(s, m.group(1), m.group(2))
        return Reply("Session ended. Dial *123# to start again.", True)

    def recharge(self, s: Session, card: str, pin: str) -> Reply:
        return Reply(self.pay.recharge_text(s.msisdn, card, pin), True)


def bundle_menu(offers: list[dict]) -> str:
    """A numbered list of bundles, short enough for one USSD screen."""
    lines = [
        f"{i}. {b['name']} {PayApi.naira(b['price_kobo'], whole=True)}"
        for i, b in enumerate(offers, 1)
    ]
    return "Buy a bundle\n" + "\n".join(lines)


class PayApi:
    """ratel-app's payments API (/v1/pay). Blocking urllib, called in a worker thread."""

    def __init__(self, base: str | None, key: str | None):
        self.base = (base or "").rstrip("/")
        self.key = key
        self.ctx = ssl.create_default_context()

    @property
    def ready(self) -> bool:
        # The key is optional: on the public paths (payments, voucher redeem) bss-app's nginx adds
        # the payments key itself and replaces any Authorization header, as it does for RatelPay.
        return bool(self.base)

    def _call(self, method: str, path: str, body: dict | None = None, extra: dict | None = None):
        req = urllib.request.Request(self.base + path, method=method)  # noqa: S310  (RATEL_PAY_URL from the service's own settings, http or https)
        if self.key:
            req.add_header("Authorization", f"Bearer {self.key}")
        req.add_header("Accept", "application/json")
        for k, v in (extra or {}).items():
            req.add_header(k, v)
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, data=data, timeout=6, context=self.ctx) as r:  # noqa: S310  (RATEL_PAY_URL from the service's own settings, http or https)
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except ValueError:
                return e.code, {}
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
            log.warning("pay api %s %s failed: %s", method, path, type(e).__name__)
            return 0, {}

    @staticmethod
    def naira(kobo: int, whole: bool = False) -> str:
        if whole and kobo % 100 == 0:
            return f"N{kobo // 100:,}"
        return f"N{kobo / 100:,.2f}"

    @staticmethod
    def size(data_bytes: int) -> str:
        if data_bytes >= 1_000_000_000:
            return f"{data_bytes / 1_000_000_000:.3g}GB"
        return f"{data_bytes / 1_000_000:.3g}MB"

    def airtime_amounts(self) -> list[int]:
        """The amounts (naira) an admin set for the menus, inside the card limits."""
        if self.ready:
            status, body = self._call("GET", "/v1/pay/airtime")
            presets = body.get("presets_kobo") if status == 200 else None
            if presets:
                return [p // 100 for p in presets]
        return list(AMOUNTS)

    def airtime_limits(self) -> tuple[int, int]:
        """(smallest, largest) card payment in naira."""
        if self.ready:
            status, body = self._call("GET", "/v1/pay/airtime")
            if status == 200 and "card_min_kobo" in body:
                return body["card_min_kobo"] // 100, body["card_max_kobo"] // 100
        return 100, 50_000

    def bundles(self, channel: str) -> list[dict]:
        """Bundles on sale on this channel, cheapest first. Empty when unknown."""
        if not self.ready:
            return []
        status, body = self._call("GET", f"/v1/pay/bundles?channel={channel}")
        items = body.get("bundles", []) if status == 200 else []
        return sorted(items, key=lambda b: (b.get("price_kobo", 0), b.get("bundle_id", 0)))[:6]

    def buy_bundle_text(
        self, msisdn: str | None, bundle_id: int, channel: str, request_id: str
    ) -> str:
        if not (self.ready and msisdn):
            return "Bundles are not available yet. Please try again later."
        status, body = self._call(
            "POST",
            f"/v1/pay/lines/{msisdn}/purchases",
            {"bundle_id": bundle_id, "channel": channel},
            {"Idempotency-Key": f"{channel}-{request_id}-{bundle_id}"[:100]},
        )
        if status == 200:
            until = ""
            if body.get("valid_to"):
                until = " until " + time.strftime("%d %b", time.gmtime(body["valid_to"]))
            return (
                f"{body['name']} is active{until}. Airtime left {self.naira(body['balance_kobo'])}"
            )
        error = (body.get("error") or {}) if isinstance(body, dict) else {}
        if error.get("code") == "insufficient_funds":
            return (
                "Not enough airtime for this bundle. "
                "Top up with BUY and the amount, or a recharge card."
            )
        if status == 409:
            return "That bundle is not available now. Send BUNDLES for the list."
        return "Bundles are not available right now. Please try again later."

    def balance_text(self, msisdn: str | None) -> str:
        if not (self.ready and msisdn):
            return "Balance is not available yet. Please try again later."
        status, body = self._call("GET", f"/v1/pay/lines/{msisdn}/balance")
        if status == 200 and "balance_kobo" in body:
            text = f"Airtime {self.naira(body['balance_kobo'])}"
            left = body.get("data_bytes_left") or 0
            if left > 0:
                text += f". Data {self.size(left)}"
                if body.get("data_valid_to"):
                    text += " until " + time.strftime("%d %b", time.gmtime(body["data_valid_to"]))
            else:
                text += ". No data bundle"
            return text
        return "Balance is not available right now. Please try again later."

    def bundles_text(self, channel: str) -> str:
        if not self.ready:
            return "Bundles are not available yet. Please try again later."
        offers = self.bundles(channel)
        if not offers:
            return "Bundles are not available right now. Please try again later."
        lines = [
            f"{i} {b['name']} {self.naira(b['price_kobo'], whole=True)}"
            for i, b in enumerate(offers, 1)
        ]
        return "Bundles\n" + "\n".join(lines) + "\nReply BUNDLE and the number"

    def payment_text(self, msisdn: str | None, naira: int) -> str:
        if not (self.ready and msisdn):
            return "Airtime purchase is not available yet. Please try again later."
        status, body = self._call(
            "POST",
            "/v1/pay/payments",
            {"msisdn": msisdn, "amount_kobo": naira * 100},
            {"Idempotency-Key": f"ussd-{msisdn}-{naira}-{int(time.time())}"},
        )
        url = body.get("checkout_url") if status == 200 else None
        if url:
            return f"Pay N{naira} at {url}"
        return "Airtime purchase is not available right now. Please try again later."

    def recharge_text(self, msisdn: str | None, card: str, pin: str) -> str:
        if not (self.ready and msisdn):
            return "Recharge is not available yet. Please try again later."
        status, body = self._call(
            "POST", "/v1/pay/vouchers/redeem", {"msisdn": msisdn, "card_number": card, "pin": pin}
        )
        if status == 200:
            return (
                f"Recharge of {self.naira(body['amount_kobo'])} successful. "
                f"New balance {self.naira(body['balance_kobo'])}"
            )
        if status == 429:
            return "Too many attempts. Please try again later."
        if status in (400, 422):
            return "This card cannot be used."
        return "Recharge is not available right now. Please try again later."


# ---------------------------------------------------------------------------------------------
# SMS short number 555: the same services by text message, for every phone
# ---------------------------------------------------------------------------------------------

SMS_SHORT = "555"
SMS_HELP = (
    "Ratelplus 555\nBAL - your balance\nBUY 500 - buy N500 airtime\n"
    "BUNDLES - list, BUNDLE 2 - buy\nCARD cardnumber pin - recharge card"
)
MSISDN_RE = re.compile(r"^234[0-9]{10}$")


class SmsCommands:
    """Turns one text sent to 555 into one answer. Stateless: every text is a full command."""

    def __init__(self, pay: PayApi):
        self.pay = pay

    @staticmethod
    def keyword(text: str) -> str:
        """For the log: the command word only, never card numbers or PINs."""
        words = text.strip().split()
        return re.sub(r"[0-9]", "#", words[0].upper())[:12] if words else "(empty)"

    def answer(self, msisdn: str, text: str, request_id: str = "") -> str:
        t = " ".join(text.upper().split())
        word, _, rest = t.partition(" ")
        if t in ("", "MENU", "HELP", "HI", "HELLO", "START", "?", "0"):
            return SMS_HELP
        if t in ("BAL", "BALANCE", "1"):
            return self.pay.balance_text(msisdn)
        if t in ("BUNDLES", "BUNDLE", "DATA", "3"):
            return self.pay.bundles_text("sms")
        if word in ("BUNDLE", "DATA") and rest.strip().isdigit():
            offers = self.pay.bundles("sms")
            n = int(rest.strip())
            if not 1 <= n <= len(offers):
                return "No bundle with that number. Send BUNDLES for the list."
            return self.pay.buy_bundle_text(msisdn, offers[n - 1]["bundle_id"], "sms", request_id)
        if word in ("BUY", "AIRTIME", "TOPUP"):
            digits = re.sub(r"[^0-9]", "", rest)
            if not digits:
                return "Send BUY and the amount, for example BUY 500"
            naira = int(digits[:7])
            low, high = self.pay.airtime_limits()
            if not low <= naira <= high:
                return f"The amount must be between N{low:,} and N{high:,}."
            return self.pay.payment_text(msisdn, naira)
        if word in ("CARD", "RECHARGE", "LOAD") or re.fullmatch(r"\*?[0-9]{20}\*[0-9]{14}#?", t):
            digits = re.sub(r"[^0-9]", "", t)
            if len(digits) != 34:
                return (
                    "Send CARD, the 20-digit card number and the 14-digit PIN, "
                    "for example CARD 1234... 5678..."
                )
            return self.pay.recharge_text(msisdn, digits[:20], digits[20:])
        return "Sorry, that is not a 555 command.\n" + SMS_HELP


class SmsService:
    """HTTP endpoint the SMSC calls for every text sent to 555, and the way answers go back.

    In:  GET /sms?from=<234...>&hex=<message text, UTF-8, hex encoded>   (from the SMSC only)
    Out: GET <SMSC>/?msisdn=555&to=<234...>&hex=<answer, UTF-8, hex encoded> (the SMSC queues it)
    The request is answered at once and the command runs in the background, so the SMSC never waits
    on the payments API.
    """

    def __init__(self, commands: SmsCommands, smsc_url: str, allowed: set[str]):
        self.commands = commands
        self.smsc_url = smsc_url.rstrip("/")
        self.allowed = allowed
        self.tasks: set[asyncio.Task] = set()

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer = (writer.get_extra_info("peername") or ("?",))[0]
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            line = head.split(b"\r\n", 1)[0].decode("latin-1")
            method, _, rest = line.partition(" ")
            target = rest.rsplit(" ", 1)[0]
            path, _, query = target.partition("?")
            if peer not in self.allowed:
                log.warning("sms: refused HTTP request from %s", peer)
                return await self._reply(writer, 403, "forbidden")
            if method != "GET" or path != "/sms":
                return await self._reply(writer, 404, "not found")
            params = dict(p.partition("=")[::2] for p in query.split("&") if p)
            msisdn = urllib.parse.unquote(params.get("from", ""))
            try:
                text = bytes.fromhex(params.get("hex", "")).decode("utf-8", "replace")
            except ValueError:
                return await self._reply(writer, 400, "bad hex")
            if not MSISDN_RE.match(msisdn):
                log.warning("sms: ignored a text from a number that is not a Ratelplus number")
                return await self._reply(writer, 400, "bad from")
            await self._reply(writer, 200, "ok")
            task = asyncio.get_running_loop().create_task(self.process(msisdn, text))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        except (
            TimeoutError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            ConnectionError,
        ):
            pass
        finally:
            writer.close()

    @staticmethod
    async def _reply(writer: asyncio.StreamWriter, code: int, text: str):
        reason = {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found"}[code]
        body = text.encode()
        writer.write(
            f"HTTP/1.1 {code} {reason}\r\nContent-Type: text/plain\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
            + body
        )
        await writer.drain()

    async def process(self, msisdn: str, text: str):
        log.info("sms: %s from %s", self.commands.keyword(text), last_four(msisdn))
        answer = await asyncio.to_thread(self.commands.answer, msisdn, text, token(12))
        if len(answer) > 160:  # one SMS: the SMSC does not split long messages
            answer = answer[:157] + "..."
        ok = await asyncio.to_thread(self.send, msisdn, answer)
        log.info(
            "sms: answer to %s %s",
            last_four(msisdn),
            "queued at the SMSC" if ok else "NOT delivered to the SMSC",
        )

    def send(self, msisdn: str, text: str) -> bool:
        # Hex, not URL encoding: the SMSC's URL decoder refuses control characters such as the
        # newlines in the menu. The SMSC decodes it with {s.decode.hexa} (apply-smsc-shortcode.py).
        url = f"{self.smsc_url}/?msisdn={SMS_SHORT}&to={msisdn}&hex={text.encode('utf-8').hex()}"
        req = urllib.request.Request(  # noqa: S310  (SMS_SMSC_URL from the service's own settings, http)
            url, headers={"Content-Length": "0"}
        )  # Kamailio wants it on TCP
        try:
            with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310  (SMS_SMSC_URL from the service's own settings, http)
                return r.status == 200
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            log.warning("sms: SMSC did not take the answer: %s", type(e).__name__)
            return False


# ---------------------------------------------------------------------------------------------
# Sessions (SIP dialogs) and transactions
# ---------------------------------------------------------------------------------------------


@dataclass
class Session:
    call_id: str
    peer: tuple[str, int]  # where the S-CSCF sent the INVITE from: next hop for our requests
    remote_target: str  # the phone's Contact URI
    route_set: list[str]  # Record-Route of the INVITE, in order
    local: str  # our From for requests (the INVITE's To plus our tag)
    remote: str  # our To for requests (the INVITE's From, with its tag)
    msisdn: str | None
    invite_ok: bytes = b""  # the 200 OK to the INVITE, resent until the ACK
    invite_branch: str = ""
    acked: bool = False
    cseq: int = 0
    state: str = "new"
    choices: list[str] = field(default_factory=list)  # what the numbers in the last menu stand for
    pending: Reply | None = None  # what to send once the ACK has arrived
    last_seen: float = field(default_factory=time.monotonic)
    closed: bool = False


class UssdService(asyncio.DatagramProtocol):
    def __init__(self, public_ip: str, port: int, menu: Menu):
        self.ip = public_ip
        self.port = port
        self.menu = menu
        self.sessions: dict[str, Session] = {}
        self.out_tx: dict[str, asyncio.Task] = {}  # our request branch -> retransmit task
        self.done_responses: dict[tuple[str, str], bytes] = {}  # (branch, method) -> response
        self.transport: asyncio.DatagramTransport | None = None

    # --- network ---------------------------------------------------------------------------

    def connection_made(self, transport):
        self.transport = transport
        log.info("listening on udp %s:%d", self.ip, self.port)

    def send(self, data: bytes, addr: tuple[str, int]):
        # The method or status only, even at DEBUG: the messages carry numbers, cards and PINs.
        log.debug("send to %s:%d: %s (%d bytes)", addr[0], addr[1], first_word(data), len(data))
        self.transport.sendto(data, addr)

    def datagram_received(self, data: bytes, addr):
        if not data.strip():
            return  # keepalive
        msg = parse(data)
        if msg is None:
            log.warning("unparsable datagram from %s", addr)
            return
        log.debug("recv from %s:%d: %s (%d bytes)", addr[0], addr[1], first_word(data), len(data))
        try:
            if msg.is_request:
                self.on_request(msg, addr)
            else:
                self.on_response(msg)
        except Exception:  # one bad message must never stop the service
            log.exception("error handling %s from %s", msg.first, addr)

    # --- responses we send --------------------------------------------------------------------

    def respond(
        self,
        req: Msg,
        addr,
        code: int,
        reason: str,
        to_tag: str | None = None,
        extra: list[tuple[str, str]] | None = None,
        body: bytes = b"",
    ) -> bytes:
        hdrs = [("Via", v) for v in req.all("via")]
        hdrs.append(("From", req.get("from") or ""))
        to = req.get("to") or ""
        if to_tag and ";tag=" not in to:
            to += f";tag={to_tag}"
        hdrs += [("To", to), ("Call-ID", req.call_id), ("CSeq", req.get("cseq") or "")]
        hdrs += extra or []
        data = build(f"SIP/2.0 {code} {reason}", hdrs, body)
        self.send(data, addr)
        return data

    # --- requests from the network -----------------------------------------------------------

    def on_request(self, req: Msg, addr):
        method = req.method
        cached = self.done_responses.get((req.branch, method))
        if cached is not None and method != "ACK":  # a retransmission: answer the same again
            self.send(cached, addr)
            return
        if method == "INVITE":
            self.on_invite(req, addr)
        elif method == "ACK":
            self.on_ack(req)
        elif method == "INFO":
            self.on_info(req, addr)
        elif method == "BYE":
            s = self.sessions.get(req.call_id)
            r = self.respond(req, addr, 200, "OK")
            self.done_responses[(req.branch, method)] = r
            if s:
                log.info("session %s ended by the phone", s.call_id)
                self.close(s)
        elif method == "CANCEL":
            r = self.respond(req, addr, 200, "OK")
            self.done_responses[(req.branch, method)] = r
        elif method == "OPTIONS":
            self.respond(
                req,
                addr,
                200,
                "OK",
                to_tag=token(),
                extra=[("Allow", ALLOW), ("Accept", USSD_TYPE)],
            )
        else:
            self.respond(
                req, addr, 405, "Method Not Allowed", to_tag=token(), extra=[("Allow", ALLOW)]
            )

    def on_invite(self, req: Msg, addr):
        if req.call_id in self.sessions:  # re-INVITE: not used by USSI
            self.respond(req, addr, 488, "Not Acceptable Here")
            return
        parts = body_parts(req)
        code = ussd_string(parts.get(USSD_TYPE, b"")) or req.ruri.split(":", 1)[-1].split(";")[0]
        code = code.split("@")[0].replace("%23", "#")
        caller = req.get("p-asserted-identity") or req.get("from") or ""
        msisdn = user_digits(caller) or user_digits(req.get("from") or "")
        tag = token()
        s = Session(
            call_id=req.call_id,
            peer=addr,
            remote_target=uri_of((req.all("contact") or [""])[0]),
            route_set=req.all("record-route"),
            local=(req.get("to") or "") + f";tag={tag}",
            remote=req.get("from") or "",
            msisdn=msisdn,
            invite_branch=req.branch,
        )
        self.sessions[s.call_id] = s
        log.info("session %s from %s: %s", s.call_id, last_four(msisdn), masked_code(code))

        answer = sdp_answer(parts.get("application/sdp"), self.ip)
        extra = [("Record-Route", rr) for rr in s.route_set]
        extra += [
            ("Contact", f"<sip:ussd@{self.ip}:{self.port}>"),
            ("Recv-Info", "g.3gpp.ussd"),
            ("Allow", ALLOW),
            ("Accept", f"{USSD_TYPE}, application/sdp, multipart/mixed"),
        ]
        if answer:
            extra.append(("Content-Type", "application/sdp"))
        s.invite_ok = self.respond(
            req, addr, 200, "OK", to_tag=tag, extra=extra, body=answer or b""
        )
        self.done_responses[(req.branch, "INVITE")] = s.invite_ok
        asyncio.get_running_loop().create_task(self.resend_ok(s, addr))
        asyncio.get_running_loop().create_task(self.first_answer(s, code))

    async def first_answer(self, s: Session, code: str):
        reply = await asyncio.to_thread(self.menu.start, s, code)
        if s.acked:
            self.deliver(s, reply)
        else:
            s.pending = reply

    async def resend_ok(self, s: Session, addr):
        delay, waited = T1, 0.0
        while not s.acked and not s.closed and waited < TIMEOUT:
            await asyncio.sleep(delay)
            waited += delay
            if s.acked or s.closed:
                return
            self.send(s.invite_ok, addr)
            delay = min(delay * 2, T2)
        if not s.acked and not s.closed:
            log.warning("session %s: no ACK, giving up", s.call_id)
            self.close(s)

    def on_ack(self, req: Msg):
        s = self.sessions.get(req.call_id)
        if not s or s.acked:
            return
        s.acked = True
        s.last_seen = time.monotonic()
        if s.pending:
            reply, s.pending = s.pending, None
            self.deliver(s, reply)

    def on_info(self, req: Msg, addr):
        s = self.sessions.get(req.call_id)
        if not s:
            self.respond(req, addr, 481, "Call/Transaction Does Not Exist")
            return
        r = self.respond(req, addr, 200, "OK")
        self.done_responses[(req.branch, "INFO")] = r
        s.last_seen = time.monotonic()
        parts = body_parts(req)
        xml = parts.get(USSD_TYPE, b"")
        if re.search(rb"<error-code>", xml):
            log.info("session %s: phone sent an error, closing", s.call_id)
            self.send_request(s, "BYE")
            return
        text = ussd_string(xml)
        if text is None:
            return
        # Only the length: an answer can be a card number and PIN, an amount or a phone number.
        log.info("session %s: user answered (%d characters)", s.call_id, len(text))
        asyncio.get_running_loop().create_task(self.next_answer(s, text))

    async def next_answer(self, s: Session, text: str):
        reply = await asyncio.to_thread(self.menu.answer, s, text)
        self.deliver(s, reply)

    def deliver(self, s: Session, reply: Reply):
        if s.closed:
            return
        # Not the text: it can hold the customer's balance or bundles.
        log.info(
            "session %s: %s, %d characters",
            s.call_id,
            "BYE" if reply.end else "INFO",
            len(reply.text),
        )
        self.send_request(s, "BYE" if reply.end else "INFO", ussd_xml(reply.text))

    # --- requests we send -------------------------------------------------------------------

    def send_request(self, s: Session, method: str, body: bytes = b""):
        s.cseq += 1
        branch = "z9hG4bK" + token(16)
        hdrs = [("Via", f"SIP/2.0/UDP {self.ip}:{self.port};branch={branch};rport")]
        hdrs += [("Route", r) for r in s.route_set]
        hdrs += [
            ("Max-Forwards", "70"),
            ("From", s.local),
            ("To", s.remote),
            ("Call-ID", s.call_id),
            ("CSeq", f"{s.cseq} {method}"),
            ("Contact", f"<sip:ussd@{self.ip}:{self.port}>"),
        ]
        if body:
            hdrs += [("Info-Package", "g.3gpp.ussd")] if method == "INFO" else []
            hdrs += [("Content-Type", USSD_TYPE), ("Content-Disposition", "Info-Package")]
        data = build(f"{method} {s.remote_target} SIP/2.0", hdrs, body)
        self.out_tx[branch] = asyncio.get_running_loop().create_task(
            self.resend_request(s, branch, data, method)
        )
        self.send(data, s.peer)
        if method == "BYE":
            s.state = "ending"

    async def resend_request(self, s: Session, branch: str, data: bytes, method: str):
        delay, waited = T1, 0.0
        while waited < TIMEOUT:
            await asyncio.sleep(delay)
            waited += delay
            if branch not in self.out_tx:
                return
            self.send(data, s.peer)
            delay = min(delay * 2, T2)
        self.out_tx.pop(branch, None)
        log.warning("session %s: no answer to our %s, closing", s.call_id, method)
        self.close(s)

    def on_response(self, resp: Msg):
        branch = resp.branch
        if resp.status < 200:
            return
        task = self.out_tx.pop(branch, None)
        if task:
            task.cancel()
        s = self.sessions.get(resp.call_id)
        if not s:
            return
        s.last_seen = time.monotonic()
        method = resp.cseq_method
        if method == "BYE":
            log.info("session %s closed (%d)", s.call_id, resp.status)
            self.close(s)
        elif method == "INFO" and resp.status >= 300:
            log.info("session %s: phone refused INFO (%d), closing", s.call_id, resp.status)
            self.send_request(s, "BYE")

    def close(self, s: Session):
        s.closed = True
        self.sessions.pop(s.call_id, None)

    async def housekeeping(self):
        while True:
            await asyncio.sleep(10)
            now = time.monotonic()
            for s in list(self.sessions.values()):
                if now - s.last_seen > SESSION_IDLE:
                    log.info("session %s idle, closing", s.call_id)
                    if s.acked:
                        self.send_request(s, "BYE", ussd_xml("Session timed out."))
                    self.close(s)
            if len(self.done_responses) > 2000:  # keep the retransmission cache small
                for k in list(self.done_responses)[:1000]:
                    self.done_responses.pop(k, None)


async def main():
    logging.basicConfig(
        level=os.environ.get("USSD_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    public_ip = os.environ["USSD_PUBLIC_IP"]
    port = int(os.environ.get("USSD_PORT", "5060"))
    key = None
    key_file = os.environ.get("RATEL_PAY_KEY_FILE")
    if key_file and os.path.exists(key_file):
        key = open(key_file).read().strip() or None
    pay = PayApi(os.environ.get("RATEL_PAY_URL"), key)
    log.info(
        "payments API: %s",
        "configured" if pay.ready else "not configured (menu answers 'not available yet')",
    )
    service = UssdService(public_ip, port, Menu(pay))
    loop = asyncio.get_running_loop()
    # Inside the ussd container: the S-CSCF reaches it over the Docker network.
    bind = os.environ.get("USSD_BIND_IP", "0.0.0.0")  # noqa: S104
    await loop.create_datagram_endpoint(lambda: service, local_addr=(bind, port))
    sms_port = os.environ.get("SMS_PORT")
    if sms_port:
        sms = SmsService(
            SmsCommands(pay),
            os.environ.get("SMS_SMSC_URL", "http://172.22.0.33:7090"),
            set(os.environ.get("SMS_ALLOWED", "172.22.0.33").split(",")),
        )
        await asyncio.start_server(sms.handle, bind, int(sms_port))
        log.info("sms: short number %s listening on tcp %s:%s", SMS_SHORT, bind, sms_port)
    await service.housekeeping()


def send_sms_cli(args: list[str]) -> int:
    """One SMS from 555 to args[0], the text read from standard input. 0 when the SMSC took it."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(args) != 1 or not re.fullmatch(r"234[0-9]{10}", args[0]):
        log.error("send-sms: give one number in 234 form")
        return 2
    text = sys.stdin.read().strip()
    if not text or len(text) > 160:
        log.error("send-sms: the text must be 1 to 160 characters (one SMS)")
        return 2
    sms = SmsService(
        SmsCommands(PayApi(None, None)),
        os.environ.get("SMS_SMSC_URL", "http://172.22.0.33:7090"),
        set(),
    )
    ok = sms.send(args[0], text)
    log.info(
        "send-sms: to %s %s",
        last_four(args[0]),
        "queued at the SMSC" if ok else "NOT taken by the SMSC",
    )
    return 0 if ok else 1


if __name__ == "__main__":
    if sys.argv[1:2] == ["--send-sms"]:
        sys.exit(send_sms_cli(sys.argv[2:]))
    asyncio.run(main())
