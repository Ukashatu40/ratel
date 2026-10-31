# Runbook: read-only checks that answer the call record questions (#26, N7)

Keep it short. These are checks, not changes. Nothing here edits Kamailio, MySQL or a table, and nothing
here prints a phone number, a row or a credential. **Names, counts and column definitions only.**

- **Last verified:** 2026-10-30 (project lead, in the lab): sections 1, 2 and 4, and every call case in section 3. Still open: the number format, a call with no BYE, and the end_reason values
- **Owner:** the network lead; the project lead may run the read-only checks (agreed for the 2026-10-16 lab
  finding; confirm it still stands)
- **Runs on:** the RatelVoice VM as a user that may run `docker` (the IMS runs in containers: `pcscf`, `scscf`,
  `icscf`, `smsc`, `mysql`, `rtpengine`, `dns`, `pyhss`), and on core-up for the interface counters
- **Answers:** questions 1, 2, 3, 5, 6, 7 and 8 of [../call-record-agreement.md](../call-record-agreement.md);
  question 4 (`end_reason`) is the network lead's to decide; N7 in
  [../RATELCORE_INTEGRATION_FACTS.md](../RATELCORE_INTEGRATION_FACTS.md)

## What is known, and what is not

Found on 2026-10-29, before `acc` was switched on (names and column definitions only; from 2026-10-30 the S-CSCF
loads `acc`, see check 3):

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

## 3. Call records in `acc` (switched on 2026-10-30)

The dialog tables stay empty (see above), so the S-CSCF now writes call records with the `acc` module, in the `scscf`
schema. **This is a change to a core host, made by hand on the voice VM, and it is not in Git.** To redo it:

1. Create the tables from the container's own script, then add the two columns the agent needs:
   ```bash
   docker exec scscf cat /usr/local/share/kamailio/mysql/acc-create.sql | docker exec -i mysql mysql -uroot scscf
   docker exec mysql mysql -uroot scscf -e "
   ALTER TABLE acc          ADD COLUMN from_user VARCHAR(64) NOT NULL DEFAULT '', ADD COLUMN to_user VARCHAR(64) NOT NULL DEFAULT '';
   ALTER TABLE missed_calls ADD COLUMN from_user VARCHAR(64) NOT NULL DEFAULT '', ADD COLUMN to_user VARCHAR(64) NOT NULL DEFAULT '';"
   ```
2. In `~/docker_open5gs/scscf/kamailio_scscf.cfg` (keep a `.before-acc` copy), add four things, then `docker restart scscf`
   (a restart drops registrations):
   - `#!define FLT_ACC 4` and `#!define FLT_ACCMISSED 8`, after `#!define FLT_DIALOG 2`;
   - `loadmodule "acc.so"`, after `loadmodule "ims_dialog.so"`;
   - after the `ims_dialog` `db_mode` block, inside `#!ifdef DB_URL`:
     `modparam("acc", "db_url", DB_URL)`, `modparam("acc", "db_flag", FLT_ACC)`,
     `modparam("acc", "db_missed_flag", FLT_ACCMISSED)`, `modparam("acc", "db_extra", "from_user=$fU;to_user=$tU")`;
   - in the main `route`, right after `setflag(FLT_DIALOG);`:
     `if (is_method("INVITE|BYE")) { setflag(FLT_ACC); setflag(FLT_ACCMISSED); }`.

What it writes: an answered INVITE and a BYE go to `acc` (`time` is when the final reply passed the S-CSCF); a failed
INVITE goes to `missed_calls` with the SIP code. **Each event is written twice** for a call between two of our own
phones, once for the calling leg and once for the receiving leg, so a reader groups by `callid`.

What the lab showed on 2026-10-30, between two of our own phones:

- Both legs of a call **share one Call-ID**, so one call is one `callid` with two rows per event.
- **The two numbers are written differently.** `from_user` was `234` and ten digits (13 characters); `to_user` was the
  number as dialled, `0` and ten digits (11 characters). TODO(network lead): confirm the format the contract wants.
  The agent has to turn `0XXXXXXXXXX` into `234XXXXXXXXXX` before it compares with a line's number.
- **A hang-up can leave BYE rows in both directions.** One call where the callee hung up gave four BYE rows in the
  same second: two with the callee's tag, two with the caller's. Earlier calls gave two BYE rows each, all one way.
  Until this is explained, take the lowest `id` BYE of a `callid` as the one who hung up. TODO: repeat the case where
  the caller hangs up and see whether its BYE rows are mixed too.
- **A failed call gives two `missed_calls` rows that can carry different codes** (a phone in airplane mode gave 408 and
  500 in the same second). Map the pair, not each row.
- **One answered call (INVITE 200, 2026-10-30 13:25 UTC) has no BYE at all**, not in `acc` and not in `missed_calls`.
  Unexplained: either it was never hung up or the BYE was not recorded.
- `acc` holds the time the final reply passed the S-CSCF, never when the call started. How long a call rang cannot be
  read from the rows.

The rows hold phone numbers (`from_user`, `to_user`), the Call-ID and the tags: personal data. **Never `SELECT *`,
never paste a row.** These queries show counts, times and codes only:

```bash
docker exec mysql mysql -uroot scscf -e "SELECT 'acc' t, method, sip_code, COUNT(*) n FROM acc GROUP BY method, sip_code UNION ALL SELECT 'missed', method, sip_code, COUNT(*) FROM missed_calls GROUP BY method, sip_code;"
docker exec mysql mysql -uroot scscf -e "SELECT 'acc' t, id, method, sip_code, sip_reason, time FROM acc ORDER BY id DESC LIMIT 8; SELECT 'missed' t, id, method, sip_code, sip_reason, time FROM missed_calls ORDER BY id DESC LIMIT 8;"
# rows and distinct calls; are the numbers filled in (lengths only); did the caller or the callee hang up (true/false only)
docker exec mysql mysql -uroot scscf -e "SELECT COUNT(*) AS row_count, COUNT(DISTINCT callid) AS calls FROM acc; SELECT id, method, CHAR_LENGTH(from_user) AS from_len, CHAR_LENGTH(to_user) AS to_len FROM acc ORDER BY id DESC LIMIT 8;"
docker exec mysql mysql -uroot scscf -e "SELECT b.id, (b.from_tag = i.from_tag) AS caller_hung_up FROM acc b JOIN acc i ON i.callid = b.callid AND i.method = 'INVITE' WHERE b.method = 'BYE' ORDER BY b.id DESC LIMIT 8;"
```

The cases tried, from phone A to phone B (note the time, wait ten seconds between calls). Every case has now been seen:

| Case | What to do | Rows seen on 2026-10-30 |
| ---- | ---------- | ----------------------- |
| Answered, caller hangs up | Talk 20 s, A hangs up | `acc` INVITE 200, then BYE 200 with `caller_hung_up` = 1 |
| Answered, callee hangs up | Talk 20 s, B hangs up | `acc` INVITE 200, then BYE 200 with `caller_hung_up` = 0 (and, once, extra rows marked 1 in the same second, see above) |
| Cancelled | A hangs up before B answers | `missed_calls` INVITE 487 |
| Busy | Call a phone already on a call | `missed_calls` INVITE 486 Busy Here |
| Declined | B declines | `missed_calls` INVITE **486 Busy Here**, not 603: indistinguishable from busy |
| Not answered | Let it ring out | `missed_calls` INVITE **486 Busy Here**, about 78 s after the call was made. Not 408 or 480 |
| Not registered | B in airplane mode | `missed_calls` INVITE **408** and **500** ("Server error on LIR select next S-CSCF") in the same second |

So **busy, declined and not answered share one code (486)** and cannot be told apart from the rows. TODO(network lead,
question 4 of the call record agreement, PRD decision 8): decide the `end_reason` values with that in mind.

`scscf.contact` stays at 0 rows even while phones are registered and calling, so it is not a way to tell whether a
phone is registered.

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
