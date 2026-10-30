# Runbook: read-only checks that answer the call record questions (#26, N7)

Keep it short. These are checks, not changes. Nothing here edits Kamailio, MySQL or a table, and nothing
here prints a phone number, a row or a credential. **Names, counts and column definitions only.**

- **Last verified:** 2026-10-29, sections 1 and 2 (project lead, in the lab). Section 3 (counts during a call) still open
- **Owner:** the network lead; the project lead may run the read-only checks (agreed for the 2026-10-16 lab
  finding; confirm it still stands)
- **Runs on:** the RatelVoice VM as a user that may run `docker` (the IMS runs in containers: `pcscf`, `scscf`,
  `icscf`, `smsc`, `mysql`, `rtpengine`, `dns`, `pyhss`), and on core-up for the interface counters
- **Answers:** questions 1, 2, 3, 5, 6, 7 and 8 of [../call-record-agreement.md](../call-record-agreement.md);
  question 4 (`end_reason`) is the network lead's to decide; N7 in
  [../RATELCORE_INTEGRATION_FACTS.md](../RATELCORE_INTEGRATION_FACTS.md)

## What is known, and what is not

Found on 2026-10-29 (names and column definitions only):

- The Kamailio nodes are containers from one image. Their configuration is on the host under
  `~/docker_open5gs/<node>/kamailio_<node>.cfg`. The `opensips_ims_*` folders next to them set `acc` options, but
  no OpenSIPS container runs, so those lines do nothing.
- **No running Kamailio node loads `acc`.** The S-CSCF loads `ims_dialog`, `db_mysql` and `ims_charging`; the
  P-CSCF loads `ims_dialog` and `db_mysql`; the I-CSCF loads `db_mysql` only.
- **No `acc`, `missed_calls` or CDR table exists** in the `icscf`, `pcscf` or `scscf` schemas.
- `pcscf` and `scscf` each have `dialog_in`, `dialog_out` and `dialog_vars`; `scscf` also has `ro_session`.
  All read 0 rows outside a call. `dialog_in` has `start_time` (epoch seconds), `state` and the From URI and call
  id, and **no answer time, no end time and no end reason**. The From URI and call id are personal data.

- **`ims_dialog` has `db_mode` 0 on both the S-CSCF and the P-CSCF**, so dialog state is kept in memory and never
  written to MySQL. Those tables stay empty whatever calls are made; counting their rows (check 3) cannot show a
  finished call. Nothing keeps one, and the network team must pick a source: `acc` writing to MySQL (the likely
  one), the charging session, or another.
- **Time zone (question 5): UTC.** The VM is `Etc/UTC` and synchronised, MySQL's `@@system_time_zone` is `UTC`, and
  `NOW()` equals `UTC_TIMESTAMP()`. The agent still converts explicitly and tests it.
- `docker port mysql` prints nothing: MySQL is not published outside the VM.

Switching on `acc` (or anything else) is a **change to a core host** and is the network team's. This page only
looks.

## 1. Is `acc` loaded, without printing a password

The configurations are edited by hand and may hold a database URL with a password. Never print those lines.

```bash
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
# which nodes load which modules (names only)
grep -n 'loadmodule' ~/docker_open5gs/{scscf,icscf,pcscf}/*.cfg | sed 's/^\([^:]*\):[0-9]*:/\1: /' | grep -iE 'acc|dialog|ims_charging|db_mysql'
# does any file set an acc option, with the database URL hidden
grep -n 'modparam("acc"' ~/docker_open5gs/*/*.cfg | sed -E 's/"mysql:[^"]*"/"<hidden>"/'
```

Write down only: whether `acc.so` is listed for a running node, and which `acc` options are set (names, not values).

## 2. What the call-related tables look like (definitions, not rows)

The MySQL container's root account has no password in this stack, so no `-p` is needed. It is reachable only
through `docker exec`. Confirm it publishes no port: `docker port mysql` should print nothing.

```bash
docker exec mysql mysql -uroot -e "SELECT table_schema, table_name, table_rows
    FROM information_schema.tables
    WHERE table_schema IN ('icscf','pcscf','scscf')
       OR table_name IN ('acc','missed_calls','acc_cdrs','dialog_in','dialog_out','dialog_vars','ro_session')
    ORDER BY 1, 2;"
docker exec mysql mysql -uroot -e "SHOW CREATE TABLE scscf.dialog_in\G"      # repeat for dialog_out, ro_session
```

`SHOW CREATE TABLE` shows the columns and their types and no data. Keep that output: it answers question 1 and,
with the column types, question 5.

## 3. What they hold during a call and just after (counts only)

Skip this while `db_mode` is 0 (see above): the counts cannot move. Run it again after a node is changed to write to
MySQL, or to test a new `acc` table (use its name in the query).

Use two lab phones. This prints the time and six counts every two seconds, and nothing else. A count is not
personal data; a row is, so do not `SELECT *`. Start it in one terminal, make the calls in the table from the
phones, and stop it with Ctrl-C.

```bash
while true; do
  printf '%s ' "$(date +%T)"
  docker exec mysql mysql -uroot -N -e "
    SELECT 'p_in',COUNT(*) FROM pcscf.dialog_in UNION ALL SELECT 'p_out',COUNT(*) FROM pcscf.dialog_out
    UNION ALL SELECT 's_in',COUNT(*) FROM scscf.dialog_in UNION ALL SELECT 's_out',COUNT(*) FROM scscf.dialog_out
    UNION ALL SELECT 's_vars',COUNT(*) FROM scscf.dialog_vars UNION ALL SELECT 's_ro',COUNT(*) FROM scscf.ro_session;" 2>/dev/null | paste -sd' '
  sleep 2
done
```

| Case | What to do | What to write down |
| ---- | ---------- | ------------------ |
| Answered, ends normally | Call, answer, talk 20 seconds, hang up | The line before, during and 30 seconds after |
| Cancelled | Call, hang up before the other phone answers | Same |
| Busy | Call a phone that is already on a call | Same |
| Not answered | Call, let it ring out | Same |
| Not registered | Call a number whose phone is switched off | Same |

Two rows per call, or one, or none after it ends, answers questions 2 and 6. Note which table each case touches,
and for how long.

## 4. Time zone (question 5)

```bash
timedatectl | grep -E 'Time zone|synchronized'
docker exec mysql mysql -uroot -N -e "SELECT @@global.time_zone, @@system_time_zone, NOW(), UTC_TIMESTAMP();"
```

If `NOW()` and `UTC_TIMESTAMP()` differ, MySQL is not in UTC and the agent must convert (and test it).

## 5. Volume (question 8)

From check 3: rows added per call, times the calls per second the demo needs (a handful). The 60-second poll
is not a concern at that size.

## 6. The network's own byte counters (N7, demo act 6)

On core-up, read-only, no privilege needed. `deploy/core-up/ratel-interface-totals.sh` reads the kernel's byte
counters on `ogstun`, which the meter agent's counting table does not touch, so the two are independent.

```bash
./ratel-interface-totals.sh snapshot > /tmp/start.txt        # right after a 5-minute boundary (:00, :05, ...)
# ... one test phone browses for a few minutes ...
./ratel-interface-totals.sh snapshot > /tmp/end.txt          # right after another boundary
./ratel-interface-totals.sh delta /tmp/start.txt /tmp/end.txt   # prints the bytes that passed
```

Then on bss-app, wait for the agent's next post and compare (see "Reconciling with the network's counters" in
[ratel-meter.md](ratel-meter.md)). The interface counts every phone together: **run it with one test phone**, or
compare one SIM with `--imsi`.

## What to send back

Into the repository, through a pull request: the `SHOW CREATE TABLE` output of any call-related table, the
counts from check 3, the time-zone lines from check 4, and the network lead's answers to the agreement's
questions. No row, no number, no credential. The agreement is then corrected and `end_reason` is settled in
`contracts/openapi.yaml` in the same commit.
