# Runbook: create a real line through RatelLink and prove it (the Week 2 gate)

This is the manual part of RatelLink's acceptance ([W2-04](../issues-week2/W2-04-ratellink-acceptance-tests.md))
and the real-SIM path ([W2-07](../issues-week2/W2-07-real-sim-path.md)). A line created **through the
API** must attach through our radio, browse, and register for calls. Never create the subscriber by
hand in MongoDB: the point is to test RatelLink.

Never put a key, a token or a full IMSI in a ticket, a chat message, a screenshot or this file. In
the record below, a SIM is identified by its **last four digits** only.

- **Who:** a developer with the network team present (the developers do not log in to the core hosts).
- **Where:** the lab core only. Never production, never a customer SIM.
- **Companion:** the network team's *Integration Guide*, section 7, and the *Operations Runbook*
  (kept next to the Build Plan, see [source/README.md](../source/README.md)).

## Before you start (all must be true)

| Check | Who | Done |
| ----- | --- | ---- |
| RatelLink is installed and running on core-cp, from `deploy/core-cp/README.md` | Network team | |
| MongoDB authentication is on, the HSS and PCRF were updated, and one test call was made after | Network team | |
| The unique `imsi` index exists on `subscribers` and RatelLink's start-up log does not say `startup.subscribers.index.missing` | Network team | Index seen 2026-10-15 (project lead); start-up log not yet checked |
| Python 3.12 is installed on core-cp next to the system Python 3.10 (N9) | Network team | |
| The encryption key file exists and **its offline backup exists with a named owner** (risk R-14) | Project lead | |
| A caller key was made with `admin_cli api-key create` and handed over without being written down | Project lead | |
| The static address range for lines is agreed and `RATEL_LINK_UE_POOL` is set to it (N2) | Network team | |
| The voice template was exported (keys left out) and `RATEL_LINK_VOICE_TEMPLATE_FILE` points at it (N1) | Network team | |
| The test SIM's keys were issued by the lab and its PLMN has a **two-digit MNC** (62100) | Network team | |
| A VoLTE **Android** phone for calls (iPhones cannot place outgoing calls today), and a second phone to call | Developer | |

If any row is not done, stop and write down which one and who owns it. That is a finding, not a failure.

## 1. Check the template comparison on the real export first (no phone needed)

On your own machine, with the key-free export saved **outside the repository**:

```
RATEL_LINK_TEMPLATE_COMPARE_FILE=/path/to/export.json make test
```

The test `tests/ratel_link/acceptance/test_subscriber_matches_template.py` then also compares what
RatelLink would write against the network team's real document. Any line it prints names a path and
a type (never a value). Fix the code or ask the network team, then run it again until it is empty.

## 2. Import the SIM's keys without them touching a file, a command line or the history

Run these on core-cp, in `bash`, as a user allowed to reach `127.0.0.1:8081`. Each `read -rs` types
nothing on screen and is not recorded in the history.

```
read -rs -p "caller key: " TOKEN; echo
read -rs -p "IMSI: " IMSI; echo
read -rs -p "Ki: " KI; echo
read -rs -p "OPc: " OPC; echo
printf '{"imsi":"%s","ki":"%s","opc":"%s"}' "$IMSI" "$KI" "$OPC" \
  | curl -sS -X POST http://127.0.0.1:8081/v1/sims \
      --config <(printf 'header = "Authorization: Bearer %s"\n' "$TOKEN") \
      -H 'Content-Type: application/json' --data-binary @-
```

Keep the shell open: step 5 needs `KI` and `OPC` once more, and ends by clearing them.

Expected: `{}` and HTTP 200. Repeating it is harmless. Sending different keys for the same IMSI is 409.

## 3. Activate with voice on

```
printf '{"msisdn":"234XXXXXXXXXX","speed_ul_mbps":5,"speed_dl_mbps":10,"voice":true}' \
  | curl -sS -X POST "http://127.0.0.1:8081/v1/lines/$IMSI/activate" \
      --config <(printf 'header = "Authorization: Bearer %s"\n' "$TOKEN") \
      -H 'Content-Type: application/json' --data-binary @-
```

Use the number the lab issued, in the stored form: `234` and ten digits. Then read it back:

```
curl -sS "http://127.0.0.1:8081/v1/lines/$IMSI" \
  --config <(printf 'header = "Authorization: Bearer %s"\n' "$TOKEN")
```

Expected: `status` `active`, `apns` `["internet","ims"]`, the fixed address inside the agreed range,
the speeds you sent, and **no** `security`, `ki` or `opc` anywhere.

## 4. Attach, browse, call (steps from the Integration Guide, section 7)

| Step | What to do | Expected |
| ---- | ---------- | -------- |
| 4.1 | Insert the SIM, power cycle the phone (or toggle airplane mode) | Within about a minute it shows the network |
| 4.2 | Open a web page | It loads, and the phone's address is the fixed one from step 3 |
| 4.3 | Check IMS registration (the network team reads the S-CSCF log) | The phone registered for calls by itself |
| 4.4 | Call the second phone using the national form (`0` and ten digits) | It rings and audio is two-way |
| 4.5 | `POST .../data` with `{"mode":"off"}`, then toggle airplane mode | No data, **calls still work** |
| 4.6 | `POST .../data` with `{"mode":"full","speed_ul_mbps":5,"speed_dl_mbps":10}`, then toggle airplane mode | Data is back |
| 4.7 | `POST .../deactivate` with `{"reason":"lab acceptance"}`, then toggle airplane mode | The phone is **rejected** (EMM cause #8) |
| 4.8 | `POST .../activate` again with the same body, then toggle airplane mode | The phone attaches again (**record this carefully**, see below) |

Step 4.8 matters: deactivating deletes the subscriber document, including the sequence number the
HSS keeps in it, so the SIM may reject the network's challenge after a re-activation until it
resynchronises. Write down exactly what happened. It decides bar-or-delete for good
([DECISIONS_PENDING.md](../DECISIONS_PENDING.md), item 52; spike W2-05).

Changes take effect at the **phone's next attach**. There is no live push yet.

## 5. Prove no key leaked

- The automated search ran green: `make check` (the pytest log) and, with MongoDB available,
  `pytest -m integration tests/ratel_link/acceptance` (a real RatelLink process, its admin command
  line, and the database).
- On core-cp, search RatelLink's own log for the SIM's keys without printing them, in the same
  shell. The keys go in through a process substitution, so they are never on a command line where
  `ps` could show them:

```
journalctl -u ratel-link --since "-2h" | grep -c -i -F -f <(printf '%s\n%s\n' "$KI" "$OPC")
unset TOKEN IMSI KI OPC
```

Expected: `0`. Do the same for the nginx log files if the proxy is in use.
- No screenshot, ticket or chat message holds a key, a caller key or a full IMSI.

## 6. Record it

Copy this into the pull request or a dated file under `docs/`. One record per run.

| | |
| --- | --- |
| Date and time (Lagos) | |
| Who ran it, and who from the network team was present | |
| SIM (last four digits of the IMSI only) | |
| Phone model and OS | |
| RatelLink release (`/opt/ratel-link/current` target) | |
| Step 1 template comparison | clean / differences (paths and types only) |
| Steps 2 and 3 | HTTP codes |
| 4.1 attach | pass / fail, how long |
| 4.2 browse | pass / fail |
| 4.3 IMS registration | pass / fail |
| 4.4 call | pass / fail |
| 4.5 data off, calls still work | pass / fail |
| 4.6 data on | pass / fail |
| 4.7 deactivate rejects the SIM | pass / fail |
| 4.8 re-activate attaches again | pass / fail, what the phone showed |
| 5 log search | 0 matches / other |
| Blockers and their owners | |

A failure that is not a provisioning problem goes to the network team with the IMSI, the time in
Lagos time and what the phone displayed. Core log timestamps are UTC, one hour behind Lagos.
