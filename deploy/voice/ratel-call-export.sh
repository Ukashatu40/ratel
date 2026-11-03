#!/usr/bin/env bash
# Prints the S-CSCF's new call rows for RatelMeter's call agent. Install as /usr/local/sbin/ratel-call-export
# (root-owned, mode 0755). The agent runs it as root through ONE sudo rule (sudoers-ratel-meter.example).
#
#   ratel-call-export --after-acc N --after-missed N --settle S
#
# Prints tab-separated rows, oldest first, at most 5,000 from each table:
#   table  id  method  sip_code  callid  from_tag  from_user  to_user  time_epoch_utc  start_ts
# `acc` rows are answered INVITEs and BYEs; `missed` rows are INVITEs that failed (docs/call-record-agreement.md).
# Only rows at least S seconds old are printed, so the rows of one call arrive together.
#
# The arguments are three whole numbers and nothing else: nothing the agent says can reach the SQL as anything
# but a number. The database is the voice VM's MySQL container, reached with `docker exec` (root, no password,
# nothing published outside the VM). The rows are personal data: this script prints them to the agent only.
set -euo pipefail
umask 077

usage() { echo "usage: ratel-call-export --after-acc N --after-missed N --settle S" >&2; exit 2; }
[ "$#" -eq 6 ] || usage
[ "$1" = "--after-acc" ] && [ "$3" = "--after-missed" ] && [ "$5" = "--settle" ] || usage
for value in "$2" "$4" "$6"; do
  [[ "$value" =~ ^[0-9]{1,12}$ ]] || usage
done
acc="$2"; missed="$4"; settle="$6"

columns="id, method, sip_code, callid, from_tag, from_user, to_user, UNIX_TIMESTAMP(time), start_ts"
exec docker exec mysql mysql -uroot -N -B scscf -e "
SELECT 'acc', $columns FROM acc
  WHERE id > $acc AND time <= NOW() - INTERVAL $settle SECOND ORDER BY id LIMIT 5000;
SELECT 'missed', $columns FROM missed_calls
  WHERE id > $missed AND time <= NOW() - INTERVAL $settle SECOND ORDER BY id LIMIT 5000;"
