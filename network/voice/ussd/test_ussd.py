#!/usr/bin/env python3
"""Plays a phone (behind the S-CSCF) against ussd_as.py over UDP on localhost.

Starts the service with a fake payments API, runs whole USSD sessions and checks every step.
"""

import json
import tempfile
import os
import re
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
KEYFILE = os.path.join(tempfile.mkdtemp(prefix="ussd-test-"), "test.key")
AS = ("127.0.0.1", 15060)
BOUNDARY = "ratelboundary"


class FakePay(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *a):
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        FakePay.calls.append(("GET", self.path, self.headers.get("Authorization")))
        if self.path.endswith("/balance"):
            return self._send(200, {"balance_kobo": 123450})
        if self.path == "/v1/pay/bundles":
            return self._send(200, {"bundles": [{"bundle_id": 1, "name": "1GB", "price_kobo": 50000}]})
        self._send(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakePay.calls.append(("POST", self.path, body, self.headers.get("Idempotency-Key")))
        if self.path == "/v1/pay/payments":
            return self._send(200, {"payment_id": "p1", "status": "pending",
                                    "amount_kobo": body["amount_kobo"],
                                    "checkout_url": "https://checkout.paystack.com/abc123"})
        if self.path == "/v1/pay/vouchers/redeem":
            if body["pin"] == "11111111111111":
                return self._send(400, {})
            return self._send(200, {"amount_kobo": 50000, "balance_kobo": 173450})
        self._send(404, {})


def parse(data):
    head, _, body = data.partition(b"\r\n\r\n")
    lines = head.decode().split("\r\n")
    hdrs = {}
    for ln in lines[1:]:
        n, _, v = ln.partition(":")
        hdrs.setdefault(n.strip().lower(), []).append(v.strip())
    return lines[0], hdrs, body


class Phone:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(5)
        self.port = self.sock.getsockname()[1]
        self.cid = f"test-{time.time_ns()}"
        self.cseq = 1

    def recv(self):
        data, _ = self.sock.recvfrom(65535)
        return parse(data)

    def send(self, text, body=b""):
        msg = text.replace("\n", "\r\n") + f"Content-Length: {len(body)}\r\n\r\n"
        self.sock.sendto(msg.encode() + body, AS)

    def invite(self, code):
        xml = (f'<?xml version="1.0" encoding="UTF-8"?><ussd-data><language>en</language>'
               f"<ussd-string>{code}</ussd-string></ussd-data>")
        sdp = "v=0\r\no=- 1 1 IN IP4 10.46.0.11\r\ns=-\r\nc=IN IP4 10.46.0.11\r\nt=0 0\r\nm=audio 0 RTP/AVP 0\r\n"
        body = (f"--{BOUNDARY}\r\nContent-Type: application/sdp\r\n\r\n{sdp}\r\n"
                f"--{BOUNDARY}\r\nContent-Type: application/vnd.3gpp.ussd+xml\r\n"
                f"Content-Disposition: render;handling=optional\r\n\r\n{xml}\r\n--{BOUNDARY}--\r\n").encode()
        self.send(
            f"INVITE tel:{code};phone-context=eps.ims.mnc002.mcc621.3gppnetwork.org SIP/2.0\n"
            f"Via: SIP/2.0/UDP 127.0.0.1:{self.port};branch=z9hG4bKinv{self.cid}\n"
            f"Via: SIP/2.0/UDP 10.46.0.11:5090;branch=z9hG4bKue1\n"
            "Record-Route: <sip:mo@127.0.0.1:6060;lr>\n"
            "Record-Route: <sip:mo@172.22.0.21;lr>\n"
            f"From: <sip:2348000000901@ims.mnc002.mcc621.3gppnetwork.org>;tag=ue{self.cid}\n"
            "To: <tel:*123%23>\n"
            f"Call-ID: {self.cid}\nCSeq: 1 INVITE\n"
            "Contact: <sip:621000000000901@10.46.0.11:5090>\n"
            "P-Asserted-Identity: <sip:2348000000901@ims.mnc002.mcc621.3gppnetwork.org>\n"
            "Recv-Info: g.3gpp.ussd\n"
            f"Content-Type: multipart/mixed;boundary={BOUNDARY}\n", body)

    def ack(self, to):
        self.send(f"ACK sip:ussd@127.0.0.1:15060 SIP/2.0\n"
                  f"Via: SIP/2.0/UDP 127.0.0.1:{self.port};branch=z9hG4bKack{time.time_ns()}\n"
                  f"From: <sip:2348000000901@ims.mnc002.mcc621.3gppnetwork.org>;tag=ue{self.cid}\n"
                  f"To: {to}\nCall-ID: {self.cid}\nCSeq: 1 ACK\n")

    def ok_to(self, first, hdrs):
        vias = "".join(f"Via: {v}\n" for v in hdrs["via"])
        self.send(f"SIP/2.0 200 OK\n{vias}From: {hdrs['from'][0]}\nTo: {hdrs['to'][0]}\n"
                  f"Call-ID: {hdrs['call-id'][0]}\nCSeq: {hdrs['cseq'][0]}\n")

    def info(self, to, text):
        self.cseq += 1
        xml = f'<?xml version="1.0" encoding="UTF-8"?><ussd-data><ussd-string>{text}</ussd-string></ussd-data>'
        self.send(f"INFO sip:ussd@127.0.0.1:15060 SIP/2.0\n"
                  f"Via: SIP/2.0/UDP 127.0.0.1:{self.port};branch=z9hG4bKinfo{time.time_ns()}\n"
                  f"From: <sip:2348000000901@ims.mnc002.mcc621.3gppnetwork.org>;tag=ue{self.cid}\n"
                  f"To: {to}\nCall-ID: {self.cid}\nCSeq: {self.cseq} INFO\n"
                  "Info-Package: g.3gpp.ussd\nContent-Type: application/vnd.3gpp.ussd+xml\n", xml.encode())

    def expect(self, want_first):
        while True:
            first, hdrs, body = self.recv()
            if first.startswith(want_first):
                return first, hdrs, body
            print(f"   (skipping {first})")


def text_of(body):
    m = re.search(rb"<ussd-string>(.*?)</ussd-string>", body, re.S)
    return m.group(1).decode() if m else None


def session(code, answers, ignore_first_ok=False):
    p = Phone()
    p.invite(code)
    first, hdrs, body = p.expect("SIP/2.0 200")
    assert "g.3gpp.ussd" in hdrs.get("recv-info", [""])[0], "200 OK without Recv-Info"
    assert b"m=audio 0" in body, "SDP answer must reject media with port 0"
    assert hdrs["record-route"] == ["<sip:mo@127.0.0.1:6060;lr>", "<sip:mo@172.22.0.21;lr>"], hdrs["record-route"]
    to = hdrs["to"][0]
    if ignore_first_ok:  # do not ACK: the service must send the 200 OK again
        first, hdrs, body = p.expect("SIP/2.0 200")
        print("   200 OK retransmitted as required")
    p.ack(to)
    texts = []
    for ans in answers + [None]:
        first, hdrs, body = p.recv()
        method = first.split()[0]
        assert method in ("INFO", "BYE"), first
        assert first.split()[1] == "sip:621000000000901@10.46.0.11:5090", "Request-URI must be the phone's Contact"
        assert hdrs["route"] == ["<sip:mo@127.0.0.1:6060;lr>", "<sip:mo@172.22.0.21;lr>"], hdrs.get("route")
        assert "application/vnd.3gpp.ussd+xml" in hdrs["content-type"][0]
        if method == "INFO":
            assert hdrs["info-package"][0] == "g.3gpp.ussd"
        texts.append((method, text_of(body)))
        p.ok_to(first, hdrs)
        if method == "BYE":
            break
        p.info(to, ans)
        p.expect("SIP/2.0 200")  # the service's 200 OK to our INFO
    return texts


def run(env_extra):
    env = {**os.environ, "USSD_PUBLIC_IP": "127.0.0.1", "USSD_PORT": "15060",
           "USSD_BIND_IP": "127.0.0.1", "USSD_LOG_LEVEL": "INFO", **env_extra}
    proc = subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "ussd_as.py")], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(1)
    return proc


class FakeSmsc(BaseHTTPRequestHandler):
    """Plays the SMSC's HTTP entry point: records every answer the 647 service queues."""
    sent = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)
        FakeSmsc.sent.append({k: v[0] for k, v in q.items()})
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"OK")


def sms_get(path):
    """One request to the 647 service as the SMSC would make it; returns the HTTP status."""
    import http.client
    c = http.client.HTTPConnection("127.0.0.1", 18647, timeout=5)
    c.request("GET", path)
    status = c.getresponse().status
    c.close()
    return status


def sms_case(msisdn, text):
    before = len(FakeSmsc.sent)
    status = sms_get(f"/sms?from={msisdn}&hex={text.encode().hex()}")
    for _ in range(50):
        if len(FakeSmsc.sent) > before:
            return status, FakeSmsc.sent[-1]
        time.sleep(0.1)
    return status, None


def sms_tests():
    failures = 0
    smsc = HTTPServer(("127.0.0.1", 17090), FakeSmsc)
    threading.Thread(target=smsc.serve_forever, daemon=True).start()
    proc = run({"RATEL_PAY_URL": "http://127.0.0.1:18080", "RATEL_PAY_KEY_FILE": KEYFILE,
                "SMS_PORT": "18647", "SMS_SMSC_URL": "http://127.0.0.1:17090", "SMS_ALLOWED": "127.0.0.1"})
    me = "2348000000902"
    cases = [
        ("menu", lambda a: a.startswith("Ratelplus 647\nBAL")),
        ("bal", lambda a: a == "Your balance is N1,234.50"),
        ("Buy 500", lambda a: a == "Pay N500 at https://checkout.paystack.com/abc123"),
        ("BUY 20", lambda a: a.startswith("The amount must be between")),
        ("bundles", lambda a: a == "Bundles\n1GB N500.00"),
        ("CARD 1234 5678 9012 3456 7890 2222 2222 2222 22", lambda a: a.startswith("Recharge of N500.00 successful")),
        ("*12345678901234567890*11111111111111#", lambda a: a == "This card cannot be used."),
        ("card 123", lambda a: a.startswith("Send CARD")),
        ("hello there & more = 100%", lambda a: a.startswith("Sorry, that is not a 647 command.")),
    ]
    try:
        for text, check in cases:
            status, sent = sms_case(me, text)
            ok = status == 200 and sent is not None and sent.get("msisdn") == "647" \
                and sent.get("to") == me and check(sent.get("text", "")) and len(sent["text"]) <= 160
            print(f"   {'ok ' if ok else 'FAIL'} {text!r} -> {sent and sent.get('text')!r}")
            failures += not ok
        for path, want in [("/sms?from=999&hex=6869", 400), ("/sms?from=" + me + "&hex=zz", 400),
                           ("/other", 404)]:
            got = sms_get(path)
            print(f"   {'ok ' if got == want else 'FAIL'} {path} -> {got} (want {want})")
            failures += got != want
    finally:
        proc.terminate()
        out = proc.communicate()[0]
        print("".join("   | " + ln + "\n" for ln in out.splitlines()[-6:]))
        if "Traceback" in out:
            failures += 1
            print("FAIL: the service logged a traceback")
        if "1234567890" in out or "22222222" in out:
            failures += 1
            print("FAIL: a card number or PIN reached the log")
    smsc.shutdown()
    proc = run({"SMS_PORT": "18647", "SMS_SMSC_URL": "http://127.0.0.1:17090", "SMS_ALLOWED": "172.22.0.33"})
    try:
        got = sms_get(f"/sms?from={me}&hex=6869")
        print(f"   {'ok ' if got == 403 else 'FAIL'} request from a non-SMSC address -> {got} (want 403)")
        failures += got != 403
    finally:
        proc.terminate()
        proc.communicate()
    return failures


def main():
    httpd = HTTPServer(("127.0.0.1", 18080), FakePay)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    keyfile = KEYFILE
    open(keyfile, "w").write("test-key")

    failures = 0
    print("== without the payments API")
    proc = run({})
    try:
        t = session("*123#", ["1"], ignore_first_ok=True)
        print("  ", t)
        assert t[0] == ("INFO", "Ratelplus\n1. My balance\n2. Buy airtime\n3. Buy a bundle\n4. Recharge card")
        assert t[1][0] == "BYE" and "not available yet" in t[1][1]
    except AssertionError as e:
        failures += 1
        print("FAIL", e)
    finally:
        proc.terminate()
        print("".join("   | " + ln + "\n" for ln in proc.communicate()[0].splitlines()[-6:]))

    print("== with the payments API")
    proc = run({"RATEL_PAY_URL": "http://127.0.0.1:18080", "RATEL_PAY_KEY_FILE": keyfile})
    cases = [
        ("*123#", ["1"], "Your balance is N1,234.50"),
        ("*123#", ["2", "3"], "Pay N500 at https://checkout.paystack.com/abc123"),
        ("*123#", ["3"], "Bundles\n1GB N500.00"),
        ("*123#", ["4", "12345678901234567890*22222222222222"], "Recharge of N500.00 successful. New balance N1,734.50"),
        ("*123*12345678901234567890*11111111111111#", [], "This card cannot be used."),
        ("*123#", ["9"], "Invalid choice. Dial *123# to start again."),
        ("*999#", [], "Unknown service code. Dial *123# for the Ratelplus menu."),
    ]
    try:
        for code, answers, want in cases:
            try:
                t = session(code, answers)
                got = t[-1]
                ok = got == ("BYE", want)
                print(f"   {'ok ' if ok else 'FAIL'} {code} {answers} -> {got[1]!r}")
                if not ok:
                    failures += 1
            except Exception as e:
                failures += 1
                print("   FAIL", code, answers, repr(e))
        auth = {c[2] for c in FakePay.calls if c[0] == "GET"}
        assert auth == {"Bearer test-key"}, auth
        pays = [c for c in FakePay.calls if c[1] == "/v1/pay/payments"]
        assert pays and pays[0][2] == {"msisdn": "2348000000901", "amount_kobo": 50000} and pays[0][3], pays
        print("   payments API called with the key, the caller's number and an Idempotency-Key")
    except AssertionError as e:
        failures += 1
        print("FAIL", e)
    finally:
        proc.terminate()
        out = proc.communicate()[0]
        print("".join("   | " + ln + "\n" for ln in out.splitlines()[-8:]))
        if "Traceback" in out:
            failures += 1
            print("FAIL: the service logged a traceback")
    print("== SMS short number 647")
    failures += sms_tests()
    httpd.shutdown()
    print("ALL PASSED" if failures == 0 else f"{failures} FAILED")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
