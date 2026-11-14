#!/usr/bin/env bash
# A rehearsal of the six acts for one person (or more): it reads you the next step, shows what you must see and the command to type,
# times every step, lets you mark a step repeated (r) or failed (f) with a key, and writes the filled-in sheet
# (docs/runbooks/rehearsal-sheet.md) to docs/records/. It changes nothing on any host: you type the commands yourself.
#
#   scripts/demo/rehearse.sh [--run N] [--people "name, name"] [--out FILE]
#
# At each step: Enter = done, r = I had to repeat it (type r, repeat the step, then Enter), f = it failed (a fallback was used;
# you are asked what), n = add a note, q = stop and save what there is. A step marked r or f means the run does not count towards the
# Week 8 gate; so does a run with fewer than three people, because the gate asks for someone else reading and timing.
#
# Settings: RATEL_REHEARSE_DIR (where the record goes, default docs/records in this repository)
set -euo pipefail

run=1
people="1 (alone)"
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    --run) [ $# -ge 2 ] || exit 2; run="$2"; shift 2 ;;
    --people) [ $# -ge 2 ] || exit 2; people="$2"; shift 2 ;;
    --out) [ $# -ge 2 ] || exit 2; out="$2"; shift 2 ;;
    *) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2 ;;
  esac
done

root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
today="$(date +%F)"
[ -n "$out" ] || out="${RATEL_REHEARSE_DIR:-$root/docs/records}/rehearsal-$today-run$run.md"
mkdir -p "$(dirname "$out")"
commit="$(git -C "$root" rev-parse --short HEAD 2>/dev/null || echo unknown)"

# A = an act (id, name, budget in seconds); S = a step (id, who, step, what you must see, budget in seconds, command to type)
steps() {
  cat <<'DATA'
A|1|Sell a SIM|150
S|1.1|Presenter|Sell SIM; pick the customer (KYC already approved)|the customer's card with a green KYC badge|25|
S|1.2|Presenter|Pick the SIM, the number and the plan|the plan's price and allowance|25|
S|1.3|Phones|The customer redeems a card on the RatelPay page for the line's number|"... added to your line"|30|
S|1.4|Presenter|Refresh balance, then Buy plan|the wallet drops by the plan's price|25|
S|1.5|Presenter|Activate line|the line is active|20|core-cp, to close #52 F: sudo journalctl -u ratel-link --since "-3min" --no-pager | grep -c line.activate   (must print 1)
S|1.6|Phones|Put the SIM in the phone; toggle airplane mode|the phone shows the network name|25|
A|2|Browse|60
S|2.1|Operator|Start the window (phone idle until it prints)|three lines: the interface and the counting table|15|core-up: ./ratel-window.sh start
S|2.2|Phones|Open a web page on line B's phone|the page loads|20|
S|2.3|Presenter|Line B's page, Usage tab|intervals with MB, newest first|25|
A|3|Call|90
S|3.1|Phones|Call line C's number from the other phone, national form (0 and ten digits)|it rings and the caller's number shows|20|
S|3.2|Phones|Answer, talk about 20 seconds|audio both ways|25|
S|3.3|Phones|Hang up|the call ends on both|10|
S|3.4|Presenter|Line C's page, Calls tab (about 70 seconds after the hang-up)|the call: start, rang for, talk time, Answered|35|
A|4|Run out of data|90
S|4.1|Presenter|Line D's page|state out of data; the history says allowance used up|15|
S|4.2|Operator|Start the rating job if the line was not out of data yet; read the journal|lines_out_of_data":1|20|bss-app: sudo systemctl start ratel-rating.service; sudo journalctl -u ratel-rating.service --since "-10min" --no-pager | grep '"rating.run"' | sed -E 's/.*"event":"rating.run",//'
S|4.3|Phones|Toggle airplane mode on line D's data phone; run a speed test|about 1 Mbit/s|30|
S|4.4|Phones|Call from a line that is also out of data|it still rings with audio|25|
A|5|Top up|90
S|5.1|Phones|RatelPay: line D's number, a card, the PIN|"... added" and the new balance|25|
S|5.2|Operator|Start the rating job; read the journal|lines_renewed":1,"lines_restored":1|20|bss-app: sudo systemctl start ratel-rating.service; sudo journalctl -u ratel-rating.service --since "-10min" --no-pager | grep '"rating.run"' | sed -E 's/.*"event":"rating.run",//'
S|5.3|Presenter|Line D's page|state active; the history says allowance restored|15|
S|5.4|Phones|Toggle airplane mode; run a speed test|tens of Mbit/s|30|
A|6|Prove the numbers|90
S|6.1|Operator|End the window (phone idle 10 seconds before), then the report|the table of three counts and the commands for bss-app|30|core-up: ./ratel-window.sh end   then   ./ratel-window.sh report
S|6.2|Operator|On bss-app paste the two commands the report printed|within 1%, exit 0|30|bss-app: the lines under "On bss-app" in the report
S|6.3|Operator|The calls query on the voice VM next to the Calls tab|the same start, rang for and talk time to the second|30|voice: the calls helper (docs/runbooks/demo-act-6.md)
DATA
}

exec 3<&0
total_steps="$(steps | grep -c '^S|')"
mmss() { printf '%d:%02d' $(($1 / 60)) $(($1 % 60)); }
ask() { local a=""; printf '%s' "$1" >&2; IFS= read -r -u 3 a || a="q"; printf '%s' "$a"; }

echo "Rehearsal $today, run $run, $people. Commit demoed: $commit."
echo "Before the stopwatch starts:"
t1="$(ask '  Was the day-before table of the checklist run today? [y/n] ')"
t2="$(ask '  Is a fresh voucher batch on sale? [y/n] ')"
pre="day-before table: ${t1:-?}; fresh voucher batch: ${t2:-?}"
echo

start="$(date +%s)"; rows=""; r_count=0; f_count=0; steps_done=0; quit=0
act_id=""; act_name=""; act_budget=0; act_start=$start; acts=""

close_act() {
  [ -n "$act_id" ] || return 0
  local spent=$(($(date +%s) - act_start))
  acts="${acts}| ${act_id} | ${act_name} | $(mmss "$act_budget") | $(mmss "$spent") |"$'\n'
}

while IFS='|' read -r kind a b c d e f; do
  [ "$quit" -eq 0 ] || break
  if [ "$kind" = "A" ]; then
    close_act
    act_id="$a"; act_name="$b"; act_budget="$c"; act_start="$(date +%s)"
    echo "=== Act $a: $b   (budget $(mmss "$c"))"
    rows="${rows}| **${a}** | | **${b}** | | **$(mmss "$c")** | | | |"$'\n'
    continue
  fi
  id="$a"; who="$b"; text="$c"; expect="$d"; budget="$e"; hint="$f"
  echo "--- $id  [$who]  $text"
  echo "    you must see: $expect   (budget $(mmss "$budget"))"
  [ -z "$hint" ] || echo "    type:         $hint"
  mark="✓"; notes=""
  while :; do
    ans="$(ask '    Enter = done, r = repeated, f = failed, n = note, q = stop > ')"
    case "$ans" in
      "") break ;;
      r) mark="R"; echo "    repeat it, then press Enter" ;;
      f) mark="F"; notes="${notes}$(ask '    what happened, and which fallback? ') "; break ;;
      n) notes="${notes}$(ask '    note: ') " ;;
      q) quit=1; mark="stopped"; break ;;
      *) echo "    (Enter, r, f, n or q)" ;;
    esac
  done
  elapsed=$(($(date +%s) - start))
  [ "$mark" != "R" ] || r_count=$((r_count + 1))
  [ "$mark" != "F" ] || f_count=$((f_count + 1))
  [ "$mark" = "stopped" ] || steps_done=$((steps_done + 1))
  rows="${rows}| ${id} | ${who} | ${text} | ${expect} | $(mmss "$budget") | $(mmss "$elapsed") | ${mark} | ${notes} |"$'\n'
  echo "    at $(mmss "$elapsed")"
done < <(steps)
close_act

total=$(($(date +%s) - start))
n_people="$(printf '%s' "$people" | tr ',' '\n' | grep -c '[A-Za-z0-9]' || true)"
case "$people" in "1 (alone)") n_people=1 ;; esac
counts="no"
[ "$quit" -eq 0 ] && [ "$r_count" -eq 0 ] && [ "$f_count" -eq 0 ] && [ "$n_people" -ge 3 ] && counts="yes"
reason=""
[ "$quit" -eq 0 ] || reason="$reason stopped early;"
[ "$r_count" -eq 0 ] || reason="$reason $r_count step(s) repeated;"
[ "$f_count" -eq 0 ] || reason="$reason $f_count step(s) failed;"
[ "$n_people" -ge 3 ] || reason="$reason fewer than three people;"

{
  echo "# Rehearsal $today, run $run (record)"
  echo
  echo "Filled in by \`scripts/demo/rehearse.sh\`; the sheet and the rules are in [rehearsal-sheet.md](../runbooks/rehearsal-sheet.md). Last four digits only."
  echo
  echo "| | |"
  echo "| --- | --- |"
  echo "| Date | $today |"
  echo "| Run number | $run |"
  echo "| People | $people |"
  echo "| Commit demoed | $commit |"
  echo "| Before the stopwatch | $pre |"
  echo "| Release on each host, lines (A to D) and phones | TODO: fill in by hand |"
  echo
  echo "| # | Who | Step | What you must see | Budget | Actual (from the start) | ✓ / R / F | Notes |"
  echo "| --- | --- | --- | --- | --- | --- | --- | --- |"
  printf '%s' "$rows"
  echo
  echo "| Act | Name | Budget | Spent |"
  echo "| --- | --- | --- | --- |"
  printf '%s' "$acts"
  echo
  echo "| | |"
  echo "| --- | --- |"
  echo "| Total time | $(mmss "$total") (budget 9:30, plus about 30 seconds between acts) |"
  echo "| Steps done | $steps_done of $total_steps |"
  echo "| Steps marked R | $r_count |"
  echo "| Steps marked F | $f_count |"
  reason="${reason# }"; reason="${reason%;}"
  echo "| Counts towards the Week 8 gate | $counts${reason:+ ($reason)} |"
  echo
  echo "## For each R and F: what, why, who fixes it by when"
  echo
  echo "TODO"
} >"$out"

echo
echo "Done in $(mmss "$total"): $steps_done steps, $r_count repeated, $f_count failed. Counts towards the gate: $counts."
echo "Record: $out"
