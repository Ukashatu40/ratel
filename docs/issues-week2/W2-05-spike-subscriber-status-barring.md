# Spike: does Open5GS v2.8.0 enforce subscriber_status barring?
Labels: type:investigation, area:ratel-link, priority:p1, risk:high

**Week:** 2 (carried from Week 1) | **Target date:** 2026-10-12 | **Owner:** @CaptRaven | **Reviewer:** @Ukashatu40
**Week:** 2 (carried from Week 1) | **Target date:** TODO (by Oct 7) | **Owner:** @CaptRaven | **Reviewer:** @Ukashatu40
**Source:** Build Plan, Contract 1 "Deactivation is delete and rewrite, for now"; RatelLink spec "Data it keeps"; Week 1 RatelLink bullets.
**TODO confirm:** this was a Week 1 task. If the answer is already written down, link it and close this issue.

## Re-planned 2026-10-08
Not on the path to the first real-SIM attach: "delete and rewrite" works without it. Moved to Mon 2026-10-12 so the network lead can first unblock W2-02 (the Open5GS template) and W2-08.

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
