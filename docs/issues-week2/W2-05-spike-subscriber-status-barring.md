# Spike: does Open5GS v2.8.0 enforce subscriber_status barring?
Labels: type:investigation, area:ratel-link, priority:p1, risk:high

**Week:** 2 (carried from Week 1) | **Target date:** 2026-10-12 | **Owner:** @CaptRaven | **Reviewer:** @Ukashatu40
**Source:** Build Plan, Contract 1 "Deactivation is delete and rewrite, for now"; RatelLink spec "Data it keeps"; Week 1 RatelLink bullets.
**TODO confirm:** this was a Week 1 task. If the answer is already written down, link it and close this issue.

## Re-planned 2026-10-08
Not on the path to the first real-SIM attach: "delete and rewrite" works without it. Moved to Mon 2026-10-12 so the network lead can first unblock W2-02 (the Open5GS template) and W2-08.

## Update 2026-10-14
`/deactivate` is built as **delete** (Build Plan), so the spike no longer blocks it. Two things to measure, for DECISIONS_PENDING item 52: (a) does barring work, and (b) **does a SIM attach again after its document was deleted and re-created** (the HSS's `security.sqn` is lost with the document).

## Objective
Know whether the MME rejects a barred subscriber, so RatelLink can choose between "delete and rewrite" and the cleaner `subscriber_status` barring field.

## Questions
1. Set `subscriber_status` on a lab subscriber: does the MME reject the attach?
2. Does a barred subscriber keep or lose registration for calls?
3. Does `status: barred` in RatelLink's `line_state` then mean a flag or a deleted document?

## Method
Lab core-cp, Open5GS v2.8.0, a lab test subscriber. Measure, do not assume. Timebox: half a day.

## Deliverable
A short written answer in `docs/` (or an ADR if it changes the design). No production code. Update W2-02 accordingly.

## Out of scope
Implementing barring.

## Suggested skill level
Comfortable with Open5GS and MongoDB on the lab. Reviewer: one.

## Source reading 2026-10-16
In Open5GS v2.8.0 the MME's `mme_s6a_handle_ula` and `mme_s6a_handle_idr` do not read `subscriber_status` or the barring data (see [spike-live-changes.md](../spike-live-changes.md)). So a barred line is probably still let in. This is not measured: the lab test (steps 4.7 and 4.8 of the lab runbook) is still needed, together with the question whether a re-activated SIM attaches after the sequence number is lost.
