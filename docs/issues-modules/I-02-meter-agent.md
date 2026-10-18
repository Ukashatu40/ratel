# Module meter_agent: the RatelMeter agent is demo-ready and tested
Labels: type:feature, area:ratel-meter, area:deployment, priority:p1, risk:high

**Module:** meter_agent (`services/meter_agent`) | **Owner:** TODO (one person owns this module) | **Backup:** TODO | **Reviewer(s):** TODO
**Blocked or unsure? Ask the project lead.** Do not wait: say what you are waiting for, in this issue.
**Source:** `docs/DEMO_SCRIPT.md`; `docs/issues-modules/README.md`; the deliverables below.

## What this module is for
The part of the demo finish line this module serves, and nothing else. The deliverables below are the work; this issue is the module's checklist. Each deliverable is described in full under "Deliverable details" below.

## Deliverables
- [ ] M-07 RatelMeter agent: the real counter reader for core-up
- [ ] M-08 RatelMeter agent: the assignments client and the ingest poster
- [ ] M-09 RatelMeter agent: entry point, settings, systemd unit and runbook for core-up
- [ ] M-10 RatelMeter agent: call mode on the voice VM

## The module is done when
- [ ] Data mode runs on core-up as a service; totals match the interface counters within 1% over a real session (lab)
- [ ] Stopping the agent mid-interval and restarting loses nothing and counts nothing twice (test and lab)
- [ ] With the API offline for an hour then back, every spooled interval arrives in order, none lost, none doubled
- [ ] A counter reset is counted from zero, never negative; zero-byte intervals are skipped
- [ ] The spool and settings are owner-only; no IMSI or address in operational logs
- [ ] Call mode reads the source the network team enabled (after #26) and posts finished calls once
- [ ] `make check` is green on `main` with this module's changes
- [ ] Its runbook or README is accurate and was followed once

## What this module needs from others
RatelLink assignments (done); M-01 for the ingest call; network team for counter access, NTP, and the call-record source.

## Not in this module
Anything on the Build Plan's "What not to build yet" list.

## Deliverable details

### M-07 RatelMeter agent: the real counter reader for core-up

**Ready:** partly. The reader and its tests against recorded snapshots can start now. Picking the mechanism needs lab session 1, section D.
**Source:** Build Plan, RatelMeter spec "How data works"; #24 and #25 (now in lab session 1); `services/meter_agent/counters/__init__.py` (the `CounterReader` protocol, a stub).

#### Objective
A real implementation of `CounterReader.read()` returns cumulative `bytes_up_total` and `bytes_down_total` for every address on core-up's `ogstun`, with the mechanism measured to lose no bytes.

#### Scope
- Implement `CounterReader` for the chosen mechanism (nftables per-element counters, per-line accounting rules, or conntrack accounting; the lab decides).
- Packets from a phone's address count as upload, to it as download.
- Until the lab decides, the parsing part works on recorded snapshots (synthetic, no real addresses) and has its tests.

#### Out of scope
The loop and the posting (M-08, M-09). Call mode (M-10).

#### Depends on
Lab session 1 section D for the final mechanism. Network team provides read access to the counters on core-up.

#### Contract impact
None.

#### Acceptance criteria
- [ ] `read()` returns integers keyed by address; a malformed snapshot raises a clear error and is never counted as zero
- [ ] Tests cover many short flows, one long transfer and an empty table (recorded snapshots)
- [ ] On the lab, totals are within 1% of the interface's own byte counters (record in lab session 1)
- [ ] `tests/architecture` rules for the agent still pass (no MongoDB or SQL driver in the agent)

#### Data, security and privacy
Addresses and counters are personal data once joined to an IMSI: no address in operational logs.

#### Testing
Unit; the accuracy check is a lab run.

### M-08 RatelMeter agent: the assignments client and the ingest poster

**Ready:** the assignments client yes (the operation `link_list_assignments` exists). The poster waits for M-01.
**Source:** `services/meter_agent/assignments/__init__.py` (`AssignmentCache`) and `ingest/__init__.py` (`MeterPoster`), both stubs; Build Plan, RatelMeter spec.

#### Objective
The agent can learn which IMSI holds an address (RatelLink `GET /v1/assignments`) and deliver a batch of records (the ingest call), through the existing protocols.

#### Scope
- `AssignmentCache`: fetch `GET /v1/assignments` with the agent's own RatelLink API key, replace the cache each interval, keep the old cache on a transient failure and never raise.
- `MeterPoster`: send a batch, return `True` only on acknowledgement, so the spool can use it as its sender.
- API keys come from owner-only environment variables (`METER_AGENT_RATEL_LINK_API_KEY`).

#### Out of scope
Creating keys (RatelLink admin CLI). Server side of the ingest (M-11).

#### Depends on
M-01 for the poster's request shape. The assignments client can use the mock now.

#### Contract impact
None (uses the contract as written).

#### Acceptance criteria
- [ ] Client tests with a fake server: success, 401, timeout, malformed body; none of them raise out of the cache
- [ ] A refresh failure keeps the old mapping (test)
- [ ] The key never appears in a log line or an exception message (the session log guard stays green)
- [ ] `make check` is green

#### Data, security and privacy
Bearer key only from the environment. No IMSI or address in operational logs.

#### Testing
Unit and failure-path. Lab: covered by lab session 1 section E.

### M-09 RatelMeter agent: entry point, settings, systemd unit and runbook for core-up

**Ready:** no, waits for M-07 and M-08
**Source:** Build Plan, RatelMeter "Done when"; #25; `services/meter_agent/README.md` (planned structure: `main.py`, `config.py`, `runners/`).

#### Objective
The data agent runs on core-up as a service that survives a restart, with a runbook page next to RatelLink's.

#### Scope
- `main.py` and settings for the data mode; wire reader, cache, poster and spool into the loop in `agent.py`.
- A systemd unit (hardened like RatelLink's), an owner-only settings file template, a README for the host under `deploy/`.
- Runbook: `docs/runbooks/ratel-meter.md` (symptoms, what to check, who to call).
- NTP must be on core-up (network team, Week 3): the intervals depend on the clock.

#### Out of scope
Call mode on the voice VM (M-10).

#### Depends on
M-07, M-08, M-01. Network team for the user account and permissions on core-up.

#### Contract impact
None.

#### Acceptance criteria
- [ ] Stopping the agent mid-interval and restarting loses nothing and counts nothing twice (test and lab)
- [ ] With the API offline for an hour then back, every spooled interval arrives in order (test with a fake poster; lab once)
- [ ] The unit starts at boot and restarts on failure
- [ ] Deployment-file tests (no secret, no host address in committed files) pass
- [ ] The runbook was followed on core-up once and "Last verified" says so

#### Data, security and privacy
Spool directory is owner-only (see PR for #31). No IMSI in operational logs.

#### Testing
Unit, failure-path, lab (lab session 1 section E).

### M-10 RatelMeter agent: call mode on the voice VM

**Ready:** no. Do not start: waits for #26. On 2026-10-16 no table or file on the voice VM keeps a finished call (`docs/call-record-agreement.md`, lab finding).
**Source:** Build Plan, RatelMeter spec "How calls work"; `docs/call-record-agreement.md`; N7.

#### Objective
Every 60 seconds the agent reads new finished-call records from the source the network team enabled, joins start and end, and posts them.

#### Scope
To be written once the source and its table definition exist (columns, key, time zone). Do not guess them.

#### Out of scope
Calls to other networks, SMS, emergency calls, charging for calls.

#### Depends on
#26 signed (the network team enables a call-record source and sends the table definition); M-13 for the API side.

#### Contract impact
`end_reason` enum in `openapi.yaml` in the same commit as the agreement.

#### Acceptance criteria
To be written after sign-off. At minimum: replay of the same call overwrites; a restart mid-call is handled as the agreement says; UTC epoch seconds.

#### Data, security and privacy
Call records are personal data. No number in operational logs.

#### Testing
Unit, failure-path, lab.
