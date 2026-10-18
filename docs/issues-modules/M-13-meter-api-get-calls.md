# RatelMeter API: call records and GET /v1/calls
Labels: type:feature, area:ratel-meter, priority:p2, risk:high

**Module:** RatelMeter API | **Roadmap week:** 4 | **Owner:** TODO | **Reviewer:** TODO | **Target:** TODO
**Ready:** no. Do not start: waits for #26 and the `end_reason` enum.
**Source:** `contracts/openapi.yaml` operation `meter_get_calls`; `docs/call-record-agreement.md`.

## Objective
Call records are stored once by `call_id` and returned by `GET /v1/calls`.

## Scope
To be completed after #26 is signed: the ingest shape for calls, the `end_reason` enum in the contract, the store and the endpoint. Remove `meter_get_calls` from `contracts/not_implemented.txt` in the same PR.

## Out of scope
Charging for calls (VOI-7 in the PRD, not before the demo unless the PRD says so).

## Depends on
#26; M-11 for the store pattern.

## Contract impact
Yes: `end_reason`, `not_implemented.txt`.

## Acceptance criteria
- [ ] A call posted twice is stored once (test)
- [ ] An unanswered call has `answered_at` null
- [ ] Contract, drift and Schemathesis pass

## Data, security and privacy
Call records are personal data. No number in operational logs.

## Testing
Unit, integration, contract.
