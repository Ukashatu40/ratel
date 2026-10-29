#!/usr/bin/env bash
# Read-only: the kernel's own byte counters on the internet interface (ogstun), so a window of
# usage can be checked against something the meter agent did not count (M-28, DEMO_SCRIPT act 6).
#
#   ratel-interface-totals.sh snapshot            prints "<epoch seconds> <rx bytes> <tx bytes>"
#   ratel-interface-totals.sh delta START END     prints the bytes that passed between two snapshots
#                                                 (files that each hold one snapshot line)
#
# It changes nothing and needs no privilege: it reads /sys/class/net. The interface can be named
# with IFACE (default ogstun). The counters are the interface's, for all phones together; they say
# how many bytes passed, not whose they were. Run the check with one test phone, or compare a
# single SIM with the agent's records using the reconcile command (docs/runbooks/ratel-meter.md).
set -euo pipefail

iface="${IFACE:-ogstun}"
stats="/sys/class/net/${iface}/statistics"

die() {
  echo "ratel-interface-totals: $*" >&2
  exit 2
}

snapshot() {
  [[ -r "${stats}/rx_bytes" && -r "${stats}/tx_bytes" ]] || die "no counters for ${iface}"
  printf '%s %s %s\n' "$(date -u +%s)" "$(<"${stats}/rx_bytes")" "$(<"${stats}/tx_bytes")"
}

delta() {
  local start_file="${1:-}" end_file="${2:-}"
  [[ -r "${start_file}" && -r "${end_file}" ]] || die "usage: delta START_FILE END_FILE"
  local t0 rx0 tx0 t1 rx1 tx1
  read -r t0 rx0 tx0 <"${start_file}"
  read -r t1 rx1 tx1 <"${end_file}"
  for n in "${t0}" "${rx0}" "${tx0}" "${t1}" "${rx1}" "${tx1}"; do
    [[ "${n}" =~ ^[0-9]+$ ]] || die "a snapshot line is not three whole numbers"
  done
  ((t1 > t0)) || die "the second snapshot is not later than the first"
  ((rx1 >= rx0 && tx1 >= tx0)) || die "a counter went backwards (the interface was reset?)"
  echo "window from ${t0} to ${t1}" >&2
  echo "$(((rx1 - rx0) + (tx1 - tx0)))"
}

case "${1:-}" in
  snapshot) snapshot ;;
  delta) shift && delta "$@" ;;
  *) die "usage: snapshot | delta START_FILE END_FILE" ;;
esac
