# Runbook: read-only checks that answer the call record questions (#26, N7)

Keep it short. These are checks, not changes. Nothing here edits Kamailio, MySQL or a table, and nothing
here prints a phone number, a row or a credential. **Names, counts and column definitions only.**

- **Last verified:** TODO (nobody has followed it yet)
- **Owner:** the network lead; the project lead may run the read-only checks (agreed for the 2026-10-16 lab
  finding; confirm it still stands)
- **Runs on:** the RatelVoice VM, as a user that may read MySQL by socket (`sudo mysql`), and on core-up for the
  interface counters
- **Answers:** questions 1, 2, 3, 5, 6, 7 and 8 of [../call-record-agreement.md](../call-record-agreement.md);
  question 4 (`end_reason`) is the network lead's to decide; N7 in
  [../RATELCORE_INTEGRATION_FACTS.md](../RATELCORE_INTEGRATION_FACTS.md)

## What is known, and what is not

On 2026-10-16 no finished-call record existed: the S-CSCF loads `ims_dialog` and `ims_charging` but not
`acc`, and no `acc`, `missed_calls` or CDR table was found. The dialog tables read 0 rows *outside a call*. What
nobody has seen is **what they hold during a call and just after it ends**. That is check 3 below, and it decides
whether call records can come from what is already running or `acc` has to be switched on.

Switching on `acc` (or anything else) is a **change to a core host** and is the network team's. This page only
looks.

## 1. Is `acc` loaded, without printing a password

The configurations are edited by hand and may hold a database URL with a password. Never print those lines.

```bash
# which file loads which modules (names only)
sudo grep -n 'loadmodule' /etc/kamailio*/kamailio*.cfg | sed 's/^\([^:]*\):[0-9]*:/\1: /'
# does any file set an acc option, with the database URL hidden
sudo grep -n 'modparam("acc"' /etc/kamailio*/*.cfg | sed -E 's/(db_url[^)]*)\)/db_url <hidden>)/; s/"mysql:[^"]*"/"<hidden>"/'
```

Write down only: whether `acc.so` is listed, and which `acc` options are set (names, not values).

## 2. What the call-related tables look like (definitions, not rows)

```bash
sudo mysql -e "SELECT table_schema, table_name, table_rows
               FROM information_schema.tables
               WHERE table_schema IN ('icscf','pcscf','scscf')
                  OR table_name IN ('acc','missed_calls','acc_cdrs','dialog_in','dialog_out','dialog_vars','ro_session')
               ORDER BY 1, 2;"
sudo mysql -e "SHOW CREATE TABLE scscf.dialog_in\G"      # repeat for dialog_out, ro_session, and any acc table
```

`SHOW CREATE TABLE` shows the columns and their types and no data. Keep that output: it answers question 1 and,
with the column types, question 5.

## 3. What they hold during a call and just after (counts only)

Use two lab phones. For each case below, count the rows in each candidate table **before, during and 30 seconds
after** the call. A count is not personal data; a row is, so do not `SELECT *`.

```bash
sudo mysql -N -e "SELECT 'dialog_in',  COUNT(*) FROM scscf.dialog_in
                  UNION ALL SELECT 'dialog_out', COUNT(*) FROM scscf.dialog_out
                  UNION ALL SELECT 'ro_session', COUNT(*) FROM scscf.ro_session;"
```

| Case | What to do | What to write down |
| ---- | ---------- | ------------------ |
| Answered, ends normally | Call, answer, talk 20 seconds, hang up | Counts before / during / after |
| Cancelled | Call, hang up before the other phone answers | Same |
| Busy | Call a phone that is already on a call | Same |
| Not answered | Call, let it ring out | Same |
| Not registered | Call a number whose phone is switched off | Same |

Two rows per call, or one, or none after it ends, answers questions 2 and 6. If every count is back to 0 after
the call, **nothing keeps a finished call** on the current configuration, and the network team must pick a
source (`acc` writing to MySQL in UTC, the charging session, or another) before call mode can be built.

## 4. Time zone (question 5)

```bash
timedatectl | grep -E 'Time zone|synchronized'
sudo mysql -N -e "SELECT @@global.time_zone, @@system_time_zone, NOW(), UTC_TIMESTAMP();"
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
