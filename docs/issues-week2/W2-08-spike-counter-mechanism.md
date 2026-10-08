# Spike: per-line byte counter mechanism on core-up
Labels: type:investigation, area:ratel-meter, priority:p1, risk:high

**Week:** 2 | **Target date:** 2026-10-12 | **Owner:** @CaptRaven | **Reviewer:** @Ukashatu40
**Source:** Build Plan, Week 1 RatelMeter bullets ("Spike the counter mechanism ..."), RatelMeter spec "How data works".
**TODO confirm:** a Week 1 item. If already done, link the write-up and close.

## Re-planned 2026-10-08
Still needed before the agent can read real counters (W2-09), but not before W2-14 and W2-15, which are pure logic. Moved to 2026-10-12.

## Objective
Choose the counter mechanism that loses no bytes under thousands of short flows, by measuring.

## Options to measure
nftables per-element counters, per-line accounting rules, or conntrack accounting, on core-up's `ogstun` interface. Packets from a phone's address count as upload, packets to it as download.

## Method
Generate many short flows plus a long transfer against the lab data path; compare each mechanism's totals with the interface's own byte counters. If the old emulator VM still exists, test with it; if not, build against recorded counter snapshots and run the accuracy check on the first real traffic.

## Deliverable
Write-up with numbers and the chosen mechanism. Target: totals within **1%** of the interface counters. Update `docs/RISK_REGISTER.md` R-03.

## Out of scope
The agent itself (W2-09).

## Suggested skill level
Strong Linux networking (nftables, conntrack). Reviewer: one.
