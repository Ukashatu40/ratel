#!/usr/bin/env bash
# Start (or restart) the USSD and SMS 555 service container on the voice VM.
#
# It joins the IMS network (ratel_ims) at 172.22.0.40 and runs ussd_as.py from this folder in a
# stock python image, nothing installed. Restarts with Docker. Changes nothing else: calls do not
# pass through it. USSD reaches it only through the S-CSCF rule, texts to 555 only through the
# SMSC change (apply-smsc-shortcode.py). It listens on udp 5060 (USSD) and tcp 8647 (texts from the SMSC).
#
# Usage: ./run-ussd.sh            start or replace the container
#        ./run-ussd.sh --stop     stop and remove it
#
# Payments API: put bss-app's base URL in ussd.env as RATEL_PAY_URL=https://... and copy bss-app's
# certificate next to this script as bss-ca.pem (cp /etc/ratel-meter/trusted-certs.pem bss-ca.pem).
# No key is needed: bss-app's nginx adds it on the public payment paths. A key, if ever needed,
# goes alone in pay.key (chmod 600). None of these files is in the repository.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
NAME=ussd
NET=ratel_ims
IP=172.22.0.40
IMAGE=python:3.12-slim

if [ "${1:-}" = --stop ]; then
	docker rm -f "$NAME" >/dev/null 2>&1 && echo "stopped $NAME" || echo "$NAME was not running"
	exit 0
fi

docker network inspect "$NET" >/dev/null
docker pull -q "$IMAGE" >/dev/null
docker rm -f "$NAME" >/dev/null 2>&1 || true

ENVFILE=()
[ -f "$HERE/ussd.env" ] && ENVFILE=(--env-file "$HERE/ussd.env")
KEY=()
[ -f "$HERE/pay.key" ] && KEY=(-v "$HERE/pay.key:/run/ussd/pay.key:ro" -e RATEL_PAY_KEY_FILE=/run/ussd/pay.key)
CA=()  # bss-app's self-signed certificate, the same file the call agent trusts
[ -f "$HERE/bss-ca.pem" ] && CA=(-v "$HERE/bss-ca.pem:/run/ussd/bss-ca.pem:ro" -e SSL_CERT_FILE=/run/ussd/bss-ca.pem)

docker run -d --name "$NAME" --restart unless-stopped \
	--network "$NET" --ip "$IP" \
	-e USSD_PUBLIC_IP="$IP" -e USSD_PORT=5060 -e USSD_LOG_LEVEL=INFO \
	-e SMS_PORT=8647 -e SMS_SMSC_URL=http://172.22.0.33:7090 -e SMS_ALLOWED=172.22.0.33 \
	"${ENVFILE[@]}" "${KEY[@]}" "${CA[@]}" \
	-v "$HERE/ussd_as.py:/app/ussd_as.py:ro" \
	--log-opt max-size=10m --log-opt max-file=3 \
	"$IMAGE" python -I /app/ussd_as.py >/dev/null

sleep 2
docker ps --filter "name=^${NAME}$" --format "{{.Names}}\t{{.Status}}"
docker logs "$NAME" 2>&1 | tail -3
echo "--- answers SIP OPTIONS? ---"
python3 - "$IP" <<'PY'
import socket, sys
ip = sys.argv[1]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(3); s.bind(("0.0.0.0", 0))
port = s.getsockname()[1]
msg = (f"OPTIONS sip:ussd@{ip}:5060 SIP/2.0\r\nVia: SIP/2.0/UDP 172.22.0.1:{port};branch=z9hG4bKprobe\r\n"
       f"From: <sip:probe@172.22.0.1>;tag=p\r\nTo: <sip:ussd@{ip}>\r\nCall-ID: probe-{port}\r\n"
       f"CSeq: 1 OPTIONS\r\nMax-Forwards: 70\r\nContent-Length: 0\r\n\r\n")
s.sendto(msg.encode(), (ip, 5060))
try:
    print(s.recv(4096).decode().splitlines()[0])
except socket.timeout:
    print("NO ANSWER")
PY
echo "--- 555 SMS port refuses a caller that is not the SMSC? (want 403) ---"
python3 - "$IP" <<'PY'
import http.client, sys
try:
    c = http.client.HTTPConnection(sys.argv[1], 8647, timeout=3)
    c.request("GET", "/sms?from=2340000000000&hex=6869")
    print(c.getresponse().status)
except OSError as e:
    print("NO ANSWER", type(e).__name__)
PY
