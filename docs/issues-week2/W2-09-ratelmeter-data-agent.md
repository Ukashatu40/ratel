# RatelMeter data agent running on core-up
Labels: type:feature, area:ratel-meter, priority:p1, risk:high

**Week:** 2 | **Target date:** TODO (running by Oct 9) | **Owner:** TODO | **Reviewer:** TODO
**Source:** Build Plan, RatelMeter spec; week two software column ("RatelMeter's data agent running on core-up"); week 3 completes the API and `/v1/usage`.

## Objective
The data-mode agent runs on core-up, reads per-address counters, and produces correct 300-second records ready for the RatelMeter API.

## Scope
- Read per-address counters with the mechanism chosen in W2-08.
- Every 300 seconds, aligned to the clock in UTC (`common.timeutil.interval_start`): subtract the previous reading; remember the last reading (`ue_ip`, `bytes_up_total`, `bytes_down_total`, `read_at`).
- Map address to IMSI with RatelLink's `GET /v1/assignments`, cached and refreshed every interval (use the mock until W2-03 is on the lab).
- A reading lower than the last means the UPF or host restarted: count the new reading from zero, never a negative increase.
- Skip intervals with zero bytes.
- Post batches to the RatelMeter API; **spool to disk** when it is unreachable and replay in order.
- Record shape: `imsi`, `period_start`, `period_end`, `bytes_up`, `bytes_down` (internal richer record: `record_id`, `ue_ip`, `apn`, `source`). Key: `imsi + period_start`.

## Out of scope
Call mode (starts once W2-10 is agreed). The API's storage and `/v1/usage` (Week 3). Online charging.

## Dependencies
W2-08. W2-03 (or the mock). **Decision needed:** the agent-to-API ingest call is not in the frozen contracts (docs/DECISIONS_PENDING.md, open question 4); agree it in W2-12. NTP on core-up (Network team, Week 3, but note clock sync matters from now).

## Acceptance criteria
- Agent runs on core-up as a service with a runbook note.
- Intervals are aligned and a replayed interval produces the same key.
- Counter reset yields a correct non-negative result (unit test).
- Stopping the agent mid-interval and restarting loses nothing and counts nothing twice (test).
- With the API offline, records spool and replay in order, none lost, none doubled (test).
- Over a real session, totals match the interface counters within 1% (verify on the first real traffic; the gate for this is Week 3).

## Data / integrity requirements
Never lose an interval, never double count, UTC epoch seconds, bytes as integers.

## Security / privacy requirements
Records are personal data: no IMSI or MSISDN in operational logs. The agent's own RatelLink API key (`METER_AGENT_RATEL_LINK_API_KEY`, sent as `Authorization: Bearer <key>`) comes from an owner-only env file.

## Testing requirements
Unit (delta, reset, alignment), failure-path (spool, replay), **lab** (accuracy).

## Suggested skill level
Linux and Python; careful with time, counters and failure handling.
