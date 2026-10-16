# RatelMeter agent: the assignments client and the ingest poster
Labels: type:feature, area:ratel-meter, priority:p1, risk:high

**Module:** RatelMeter agent | **Roadmap week:** 2 to 3 | **Owner:** TODO | **Reviewer:** TODO | **Target:** TODO
**Ready:** the assignments client yes (the operation `link_list_assignments` exists). The poster waits for M-01.
**Source:** `services/meter_agent/assignments/__init__.py` (`AssignmentCache`) and `ingest/__init__.py` (`MeterPoster`), both stubs; Build Plan, RatelMeter spec.

## Objective
The agent can learn which IMSI holds an address (RatelLink `GET /v1/assignments`) and deliver a batch of records (the ingest call), through the existing protocols.

## Scope
- `AssignmentCache`: fetch `GET /v1/assignments` with the agent's own RatelLink API key, replace the cache each interval, keep the old cache on a transient failure and never raise.
- `MeterPoster`: send a batch, return `True` only on acknowledgement, so the spool can use it as its sender.
- API keys come from owner-only environment variables (`METER_AGENT_RATEL_LINK_API_KEY`).

## Out of scope
Creating keys (RatelLink admin CLI). Server side of the ingest (M-11).

## Depends on
M-01 for the poster's request shape. The assignments client can use the mock now.

## Contract impact
None (uses the contract as written).

## Acceptance criteria
- [ ] Client tests with a fake server: success, 401, timeout, malformed body; none of them raise out of the cache
- [ ] A refresh failure keeps the old mapping (test)
- [ ] The key never appears in a log line or an exception message (the session log guard stays green)
- [ ] `make check` is green

## Data, security and privacy
Bearer key only from the environment. No IMSI or address in operational logs.

## Testing
Unit and failure-path. Lab: covered by lab session 1 section E.
