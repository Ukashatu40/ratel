#!/usr/bin/env bash
# Put the patched HSS into service on core-cp, or take it out again.
#
# The packaged binary is never touched. The patched one goes to /usr/local/sbin, and a systemd
# drop-in points open5gs-hssd at it with the same arguments the package uses. Rolling back removes
# the drop-in. A package upgrade of open5gs-hss does not remove the drop-in, so check this file's
# README before upgrading.
#
# Usage (on core-cp, from the folder holding open5gs-hssd-ratel and its .sha256):
#   sudo ./deploy-hssd.sh             show what would change, change nothing
#   sudo ./deploy-hssd.sh --apply     install, restart open5gs-hssd, check it
#   sudo ./deploy-hssd.sh --rollback  back to the packaged binary, restart, check it
#
# Restarting the HSS takes seconds. Existing calls and data sessions continue. New attaches and IMS
# registrations wait until the MME, I-CSCF and S-CSCF have reconnected (checked below).
set -euo pipefail

MODE=${1:-}
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$HERE/open5gs-hssd-ratel
DEST=/usr/local/sbin/open5gs-hssd-ratel
DROPIN_DIR=/etc/systemd/system/open5gs-hssd.service.d
DROPIN=$DROPIN_DIR/ratel-patched.conf

[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }

check() {
	echo "== open5gs-hssd"
	systemctl is-active open5gs-hssd
	systemctl show open5gs-hssd -p ActiveEnterTimestamp
	echo "running binary: $(readlink -f /proc/"$(systemctl show open5gs-hssd -p MainPID --value)"/exe)"
	echo "== Diameter peers back (up to 60 s): I-CSCF .19:3869 and S-CSCF .20:3870"
	for i in $(seq 1 12); do
		I=$(ss -tan | grep -c "ESTAB.*172.22.0.19:3869" || true)
		S=$(ss -tan | grep -c "ESTAB.*172.22.0.20:3870" || true)
		[ "$I" -ge 1 ] && [ "$S" -ge 1 ] && { echo "both connected after $((i * 5)) s"; break; }
		sleep 5
	done
	[ "${I:-0}" -ge 1 ] && [ "${S:-0}" -ge 1 ] || echo "WARNING: I-CSCF $I, S-CSCF $S connections. Check before going on."
	echo "== MME to HSS (S6a, SCTP) since the restart"
	START=$(systemctl show open5gs-hssd -p ActiveEnterTimestamp --value)
	journalctl -u open5gs-mmed --since "$START" --no-pager 2>/dev/null | grep -c "CONNECTED TO 'hss" || true
	grep "CONNECTED TO 'hss" /var/log/open5gs/mme.log | tail -1 | cut -c1-90
}

case "$MODE" in
--rollback)
	[ -f "$DROPIN" ] || { echo "not deployed: $DROPIN does not exist"; exit 0; }
	rm -f "$DROPIN"
	systemctl daemon-reload
	systemctl restart open5gs-hssd
	sleep 5
	check
	echo "rolled back to the packaged HSS. $DEST is left in place, remove it if no longer wanted."
	exit 0
	;;
--apply | "") ;;
*)
	echo "usage: $0 [--apply|--rollback]" >&2
	exit 1
	;;
esac

echo "== checks on the new binary"
[ -f "$SRC" ] && [ -f "$SRC.sha256" ] || { echo "need $SRC and $SRC.sha256 here" >&2; exit 1; }
(cd "$HERE" && sed "s#  .*/#  #" "$SRC.sha256" | sha256sum -c -)
file "$SRC" | grep -q "x86-64" || { echo "not an x86-64 binary" >&2; exit 1; }
if ldd "$SRC" | grep -q "not found"; then
	echo "missing libraries:" >&2
	ldd "$SRC" | grep "not found" >&2
	exit 1
fi
echo "libraries resolve: $(ldd "$SRC" | grep -c libogs) Open5GS libraries, all found"

# Keep exactly the arguments the package starts the HSS with.
EXEC=$(systemctl show open5gs-hssd -p ExecStart --value | sed -n 's/.*argv\[\]=\([^;]*\);.*/\1/p' | head -1)
ARGS=$(echo "$EXEC" | cut -d" " -f2- | sed 's/ *$//')
[ -n "$ARGS" ] || { echo "could not read the HSS start arguments from systemd" >&2; exit 1; }
echo "packaged start line: $EXEC"
echo "new start line:      $DEST $ARGS"

if [ "$MODE" != --apply ]; then
	echo
	echo "Nothing changed. Run again with --apply to install and restart."
	exit 0
fi

install -m 0755 -o root -g root "$SRC" "$DEST"
mkdir -p "$DROPIN_DIR"
cat >"$DROPIN" <<EOF
# RatelPlus: patched HSS, see deploy/core-cp/hss/README.md in the ratel repository.
# Remove this file (or run deploy-hssd.sh --rollback) to go back to the packaged binary.
[Service]
ExecStart=
ExecStart=$DEST $ARGS
EOF
systemctl daemon-reload
systemctl restart open5gs-hssd
sleep 5
check
echo
echo "Deployed. Now toggle airplane mode on every phone so each re-registers through the patched HSS."
