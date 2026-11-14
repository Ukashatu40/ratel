# Evidence for the module issues, as of 2026-11-14

For the project lead to paste, issue by issue. **Tick a box only with the evidence next to it; a box with no evidence stays open.** Records
named here are in `docs/records/` and `docs/runbooks/`. Nothing here is a secret: lines are named by the last four digits of their IMSI
and no key, PIN or number appears.

Two things are not ticked anywhere because they are not true yet: two full rehearsals with no step repeated (#65, M-31), and the independent
reviews (#65, M-24 and M-30). Everything else is below.

## #59 meter_api: close it

| Box | Evidence |
| --- | --- |
| M-13 call records and `GET /v1/calls` | merged (#180), migration `a7c3e1f9b2d4` applied on bss-app 2026-11-03, calls read by RatelDesk |
| Intervals and calls stored once by their key; a replay overwrites (test on a real PostgreSQL) | `test_calls_postgres_integration.py`, `test_repository_postgres_integration.py`; 66 old calls posted twice on 2026-11-03 without a duplicate |
| `meter_get_usage` and `meter_get_calls` removed from `not_implemented.txt`, pass drift and Schemathesis | done in #180; `make check` runs both |
| Pagination covers more than 5,000 records with no gap and no duplicate | `tests/app/meter_api/test_repository.py::test_pagination_covers_12000_records_with_no_gaps_or_duplicates` |
| Usage for a real session matches the interface within 1% (lab) | [meter-agent-accuracy-2026-11-13.md](meter-agent-accuracy-2026-11-13.md): 0.01% (9 Nov), 0.00% (40 min, 13 Nov), 0.01% (25 min, API down, 13 Nov) |
| The reconciliation check flags a deliberately wrong total | `test_reconcile.py` (1.01% fails, 1.00% passes) and three real runs that failed as they should (32.28%, 9.95%, 3.10%) |
| Migrations apply and roll back; no IMSI or number in operational logs | `test_calls_migration.py` (the downgrade refuses while rows exist, by design); the log tests in `test_calls_api.py` |
| `make check` green on `main`; runbook accurate and followed once | CI; `docs/runbooks/ratel-meter.md` followed on core-up, with the findings written into it |

## #58 meter_agent: close it

| Box | Evidence |
| --- | --- |
| M-10 call mode on the voice VM | merged (#181), running since 2026-11-03; [deploy/voice/README.md](../../deploy/voice/README.md) followed |
| Data mode as a service, totals within 1% over a real session (lab) | [meter-agent-accuracy-2026-11-13.md](meter-agent-accuracy-2026-11-13.md) |
| Stopping and restarting mid-interval loses nothing and counts nothing twice (test and lab) | `tests/meter_agent/test_agent_restart.py`; the journal lines `meter.agent.resumed` and `meter.agent.waiting_for_boundary` for two restarts on 2026-11-12; normal rows either side |
| API offline for an hour, every spooled interval arrives in order, none lost, none doubled | 2026-11-12, 60 min: 12 intervals × 2 records, no gap or duplicate, spool emptied; 2026-11-13, 25 min with the API down: stored equals the counting table to the byte (0.01% off the interface). The one 2.5% gap of 2026-11-12 is in the record, unexplained and not reproduced |
| Call mode reads the source and posts finished calls once | the call agent's `assembled` lines (`finished`, `open`); a replay overwrites by Call-ID |
| `make check` green on `main`; runbook accurate and followed once | CI; core-up and voice READMEs, and `scripts/deploy/deploy.sh` used for both agents |

## #57 ratel_link

Tick:
- **M-05** and **"Deactivate and re-activate behave as the lab proved, and the decision is written"**: 2026-11-06 (4.7 rejected, 4.8
  attached and a call placed), `DECISIONS_PENDING.md` item 52, `W2-05`.
- **"A line created only through the API attaches, browses and registers for calls"**: [ratellink-lab-acceptance-2026-11-05.md](ratellink-lab-acceptance-2026-11-05.md).
- **"Every route still requires a key"**: the route-protection test.
- **"A caller key was rotated once with the documented steps"**: `api-key list` shows `bss-app` generation 1 revoked and 2 valid; `lab-import` rotated.
- **"No Ki, OPc or caller key in any log, ticket or screenshot"**: the lab search returned 0 (2026-11-04). *Say in the comment:* two lab caller
  keys (`lab-import-6`, `lab-import-7`) were printed into a chat session on 2026-11-12 and 2026-11-13; both were already disabled, no Ki
  or OPc was involved.
- **`make check` green on `main`**.

Leave open: **M-06** (not built, needs the replica set); **"survives a restart and a MongoDB restart without losing or duplicating a write"**
(not tested; the core-cp reboot test with the network lead would cover half); **"runs from a release on core-cp, the runbook was followed, a
rollback was done once"** (releases installed with `deploy.sh link` on 2026-11-11; a rollback was only tested against fakes).

Also add: `network_access_mode` is written 0 on every activation since release `b561724` (decision 59, 2026-11-11).

## #61 bss_money

Tick **"At zero a line is slowed or cut once, calls still work, and a top-up restores data with out of data reversed (lab)"**:
[demo-acts-4-5-backend-2026-11-10.md](demo-acts-4-5-backend-2026-11-10.md) (the backend, exact to the byte) and the run on two phones on
2026-11-11 (rating journal lines for both acts, speed at most 1 Mbit/s while slowed, calls both ways, tens of Mbit/s after the top-up).

**"A crash mid-run of the rating job rates nothing twice and loses nothing"**: the test is
`tests/app/bss_money/services/test_rating_job_postgres_integration.py::test_a_crash_after_the_deduction_keeps_nothing_and_the_next_run_rates_once`
(PostgreSQL). Tick it only after you have seen that test pass: it is marked `integration`, so check that CI runs it or run
`pytest -m integration` against a local PostgreSQL once.

Leave open: **"Two real reviewers approved every PR; the security review (M-30) found nothing open"**.

## #62 desk

Tick: the sell journey on the real API (2026-11-04 onwards); the line page shows data used and updates within one interval; times in WAT;
CI runs the frontend tests; `make check`. M-29: the line page with usage and the Calls tab are done. **Edit the boxes about the
reconciliation view** to say that act 6 is shown with `reconcile_cli` and `ratel-window.sh` next to RatelDesk, decided 2026-10-21, then
tick them citing `demo-act-6.md`. Leave open: "customer care can complete each journey with the written runbook" (a care person has not
followed `rateldesk.md` yet).

## #63 pay

Tick: **"A voucher redeems from the page and credits once"** (2026-11-04 onwards, balance shown, the wallet equals the ledger). Leave
open: the 3G box (Arfaaah measured 2.7 s locally; through the proxy it is not measured, and gzip on `/pay` is not confirmed: see below);
PIN and time display; the gateway path.

## #52 lab session 1

| Section | Result |
| --- | --- |
| A, the gate | pass: created through the API, attach, browse, calls with two-way audio and IMS registration, key search 0. **Open:** the audit entries naming the caller; data off and on (4.5, 4.6) |
| B, deactivate and re-activate | pass: rejected, re-attached and called. **Not tested:** barring (`subscriber_status`) |
| C, live changes | deferred: needs the single-node replica set (N5); owner the network team |
| D, byte counter | pass: the counting table is within 0.01% of the interface, 0.17% over 2.2 GB; R-03 updated |
| E, the data agent on core-up | pass: service, within 1%, restart and outage |
| F, the RatelBSS flow | **open:** count `/activate` calls for one sale (during rehearsal 1, step 1.5: `sudo journalctl -u ratel-link --since "-3min" --no-pager \| grep -c line.activate` on core-cp should say 1) and read the line back from RatelLink (needs a key) |

Close #52 when every section reads pass or a named blocker with an owner (C is the network team's, F is yours).

## #64 network team (his to tick; tell him what is true)

True and evidenced: MongoDB authentication and one test call (N3); Python 3.12 and RatelLink installed; the voice template (N1); SIM keys and
the two-digit MNC; the eNB joined; the `ims` APN; NTP; the call record source; the per-line byte counter measured and handed over (nftables,
0.00% to 0.01%); `network/voice/stack/` in Git (his PR #224). **Untick or reword "#26 signed"**: it was accepted on his word, not signed
(`docs/call-record-agreement.md`, section 12). Still open on his side: smartphone voice (IPsec through the P-CSCF), hand-made
subscribers removed, the owner and backup of `/etc/osmocom` and `hlr.db`, the core-cp reboot test, the six phone models, RatelOps.

## #65 project lead

Ticked: M-22, M-23 (the key backup is proven: the offline copy decrypts to the live key, 2026-11-05), M-27. Open and honest: M-24 and M-30
(independent reviews), M-31 (rehearsals: sheet and checklist exist, none run yet).
