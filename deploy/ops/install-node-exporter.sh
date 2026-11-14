#!/usr/bin/env bash
# RatelOps: node_exporter on an existing host (core-cp, core-up, the voice VM or bss-app).
#
# This installs NO packages. It is one static binary from the upstream release, SHA-256 checked, and
# a systemd unit. Nothing already running is restarted and no configuration of anything else is
# touched. On a core host that matters: this is additive.
#
# It binds to the host's own LAN address so RatelOps can scrape it. That address is public, so the
# port stays unreachable until the host's firewall rule is added, which is a separate step on
# purpose (deploy/firewall/). Install this first, open the port second, and at no point is an
# unprotected port exposed.
#
# Safe to run again.
#
# Usage:
#   sudo ./install-node-exporter.sh /path/to/node_exporter   # from a binary you copied here
#   sudo ./install-node-exporter.sh                          # download it, needs the internet
#
# Prefer the first form. core-cp, core-up, the voice VM and bss-app have no outbound internet, and
# they should not: a host that needs to reach GitHub to be monitored is a dependency you do not
# want in a core. Copy the binary from the ops VM, which already has a checked copy at
# /usr/local/bin/node_exporter.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
	echo "run with sudo" >&2
	exit 1
fi

ARCH=linux-amd64
PORT=9100
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# The address the radios and the other hosts know this host by: its global IPv4 address. Binding to
# it rather than 0.0.0.0 keeps the exporter off any other interface this host may grow later.
BIND=$(ip -4 -o addr show scope global | awk '{print $4}' | cut -d/ -f1 | head -1)
[ -n "$BIND" ] || {
	echo "could not work out this host's address" >&2
	exit 1
}
echo "host address: $BIND"

SRC=${1:-}
if [ -n "$SRC" ]; then
	[ -f "$SRC" ] || {
		echo "no such file: $SRC" >&2
		exit 1
	}
	chmod +x "$SRC"
	VER=$("$SRC" --version 2>&1 | sed -n 's/.*version \([0-9][0-9.]*\).*/\1/p' | head -1)
	[ -n "$VER" ] || {
		echo "$SRC does not look like node_exporter" >&2
		exit 1
	}
	BIN=$SRC
	echo "using the copy you provided: node_exporter $VER"
else
	VER=$(curl -4 -fsSL https://api.github.com/repos/prometheus/node_exporter/releases/latest |
		sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p' | head -1)
	[ -n "$VER" ] || {
		echo "could not read the latest node_exporter version from github" >&2
		echo "this host may have no outbound internet: copy the binary here and pass its path" >&2
		exit 1
	}
	BASE=node_exporter-$VER.$ARCH
	URL=https://github.com/prometheus/node_exporter/releases/download/v$VER
	curl -4 -fsSL -o "$WORK/$BASE.tar.gz" "$URL/$BASE.tar.gz"
	curl -4 -fsSL -o "$WORK/sums.txt" "$URL/sha256sums.txt"
	(cd "$WORK" && grep " $BASE.tar.gz\$" sums.txt | sha256sum -c -) >&2
	tar -xzf "$WORK/$BASE.tar.gz" -C "$WORK"
	BIN=$WORK/$BASE/node_exporter
fi

id node_exporter >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin node_exporter
install -m 0755 "$BIN" /usr/local/bin/node_exporter

cat >/etc/systemd/system/node_exporter.service <<UNIT
[Unit]
Description=Prometheus node exporter (RatelOps)
After=network-online.target
Wants=network-online.target

[Service]
User=node_exporter
Group=node_exporter
ExecStart=/usr/local/bin/node_exporter --web.listen-address=$BIND:$PORT
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
LockPersonality=true

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now node_exporter.service
systemctl restart node_exporter.service
sleep 2

echo "--- service ---"
systemctl is-active node_exporter.service
echo "--- listening ---"
ss -ltn "sport = :$PORT" | tail -n +2
echo "--- it answers locally ---"
curl -4 -fsS -o /dev/null -w "http=%{http_code}\n" "http://$BIND:$PORT/metrics"
echo
echo "installed node_exporter $VER on $BIND:$PORT"
echo "Not reachable from RatelOps until this host's firewall rule is added."
