#!/usr/bin/env bash
# Put the patched HSS into service on core-cp, or take it out again.
#
# Installs the complete build to /opt/open5gs-hss-ratel (its own libraries) and adds the systemd
# drop-in zz-ratel-hss.conf, which overrides the start line and the library path of the existing
# drop-in fix4633.conf. Nothing else is touched: the packaged HSS, /opt/open5gs-hss and
# fix4633.conf stay as they are. Rolling back removes zz-ratel-hss.conf, which puts the
# fix4633 build back in service.
#
# Usage (on core-cp, from the folder holding open5gs-hss-ratel.tgz and its .sha256):
#   sudo ./deploy-hssd.sh             show what would change, change nothing
#   sudo ./deploy-hssd.sh --apply     install, restart open5gs-hssd, check it
#   sudo ./deploy-hssd.sh --rollback  back to the fix4633 build, restart, check it
#
# Restarting the HSS takes seconds. Existing calls and data sessions continue. New attaches and IMS
# registrations wait until the MME, I-CSCF and S-CSCF have reconnected (checked below).
set -euo pipefail

MODE=${1:-}
HERE=$(cd "$(dirname "$0")" && pwd)
TGZ=$HERE/open5gs-hss-ratel.tgz
PREFIX=/opt/open5gs-hss-ratel
LIBDIR=$PREFIX/lib/x86_64-linux-gnu
BIN=$PREFIX/bin/open5gs-hssd
DROPIN_DIR=/etc/systemd/system/open5gs-hssd.service.d
DROPIN=$DROPIN_DIR/zz-ratel-hss.conf

[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }

check() {
	echo "== open5gs-hssd"
	systemctl is-active open5gs-hssd
	systemctl show open5gs-hssd -p ActiveEnterTimestamp
	PID=$(systemctl show open5gs-hssd -p MainPID --value)
	echo "running binary: $(readlink -f /proc/"$PID"/exe)"
	echo "its libogscore: $(grep -m1 -o '/[^ ]*libogscore[^ ]*' /proc/"$PID"/maps || echo unknown)"
	echo "== Diameter peers back (up to 60 s): I-CSCF .19:3869 and S-CSCF .20:3870"
	I=0
	S=0
	for i in $(seq 1 12); do
		I=$(ss -tan | grep -c "ESTAB.*172.22.0.19:3869" || true)
		S=$(ss -tan | grep -c "ESTAB.*172.22.0.20:3870" || true)
		[ "$I" -ge 1 ] && [ "$S" -ge 1 ] && { echo "both connected after $((i * 5)) s"; break; }
		sleep 5
	done
	[ "$I" -ge 1 ] && [ "$S" -ge 1 ] || echo "WARNING: I-CSCF $I, S-CSCF $S connections. Check before going on."
	echo "== MME to HSS (S6a, SCTP), latest connect line"
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
	echo "Rolled back to the fix4633 build. $PREFIX is left in place."
	exit 0
	;;
--apply | "") ;;
*)
	echo "usage: $0 [--apply|--rollback]" >&2
	exit 1
	;;
esac

echo "== current start configuration"
systemctl cat open5gs-hssd | grep -E "^# /|^ExecStart=|^Environment=" || true

echo "== checks on the new build"
[ -f "$TGZ" ] && [ -f "$TGZ.sha256" ] || { echo "need $TGZ and $TGZ.sha256 here" >&2; exit 1; }
(cd "$HERE" && sha256sum -c "$(basename "$TGZ").sha256")
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
tar -C "$STAGE" -xzf "$TGZ"
SBIN=$STAGE$BIN
[ -x "$SBIN" ] || { echo "the archive has no $BIN" >&2; exit 1; }
file "$SBIN" | grep -q "x86-64" || { echo "not an x86-64 binary" >&2; exit 1; }
MISSING=$(LD_LIBRARY_PATH=$STAGE$LIBDIR ldd "$SBIN" | grep "not found" || true)
[ -z "$MISSING" ] || { echo "missing system libraries:" >&2; echo "$MISSING" >&2; exit 1; }
echo "libraries resolve (system libraries present, Open5GS ones from the build)"
strings "$SBIN" | grep -q "Cx: move Public-Identity" && echo "our patch: present"
echo "tel identity format: $(strings "$SBIN" | grep -m1 '^tel:')  (running build: $(strings /opt/open5gs-hss/bin/open5gs-hssd 2>/dev/null | grep -m1 '^tel:' || echo n/a))"

EXEC=$(systemctl show open5gs-hssd -p ExecStart --value | sed -n 's/.*argv\[\]=\([^;]*\);.*/\1/p' | head -1)
ARGS=$(echo "$EXEC" | cut -d" " -f2- | sed 's/ *$//')
[ -n "$ARGS" ] || { echo "could not read the HSS start arguments from systemd" >&2; exit 1; }
echo "freeDiameter extensions the HSS loads:"
CONF=$(sed -n 's/^[[:space:]]*freeDiameter:[[:space:]]*//p' /etc/open5gs/hss.yaml | head -1)
[ -n "$CONF" ] && grep -E "^[[:space:]]*LoadExtension" "$CONF" | sed 's/^/  /' || echo "  (could not read them)"
echo "current start line: $EXEC"
echo "new start line:     $BIN $ARGS   with LD_LIBRARY_PATH=$LIBDIR"

if [ "$MODE" != --apply ]; then
	echo
	echo "Nothing changed. Run again with --apply to install and restart."
	exit 0
fi

if [ -d "$PREFIX" ]; then
	mv "$PREFIX" "$PREFIX.previous-$(date +%Y%m%d%H%M%S)"
fi
tar -C / -xzf "$TGZ"
mkdir -p "$DROPIN_DIR"
cat >"$DROPIN" <<EOF
# RatelPlus: patched HSS, see deploy/core-cp/hss/README.md in the ratel repository.
# Overrides fix4633.conf. Remove this file (or run deploy-hssd.sh --rollback) to go back to it.
[Service]
Environment=LD_LIBRARY_PATH=$LIBDIR
ExecStart=
ExecStart=$BIN $ARGS
EOF
systemctl daemon-reload
systemctl restart open5gs-hssd
sleep 5
check
echo
echo "Deployed. Now toggle airplane mode on every phone so each re-registers through the patched HSS."
