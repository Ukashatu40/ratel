#!/usr/bin/env bash
# Installs ratel-welcome-sms.timer: welcome_sms.py every minute, as the user running this script
# (it must be able to run `docker exec`). Run on the voice VM from this folder, with sudo access.
#   ./install-welcome-timer.sh          install (or update) and start
#   ./install-welcome-timer.sh --stop   stop and remove the timer
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="$(id -un)"
UNIT=/etc/systemd/system/ratel-welcome-sms

if [ "${1:-}" = "--stop" ]; then
	sudo systemctl disable --now ratel-welcome-sms.timer 2>/dev/null || true
	sudo rm -f "$UNIT.service" "$UNIT.timer"
	sudo systemctl daemon-reload
	echo "welcome SMS timer removed"
	exit 0
fi

docker exec scscf true >/dev/null || { echo "cannot reach the scscf container as $USER_NAME" >&2; exit 1; }
# --send-sms with a wrong number answers 2 and sends nothing; an older service would start instead.
rc=0; timeout 10 docker exec ussd python -I /app/ussd_as.py --send-sms x </dev/null >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 2 ] || { echo "the ussd container does not have --send-sms yet: run ./run-ussd.sh first" >&2; exit 1; }
grep -q '^RATEL_PAY_URL=' "$HERE/ussd.env" || { echo "RATEL_PAY_URL missing in ussd.env" >&2; exit 1; }

sudo tee "$UNIT.service" >/dev/null <<UNITEOF
[Unit]
Description=Ratelplus: send the welcome SMS of newly activated lines once they register
After=docker.service

[Service]
Type=oneshot
User=$USER_NAME
ExecStart=/usr/bin/python3 -I $HERE/welcome_sms.py
NoNewPrivileges=yes
UNITEOF

sudo tee "$UNIT.timer" >/dev/null <<UNITEOF
[Unit]
Description=Ratelplus: welcome SMS sender, every minute

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
AccuracySec=5s

[Install]
WantedBy=timers.target
UNITEOF

sudo systemctl daemon-reload
sudo systemctl enable --now ratel-welcome-sms.timer
systemctl list-timers ratel-welcome-sms.timer --no-pager | sed -n 1,2p
echo "logs: journalctl -u ratel-welcome-sms.service"
