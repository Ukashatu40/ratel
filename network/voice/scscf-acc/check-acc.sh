#!/usr/bin/env bash
# Read-only check of the S-CSCF call-record setup on the voice VM. Prints names, counts and yes/no: never a row, a
# number, a Call-ID or the database URL.
#
#   bash check-acc.sh [path-to-kamailio_scscf.cfg]      (default: ~/docker_open5gs/scscf/kamailio_scscf.cfg)
set -u
cfg="${1:-$HOME/docker_open5gs/scscf/kamailio_scscf.cfg}"
ok=0
check() { if "$@" >/dev/null 2>&1; then echo "ok      $label"; else echo "MISSING $label"; ok=1; fi; }

label='flag FLT_ACC defined'              ; check grep -q '^#!define FLT_ACC 4' "$cfg"
label='flag FLT_ACCMISSED defined'        ; check grep -q '^#!define FLT_ACCMISSED 8' "$cfg"
label='acc.so loaded'                     ; check grep -q '^loadmodule "acc.so"' "$cfg"
label='acc db_flag and db_missed_flag'    ; check grep -q 'modparam("acc", "db_missed_flag", FLT_ACCMISSED)' "$cfg"
label='db_extra has start_ts'             ; check grep -q 'db_extra", "from_user=$fU;to_user=$tU;start_ts=$avp(acc_start)"' "$cfg"
label='start time is stored in the route' ; check grep -q '\$avp(acc_start) = \$TS;' "$cfg"

for table in acc missed_calls; do
  for column in from_user to_user start_ts; do
    label="column $table.$column"
    check docker exec mysql mysql -uroot -N scscf -e "SELECT $column FROM $table LIMIT 0"
  done
done
label='scscf container is up'; check bash -c "docker ps --format '{{.Names}} {{.Status}}' | grep -q '^scscf Up'"
echo
docker exec mysql mysql -uroot -N scscf -e "SELECT 'acc rows', COUNT(*) FROM acc UNION ALL SELECT 'missed_calls rows', COUNT(*) FROM missed_calls" 2>/dev/null
exit "$ok"
