# Agree the call record fields with the network team
Labels: type:documentation, area:ratel-meter, area:network, priority:p1, risk:high

**Week:** 2 | **Target date:** 2026-10-14 (draft 2026-10-12) | **Owner:** @ml-lawarn | **Reviewers:** @Ukashatu40 + @CaptRaven (network lead)
**Source:** Build Plan, RatelMeter spec "How calls work"; week two RatelVoice column ("call record fields agreed with RatelMeter").

## Re-planned 2026-10-08
@ml-lawarn drafts the proposal from the contract's `CallRecord` fields and a list of questions; @CaptRaven (network side) answers what Kamailio can produce. The agreement is the network lead's to sign off, not the drafter's. Draft by 2026-10-12.

## Objective
The software and network teams agree, in writing, exactly what RatelVoice writes and what `/v1/calls` returns, so call mode can start.

## Context
The S-CSCF writes a record when each call starts and ends, using Kamailio's accounting (the `acc` and `dialog` modules) into RatelVoice's MySQL. Every 60 seconds the agent reads new records, joins start and end into one record, and posts it to the RatelMeter API. The network team owns the Kamailio side. `/v1/calls` returns `call_id`, `from_msisdn`, `to_msisdn`, `started_at`, `answered_at` (null when never answered), `ended_at`, `end_reason`. Calls are keyed on `call_id`.

## Scope
- The MySQL tables and columns the agent will read; how start and end rows are linked.
- How `call_id` is produced and why it is stable and unique (replays must overwrite, not duplicate).
- `end_reason` values; how an unanswered call is represented; time zone and format (UTC, epoch seconds in the API).
- Update `contracts/openapi.yaml` (`end_reason` TODO) in the same commit.

## Out of scope
Building call mode. Charging for calls (not before the demo).

## Dependencies
Network team's Kamailio accounting configuration. W2-12.

## Acceptance criteria
- A short document in `docs/` signed off by the network lead and the RatelMeter owner.
- `openapi.yaml` updated, `TODO(contract)` for `end_reason` resolved.
- Call records are treated as personal data in the agreement: access, no logging of numbers.

## Suggested skill level
Communication and data modeling; SIP and Kamailio knowledge helps. Reviewer: one, plus the network lead.
