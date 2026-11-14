#!/usr/bin/env bash
# RatelOps: install the Grafana dashboards that live in the repository.
#
# Dashboards are provisioned from files, not drawn by hand in the browser, for the same reason the
# Kamailio configuration is in Git: a dashboard that exists only in one person's Grafana is lost
# with the VM and cannot be reviewed.
#
# Run it from a directory holding the dashboard JSON files, or pass that directory:
#   sudo ./install-dashboards.sh [directory]
#
# The repository copies are in ops/grafana/dashboards/. They carry no addresses: host names come
# from the 'host' label in Prometheus's scrape config, which lives only on the ops VM.
#
# Safe to run again.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
	echo "run with sudo" >&2
	exit 1
fi

SRC=${1:-$(pwd)}
DEST=/var/lib/grafana/dashboards

shopt -s nullglob
FILES=("$SRC"/*.json)
[ ${#FILES[@]} -gt 0 ] || {
	echo "no .json dashboards in $SRC" >&2
	exit 1
}

for f in "${FILES[@]}"; do
	python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$f" || {
		echo "$f is not valid JSON" >&2
		exit 1
	}
done

install -d -o grafana -g grafana -m 0755 "$DEST"
for f in "${FILES[@]}"; do
	install -o grafana -g grafana -m 0644 "$f" "$DEST/"
	echo "installed $(basename "$f")"
done

install -d -m 0755 /etc/grafana/provisioning/dashboards
cat >/etc/grafana/provisioning/dashboards/10-ratel.yaml <<'YAML'
# RatelOps. Keep this in step with ops/grafana/dashboards/ in the ratel repository.
#
# allowUiUpdates is true on purpose while this is young: you can change a panel in the browser and
# it sticks. It is NOT the source of truth. Anything you want to keep must go back into the
# repository copy, or the next file change overwrites it.
apiVersion: 1
providers:
  - name: ratel
    orgId: 1
    folder: RatelOps
    type: file
    disableDeletion: false
    allowUiUpdates: true
    updateIntervalSeconds: 30
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: false
YAML

systemctl restart grafana-server.service

for _ in $(seq 1 30); do
	curl -4 -fsS -o /dev/null http://127.0.0.1:3000/api/health 2>/dev/null && break
	sleep 2
done

echo "--- grafana health ---"
curl -4 -sS http://127.0.0.1:3000/api/health
echo
echo "--- provisioning errors, if any ---"
journalctl -u grafana-server --since "-2 min" --no-pager | grep -iE "provision|dashboard" | tail -10 || true
echo
echo "Open the tunnel from your own machine, then look under Dashboards, folder RatelOps:"
echo "  ssh -N -L 3000:127.0.0.1:3000 ratel-ops"
