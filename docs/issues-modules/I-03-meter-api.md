# Module meter_api: the RatelMeter API is demo-ready and tested
Labels: type:feature, type:database, area:ratel-meter, area:contracts, priority:p1, risk:high

**Module:** meter_api (`services/app/meter_api`) | **Owner:** TODO (one person owns this module) | **Backup:** TODO | **Reviewer(s):** TODO
**Blocked or unsure? Ask the project lead.** Do not wait: say what you are waiting for, in this issue.
**Source:** `docs/DEMO_SCRIPT.md`; `docs/issues-modules/README.md`; the deliverables below.

## What this module is for
The part of the demo finish line this module serves, and nothing else. The deliverables below are the work; this issue is the module's checklist. Each deliverable is described in full under "Deliverable details" below.

## Deliverables
- [ ] M-01 Contracts: specify the agent's ingest call to the RatelMeter API
- [ ] M-11 RatelMeter API: ingest endpoint and the usage record store
- [ ] M-12 RatelMeter API: GET /v1/usage
- [ ] M-13 RatelMeter API: call records and GET /v1/calls
- [ ] M-28 RatelMeter API: reconcile our usage against the network's own counters

## The module is done when
- [ ] Intervals and calls are stored once by their key; a replay overwrites (test on a real PostgreSQL)
- [ ] meter_get_usage and meter_get_calls are removed from not_implemented.txt and pass the drift test and Schemathesis
- [ ] Pagination covers more than 5,000 records with no gap and no duplicate
- [ ] Usage for a real session matches the interface counters within 1% (lab)
- [ ] The reconciliation check flags a deliberately wrong total (proven able to fail)
- [ ] Migrations apply and roll back; no IMSI or number in operational logs
- [ ] `make check` is green on `main` with this module's changes
- [ ] Its runbook or README is accurate and was followed once

## What this module needs from others
M-01 (the ingest call); #26 and the network team (call records, N7); bss-app deployed (M-27).

## Not in this module
Anything on the Build Plan's "What not to build yet" list.

## Deliverable details

### M-01 Contracts: specify the agent's ingest call to the RatelMeter API

**Ready:** no, needs the project lead's decision on the shape (DECISIONS_PENDING, open question 4)
**Source:** Build Plan, RatelMeter spec (record shape and key); #25 ("the agent-to-API ingest call is not in the frozen contracts").

#### Objective
The call the data agent makes to deliver 300-second records is in `contracts/openapi.yaml`, served by the mock, so the agent and the API can be built independently.

#### Scope
- One new operation. Record: `imsi`, `period_start`, `period_end`, `bytes_up`, `bytes_down` (integers, UTC epoch seconds). The key is `imsi + period_start`: sending the same interval again overwrites, never duplicates.
- Batch size, authentication of the agent to this API, and error codes: TODO, proposed in the issue by the person who takes it, decided by the project lead.
- The operation is listed in `contracts/not_implemented.txt` until M-11 implements it.

#### Out of scope
The storage and the endpoint's code (M-11), call records (M-13).

#### Depends on
A decision on the points marked TODO. Nothing else.

#### Contract impact
Changes `openapi.yaml`, `not_implemented.txt` and the mock in one commit.

#### Acceptance criteria
- [ ] The operation validates (`make contract`) and follows the contract conventions test
- [ ] The mock accepts a valid batch and rejects an invalid one
- [ ] Replay of an identical interval is documented as an overwrite, with the example in the contract
- [ ] No IMSI appears in any example outside the synthetic fixtures

#### Data, security and privacy
Records are personal data. Integers only for bytes. UTC epoch seconds.

#### Testing
Contract tests. No lab.

### M-11 RatelMeter API: ingest endpoint and the usage record store

**Ready:** no, waits for M-01 (the operation's shape)
**Source:** Build Plan, RatelMeter spec ("records every 300 seconds", upsert on `imsi + period_start`); `services/app/meter_api` (empty).

#### Objective
The API accepts the agent's batches, stores each interval once, and a replay overwrites instead of adding.

#### Scope
- The ingest endpoint from M-01 and its storage in PostgreSQL, through a migration under `services/app/migrations/` (reviewed as a database change).
- Upsert on `imsi + period_start`. Reject negative or non-integer bytes.
- Authentication of the agent as M-01 decides.
- Remove the operation from `contracts/not_implemented.txt` in the same PR.

#### Out of scope
`GET /v1/usage` (M-12), rating and charging.

#### Depends on
M-01.

#### Contract impact
Yes: `not_implemented.txt` (and `openapi.yaml` if M-01 left a gap).

#### Acceptance criteria
- [ ] The same interval posted twice leaves one row (test on a real PostgreSQL)
- [ ] A batch with one bad record is rejected as a whole or per record as M-01 says, never half-stored silently
- [ ] Migration applies and rolls back
- [ ] Schemathesis passes on the new operation
- [ ] No IMSI in operational logs

#### Data, security and privacy
Records are personal data: access follows the VPN rules in `deploy/bss-app/README.md`.

#### Testing
Unit, integration (PostgreSQL), contract.

### M-12 RatelMeter API: GET /v1/usage

**Ready:** no, waits for M-11
**Source:** `contracts/openapi.yaml` operation `meter_get_usage`; Build Plan, RatelMeter spec; Week 3 gate (usage matches the interface counters within 1%).

#### Objective
RatelBSS can read a line's usage records over a period, with the pagination the contract defines.

#### Scope
Implement `meter_get_usage` exactly as the contract says (at most 5,000 records, `next_cursor`). Remove `meter_get_usage` from `contracts/not_implemented.txt` in the same PR.

#### Out of scope
Calls (M-13), rating (M-17).

#### Depends on
M-11.

#### Contract impact
`not_implemented.txt`.

#### Acceptance criteria
- [ ] Response matches the contract (drift test and Schemathesis pass)
- [ ] Pagination covers 12,000 records with no gap and no duplicate (test)
- [ ] Bytes are integers, times are UTC epoch seconds
- [ ] On the lab, usage for a real session matches the interface counters within 1% (Week 3 gate)

#### Data, security and privacy
Personal data; no IMSI in logs.

#### Testing
Unit, integration, contract; the 1% check is part of lab session 1 section E.

### M-13 RatelMeter API: call records and GET /v1/calls

**Ready:** no. Do not start: waits for #26 and the `end_reason` enum.
**Source:** `contracts/openapi.yaml` operation `meter_get_calls`; `docs/call-record-agreement.md`.

#### Objective
Call records are stored once by `call_id` and returned by `GET /v1/calls`.

#### Scope
To be completed after #26 is signed: the ingest shape for calls, the `end_reason` enum in the contract, the store and the endpoint. Remove `meter_get_calls` from `contracts/not_implemented.txt` in the same PR.

#### Out of scope
Charging for calls (VOI-7 in the PRD, not before the demo unless the PRD says so).

#### Depends on
#26; M-11 for the store pattern.

#### Contract impact
Yes: `end_reason`, `not_implemented.txt`.

#### Acceptance criteria
- [ ] A call posted twice is stored once (test)
- [ ] An unanswered call has `answered_at` null
- [ ] Contract, drift and Schemathesis pass

#### Data, security and privacy
Call records are personal data. No number in operational logs.

#### Testing
Unit, integration, contract.

### M-28 RatelMeter API: reconcile our usage against the network's own counters

**Ready:** no, waits for N7 (where the network's records are read from) and M-12
**Source:** `docs/DEMO_SCRIPT.md` act 6 ("every byte and every call matching the network's own records"); Roadmap Week 7 (reconciliation reports).

#### Objective
For a day or a session, our stored usage and our stored calls can be compared with the network's own totals, and a difference over 1% for data is flagged.

#### Scope
The comparison and its output (what the line page and RatelOps show). Where the network's totals come from: TODO(network team, N7). Shape of the output: TODO, agreed with M-29 first.

#### Out of scope
Fixing a difference automatically. Billing corrections.

#### Depends on
M-12, M-07, N7, #26 for calls.

#### Contract impact
Probably yes (a new operation or a field); decided in the issue before building.

#### Acceptance criteria
- [ ] A deliberately wrong total is flagged (the check is proven able to fail)
- [ ] A correct day passes within 1% on the lab
- [ ] No IMSI in operational logs

#### Data, security and privacy
Personal data.

#### Testing
Unit; the real comparison is a lab run.
