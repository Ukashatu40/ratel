# Spike: live changes, written up by the end of Week 2
Labels: type:investigation, area:ratel-link, priority:p1, risk:high

**Week:** 2 | **Target date:** Oct 9 | **Owner:** @CaptRaven | **Reviewer:** @Ukashatu40
**Source:** Build Plan, RatelLink spec "Live changes" (PRD CHG-6, P1).

## Objective
Decide, in writing, whether live changes (slow or cut a connected line) are small enough to build in Week 5, or whether "changes at next attach" is the plan for the demo.

## Questions (answer each against Open5GS v2.8.0)
1. When RatelLink changes a subscriber document, does the HSS tell the MME, with Insert Subscriber Data or Cancel Location? If it does, much of this already exists.
2. Can the PCRF push a new policy, such as a lower speed, to a live session over Gx? If not, is a small patch or an Rx client the simpler route?
3. Can we force a detach for a single IMSI, so the phone reattaches and picks up its new record? A detach also ends its registration for calls.

## Method
Lab core, test subscriber and phone or simulator. Measure. Timebox the whole spike to what Week 2 allows; start from RatelLink's spec.

## Target to judge against
A line moved to `out_of_data` mid-session is slowed within **60 seconds**; a suspended line loses internet and calls within **60 seconds**.

## Deliverable
A write-up in `docs/` answering all three questions, a recommendation (build in Week 5, or fallback), and, if the fallback, the exact wording customer care needs ("changes apply at the next attach"). **No production code.** Update `docs/RISK_REGISTER.md` R-05.

## Out of scope
Any live-change implementation. The Build Plan says guessing means writing it twice.

## Suggested skill level
Strong Linux and telecom core debugging (Diameter, Gx, Open5GS internals). The network team should be consulted.
Reviewer: one, plus the project lead reads the recommendation.
