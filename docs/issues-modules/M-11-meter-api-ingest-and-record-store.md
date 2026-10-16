# RatelMeter API: ingest endpoint and the usage record store
Labels: type:feature, type:database, area:ratel-meter, priority:p1, risk:high

**Module:** RatelMeter API | **Roadmap week:** 3 | **Owner:** TODO | **Reviewer:** TODO | **Target:** TODO
**Ready:** no, waits for M-01 (the operation's shape)
**Source:** Build Plan, RatelMeter spec ("records every 300 seconds", upsert on `imsi + period_start`); `services/app/meter_api` (empty).

## Objective
The API accepts the agent's batches, stores each interval once, and a replay overwrites instead of adding.

## Scope
- The ingest endpoint from M-01 and its storage in PostgreSQL, through a migration under `services/app/migrations/` (reviewed as a database change).
- Upsert on `imsi + period_start`. Reject negative or non-integer bytes.
- Authentication of the agent as M-01 decides.
- Remove the operation from `contracts/not_implemented.txt` in the same PR.

## Out of scope
`GET /v1/usage` (M-12), rating and charging.

## Depends on
M-01.

## Contract impact
Yes: `not_implemented.txt` (and `openapi.yaml` if M-01 left a gap).

## Acceptance criteria
- [ ] The same interval posted twice leaves one row (test on a real PostgreSQL)
- [ ] A batch with one bad record is rejected as a whole or per record as M-01 says, never half-stored silently
- [ ] Migration applies and rolls back
- [ ] Schemathesis passes on the new operation
- [ ] No IMSI in operational logs

## Data, security and privacy
Records are personal data: access follows the VPN rules in `deploy/bss-app/README.md`.

## Testing
Unit, integration (PostgreSQL), contract.
