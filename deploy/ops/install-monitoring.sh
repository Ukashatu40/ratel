#!/usr/bin/env bash
# RatelOps: Prometheus and node_exporter on the ops VM, from upstream releases.
#
# Ubuntu's own prometheus package is years behind, so this takes the upstream tarball, checks its
# SHA-256 against the release's own sums file, and runs it under systemd as an unprivileged user.
#
# Both listen on 127.0.0.1 only. Grafana runs on the same host and reaches them there, so nothing
# here opens a port to the LAN. The exporters on the other hosts are a separate step.
#
# Safe to run again: it reinstalls the current upstream version and restarts the two services.
#
# Usage: sudo ./install-monitoring.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
	echo "run with sudo" >&2
	exit 1
fi

ARCH=linux-amd64
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# This network answers DNS with IPv6 addresses but has no IPv6 route, so anything that prefers AAAA
# stalls until it times out: curl, apt, Grafana's repo. Tell glibc to prefer IPv4 instead of
# switching IPv6 off, so the day the network does route it, this host just works.
if ! grep -q '^precedence ::ffff:0:0/96' /etc/gai.conf 2>/dev/null; then
	printf '\n# RatelOps: prefer IPv4, this network resolves AAAA but does not route it.\nprecedence ::ffff:0:0/96  100\n' >>/etc/gai.conf
	echo "set IPv4 preference in /etc/gai.conf"
fi

latest() { # repo -> version without the leading v
	curl -4 -fsSL "https://api.github.com/repos/prometheus/$1/releases/latest" |
		sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p' | head -1
}

fetch() { # repo version -> extracted directory in $WORK, SHA-256 checked
	local repo=$1 ver=$2 base=$1-$2.$ARCH
	local url=https://github.com/prometheus/$repo/releases/download/v$ver
	curl -4 -fsSL -o "$WORK/$base.tar.gz" "$url/$base.tar.gz"
	curl -4 -fsSL -o "$WORK/sums-$repo.txt" "$url/sha256sums.txt"
	# The check's own output goes to stderr: this function returns a path on stdout.
	(cd "$WORK" && grep " $base.tar.gz\$" "sums-$repo.txt" | sha256sum -c -) >&2
	tar -xzf "$WORK/$base.tar.gz" -C "$WORK"
	echo "$WORK/$base"
}

PROM_VER=$(latest prometheus)
NODE_VER=$(latest node_exporter)
[ -n "$PROM_VER" ] && [ -n "$NODE_VER" ] || {
	echo "could not read the latest versions from github" >&2
	exit 1
}
echo "prometheus $PROM_VER, node_exporter $NODE_VER"

PROM_DIR=$(fetch prometheus "$PROM_VER")
NODE_DIR=$(fetch node_exporter "$NODE_VER")

id prometheus >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin prometheus
id node_exporter >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin node_exporter

install -m 0755 "$PROM_DIR/prometheus" "$PROM_DIR/promtool" /usr/local/bin/
install -m 0755 "$NODE_DIR/node_exporter" /usr/local/bin/
install -d -o prometheus -g prometheus -m 0750 /var/lib/prometheus
install -d -m 0755 /etc/prometheus

# Only written the first time. After that the file is the operator's, and the repo's copy in
# ops/prometheus/prometheus.yml is what gets edited and copied here.
if [ ! -f /etc/prometheus/prometheus.yml ]; then
	cat >/etc/prometheus/prometheus.yml <<'YAML'
# RatelOps. Keep this in step with ops/prometheus/prometheus.yml in the ratel repository.
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    network: ratelplus

scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: ["127.0.0.1:9090"]

  - job_name: node
    static_configs:
      - targets: ["127.0.0.1:9100"]
        labels: { host: ops }
YAML
	chown root:prometheus /etc/prometheus/prometheus.yml
	chmod 0640 /etc/prometheus/prometheus.yml
fi

cat >/etc/systemd/system/node_exporter.service <<'UNIT'
[Unit]
Description=Prometheus node exporter
After=network-online.target
Wants=network-online.target

[Service]
User=node_exporter
Group=node_exporter
ExecStart=/usr/local/bin/node_exporter --web.listen-address=127.0.0.1:9100
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

cat >/etc/systemd/system/prometheus.service <<'UNIT'
[Unit]
Description=Prometheus
After=network-online.target
Wants=network-online.target

[Service]
User=prometheus
Group=prometheus
ExecStart=/usr/local/bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/var/lib/prometheus \
  --storage.tsdb.retention.time=90d \
  --web.listen-address=127.0.0.1:9090
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/prometheus
ProtectHome=true
PrivateTmp=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
LockPersonality=true

[Install]
WantedBy=multi-user.target
UNIT

promtool check config /etc/prometheus/prometheus.yml

systemctl daemon-reload
systemctl enable --now node_exporter.service prometheus.service
systemctl restart node_exporter.service prometheus.service

sleep 3
systemctl is-active node_exporter.service prometheus.service
echo "--- what prometheus is scraping ---"
curl -4 -fsS "http://127.0.0.1:9090/api/v1/targets?state=active" |
	sed -n 's/.*"job":"\([^"]*\)".*"health":"\([^"]*\)".*/\1 \2/p' | sort -u || true
curl -4 -fsS "http://127.0.0.1:9090/api/v1/query?query=up" | head -c 400
echo
echo "installed: prometheus $PROM_VER, node_exporter $NODE_VER"
