#!/usr/bin/env bash
# Three counts of one window on core-up, taken together, so a comparison cannot mix them up (M-28, DEMO_SCRIPT act 6):
# the interface's own byte counters, the counting table the agent reads, and what the agent reported as unmapped.
# Read-only: it changes nothing. It needs sudo for the counting table and the journal, and asks for the password once, first.
#
#   ratel-window.sh start    wait for 1 to 3 seconds past a 5-minute mark, then record the counters
#   ratel-window.sh end      the same, later (at least 5 minutes after start)
#   ratel-window.sh report   the three counts, and the exact commands to run on bss-app
#
# Keep the phone idle (or streaming steadily) for the 10 seconds around start and end: traffic at only one edge shows as an error.
# Wait about 2 minutes after `end` before running the commands that `report` prints for bss-app: the agent posts the last interval
# at the boundary.
#
# Settings (environment; the defaults are right on core-up):
#   IFACE (ogstun)  RATEL_WINDOW_DIR (/tmp/ratel-window)  RATEL_WINDOW_SUDO (sudo; empty for none)
#   RATEL_WINDOW_NFT (nft)  RATEL_WINDOW_JOURNALCTL (journalctl)  RATEL_WINDOW_NOWAIT=1 (do not wait for the 5-minute mark)
set -euo pipefail

iface="${IFACE:-ogstun}"
dir="${RATEL_WINDOW_DIR:-/tmp/ratel-window}"
nft_cmd="${RATEL_WINDOW_NFT:-nft}"
journal_cmd="${RATEL_WINDOW_JOURNALCTL:-journalctl}"
stats="${RATEL_WINDOW_STATS:-/sys/class/net/${iface}/statistics}"
read -r -a sudo_cmd <<<"${RATEL_WINDOW_SUDO-sudo}"

die() { echo "ratel-window: $*" >&2; exit 2; }
as_root() { ${sudo_cmd[@]+"${sudo_cmd[@]}"} "$@"; }
clock() { date -u -d "@$1" +%H:%M:%S 2>/dev/null || date -u -r "$1" +%H:%M:%S; }

set_total() {  # the sum of the bytes of every address in one counting set
  as_root "$nft_cmd" list set inet ratel_meter "$1" | tr ',' '\n' | grep -o 'bytes [0-9]*' | awk '{t += $2} END {print t + 0}'
}

snapshot() {  # snapshot <file>
  [ -r "$stats/rx_bytes" ] && [ -r "$stats/tx_bytes" ] || die "no counters for ${iface}"
  [ -n "${sudo_cmd[*]-}" ] && as_root -v  # the password is asked here, before the wait, never during it
  if [ "${RATEL_WINDOW_NOWAIT:-0}" != 1 ]; then
    while :; do s=$(($(date +%s) % 300)); [ "$s" -ge 1 ] && [ "$s" -le 3 ] && break; sleep 1; done
  fi
  local now rx tx up down
  now="$(date +%s)"; rx="$(<"$stats/rx_bytes")"; tx="$(<"$stats/tx_bytes")"
  up="$(set_total up)"; down="$(set_total down)"
  mkdir -p "$dir"; chmod 700 "$dir"
  printf '%s %s %s %s %s\n' "$now" "$rx" "$tx" "$up" "$down" >"$1"
  echo "$(basename "$1") at $(clock "$now") UTC: interface $((rx + tx)) bytes, counting table $((up + down)) bytes"
}

pct() { awk -v a="$1" -v b="$2" 'BEGIN { if (b == 0) print "n/a"; else printf "%.2f%%", (a - b) * 100 / b }'; }

report() {
  [ -r "$dir/start" ] && [ -r "$dir/end" ] || die "take both with: start, then end"
  local t0 rx0 tx0 up0 down0 t1 rx1 tx1 up1 down1
  read -r t0 rx0 tx0 up0 down0 <"$dir/start"
  read -r t1 rx1 tx1 up1 down1 <"$dir/end"
  [ "$t1" -gt "$t0" ] || die "end is not later than start"
  [ "$rx1" -ge "$rx0" ] && [ "$tx1" -ge "$tx0" ] && [ "$up1" -ge "$up0" ] && [ "$down1" -ge "$down0" ] \
    || die "a counter went backwards (a restart?): take a new window"
  local from to if_up if_down nf_up nf_down un_up un_down n
  from=$((t0 / 300 * 300)); to=$((t1 / 300 * 300))
  if_up=$((rx1 - rx0)); if_down=$((tx1 - tx0)); n=$((if_up + if_down))
  nf_up=$((up1 - up0)); nf_down=$((down1 - down0))
  read -r un_up un_down < <(as_root "$journal_cmd" -u ratel-meter.service --since "@$((from + 1))" --until "@$((to + 90))" --no-pager 2>/dev/null |
    grep unmapped_usage | sed -E 's/.*"bytes_up":([0-9]+),"bytes_down":([0-9]+).*/\1 \2/' | awk '{u += $1; d += $2} END {print u + 0, d + 0}')
  echo
  echo "window        $(clock "$t0") to $(clock "$t1") UTC ($((t1 - t0)) s); whole intervals $(clock "$from") to $(clock "$to") ($((to - from)) s)"
  echo
  printf '%-22s %14s %14s %14s\n' "" "up" "down" "total"
  printf '%-22s %14s %14s %14s\n' "interface (ogstun)" "$if_up" "$if_down" "$n"
  printf '%-22s %14s %14s %14s\n' "counting table" "$nf_up" "$nf_down" "$((nf_up + nf_down))"
  printf '%-22s %14s %14s %14s\n' "agent: unmapped" "$un_up" "$un_down" "$((un_up + un_down))"
  printf '%-22s %14s %14s %14s\n' "table less unmapped" "$((nf_up - un_up))" "$((nf_down - un_down))" "$((nf_up + nf_down - un_up - un_down))"
  echo
  echo "the table against the interface:      $(pct $((nf_up + nf_down)) "$n")   (the counting rule)"
  echo "what the agent should have stored:    $((nf_up + nf_down - un_up - un_down)) bytes   (the table less the unmapped addresses)"
  echo
  echo "On bss-app, after the agent's next post (the stored total is what to compare with the line above):"
  echo "  T0=$t0; T1=$t1; N=$n"
  echo "  bss app.meter_api.reconcile_cli --from \$((T0 / 300 * 300)) --to \$((T1 / 300 * 300)) --network-total \$N; echo \"exit \$?\""
  echo "  sudo -u postgres psql -Atd ratel_bss -c \"select coalesce(sum(bytes_up + bytes_down), 0) from usage_record where period_start >= to_timestamp($from) and period_start < to_timestamp($to)\""
}

case "${1:-}" in
  start) snapshot "$dir/start" ;;
  end) snapshot "$dir/end" ;;
  report) report ;;
  *) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2 ;;
esac
