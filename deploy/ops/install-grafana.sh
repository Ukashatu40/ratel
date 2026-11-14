#!/usr/bin/env bash
# RatelOps: Grafana on the ops VM, from Grafana's own apt repository.
#
# Ubuntu's packaged Grafana is far behind, so this uses the upstream repository with its signing key
# in /etc/apt/keyrings, the current Debian way, not apt-key.
#
# Grafana listens on 127.0.0.1:3000 ONLY. These hosts are on public addresses, so a dashboard bound
# to 0.0.0.0 would be on the internet, and Grafana ships with admin/admin. Reach it from your own
# machine with an SSH tunnel instead:
#
#   ssh -N -L 3000:127.0.0.1:3000 ratel-ops      # then open http://127.0.0.1:3000
#
# The Prometheus datasource is provisioned from a file, so it exists on a fresh install and is not
# something somebody has to remember to click. Datasources that need a password, such as RatelBSS's
# Postgres, are deliberately NOT here: they go in their own provisioning file with the secret in an
# environment file, and that is a separate step.
#
# Safe to run again.
#
# Usage: sudo ./install-grafana.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
	echo "run with sudo" >&2
	exit 1
fi

export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y -qq apt-transport-https software-properties-common gnupg curl >/dev/null

install -d -m 0755 /etc/apt/keyrings
curl -4 -fsSL https://apt.grafana.com/gpg.key | gpg --dearmor --yes -o /etc/apt/keyrings/grafana.gpg
chmod 0644 /etc/apt/keyrings/grafana.gpg
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" \
	>/etc/apt/sources.list.d/grafana.list

apt-get update -qq
apt-get install -y -qq grafana >/dev/null

# Bind to loopback. Written as a drop-in rather than editing grafana.ini, so a package upgrade
# cannot quietly take it away and put Grafana back on 0.0.0.0.
install -d -m 0755 /etc/systemd/system/grafana-server.service.d
cat >/etc/systemd/system/grafana-server.service.d/10-ratel-bind.conf <<'UNIT'
[Service]
# These hosts have public addresses. Grafana is reached through an SSH tunnel, never directly.
Environment=GF_SERVER_HTTP_ADDR=127.0.0.1
Environment=GF_SERVER_HTTP_PORT=3000
Environment=GF_SERVER_DOMAIN=localhost
Environment=GF_ANALYTICS_REPORTING_ENABLED=false
Environment=GF_ANALYTICS_CHECK_FOR_UPDATES=false
Environment=GF_USERS_ALLOW_SIGN_UP=false
UNIT

install -d -m 0755 /etc/grafana/provisioning/datasources
cat >/etc/grafana/provisioning/datasources/10-prometheus.yaml <<'YAML'
# RatelOps. Keep this in step with ops/grafana/datasources/10-prometheus.yaml in the ratel repository.
apiVersion: 1
datasources:
  - name: Prometheus
    uid: ratel-prometheus
    type: prometheus
    access: proxy
    url: http://127.0.0.1:9090
    isDefault: true
    jsonData:
      timeInterval: 15s
      httpMethod: POST
YAML
chown root:grafana /etc/grafana/provisioning/datasources/10-prometheus.yaml
chmod 0640 /etc/grafana/provisioning/datasources/10-prometheus.yaml

systemctl daemon-reload
systemctl enable --now grafana-server.service
systemctl restart grafana-server.service

for _ in $(seq 1 30); do
	curl -4 -fsS -o /dev/null http://127.0.0.1:3000/api/health 2>/dev/null && break
	sleep 2
done

echo "--- health ---"
curl -4 -sS http://127.0.0.1:3000/api/health
echo
echo "--- what it is listening on (must be 127.0.0.1 only) ---"
ss -ltnp 2>/dev/null | grep -E ':3000|:9090|:9100' || true
echo
echo "grafana $(grafana-server -v 2>/dev/null || dpkg-query -W -f='${Version}' grafana)"
echo
echo "Next: from your own machine"
echo "  ssh -N -L 3000:127.0.0.1:3000 ratel-ops"
echo "  open http://127.0.0.1:3000  (admin / admin, it will make you change it)"
