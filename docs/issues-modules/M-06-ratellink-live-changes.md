# RatelLink: apply data changes without waiting for the next attach (detach and re-attach)
Labels: type:feature, area:ratel-link, priority:p3, risk:critical

**Module:** RatelLink | **Roadmap week:** 5, only if the spike says it is small | **Owner:** TODO | **Reviewer:** TODO (two required) | **Target:** TODO
**Ready:** no. Do not start. The Build Plan forbids live-change code before the spike answers; waits for lab session 1 section C and decision 57.
**Source:** `docs/spike-live-changes.md`; N5; PRD CHG-6 (live changes, P1, to read once the PRD is in hand); DECISIONS_PENDING item 57.

## Objective
After a data change, the phone is detached and re-attaches within 60 seconds with its new record.

## Scope
After the existing `$set`, set and then clear the boolean `request_cancel_location` on that one subscriber document. The replica set and the HSS setting `use_mongodb_change_stream` are done by the network team first.

## Out of scope
Pushing a new speed into a running session (needs new C code in the PCRF; not recommended).

## Depends on
Lab session 1 section C passes; network team agrees the field outside the integration guide's list and the `schema_version` change; replica set running.

## Contract impact
None expected. Whether the response says "applied now" is a product call (PRD).

## Acceptance criteria
- [ ] The field is a BSON boolean and is never left `true`
- [ ] Nothing else in the document changes; HSS-owned fields survive
- [ ] A failure to detach does not undo the data change
- [ ] On the lab, a data change reaches the phone within 60 seconds without airplane mode
- [ ] If the lab test fails, this issue is closed and the airplane-mode fallback stays

## Data, security and privacy
No new privilege. No value logged.

## Testing
Unit, MongoDB integration, lab.
