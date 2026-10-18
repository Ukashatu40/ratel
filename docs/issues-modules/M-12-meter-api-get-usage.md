# RatelMeter API: GET /v1/usage
Labels: type:feature, area:ratel-meter, priority:p1, risk:high

**Module:** RatelMeter API | **Roadmap week:** 3 | **Owner:** TODO | **Reviewer:** TODO | **Target:** TODO
**Ready:** no, waits for M-11
**Source:** `contracts/openapi.yaml` operation `meter_get_usage`; Build Plan, RatelMeter spec; Week 3 gate (usage matches the interface counters within 1%).

## Objective
RatelBSS can read a line's usage records over a period, with the pagination the contract defines.

## Scope
Implement `meter_get_usage` exactly as the contract says (at most 5,000 records, `next_cursor`). Remove `meter_get_usage` from `contracts/not_implemented.txt` in the same PR.

## Out of scope
Calls (M-13), rating (M-17).

## Depends on
M-11.

## Contract impact
`not_implemented.txt`.

## Acceptance criteria
- [ ] Response matches the contract (drift test and Schemathesis pass)
- [ ] Pagination covers 12,000 records with no gap and no duplicate (test)
- [ ] Bytes are integers, times are UTC epoch seconds
- [ ] On the lab, usage for a real session matches the interface counters within 1% (Week 3 gate)

## Data, security and privacy
Personal data; no IMSI in logs.

## Testing
Unit, integration, contract; the 1% check is part of lab session 1 section E.
