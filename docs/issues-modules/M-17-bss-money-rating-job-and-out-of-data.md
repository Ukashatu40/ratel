# RatelBSS money: the rating job and the out-of-data trigger
Labels: type:feature, area:bss-money, priority:p1, risk:critical

**Module:** RatelBSS money | **Roadmap week:** 4 | **Owner:** TODO | **Reviewer:** TODO (two required, critical) | **Target:** TODO
**Ready:** no, waits for M-12, M-15, M-16 and M-14
**Source:** Roadmap Week 4 gate (the full prepaid loop); `docs/DEMO_SCRIPT.md` act 4.

## Objective
When a line's allowance reaches zero, the job moves it to out of data through the state machine and RatelLink slows or cuts data while calls keep working.

## Scope
- A job every 300 seconds reading usage (M-12), rating it (M-16), writing ledger entries (M-15).
- At zero: the state machine transition, then `POST /v1/lines/{imsi}/data` through the RatelLink client (M-14).
- Reversal when data is restored (top-up), with `data` full.
- Changes reach the phone at its next attach until live changes exist (M-06): say so in the runbook.

## Out of scope
Real-time online charging. A faster loop for the demo (a deviation the project lead approves).

## Depends on
M-12, M-14, M-15, M-16. Lab for the end-to-end run.

## Contract impact
None expected.

## Acceptance criteria
- [ ] A crash mid-run rates nothing twice and loses nothing (test)
- [ ] A line at zero is moved once, however many times the job runs (idempotent)
- [ ] Voice is untouched by the data change (test at the RatelLink client boundary)
- [ ] On the lab, a line used past zero is slowed or cut and a call still works after an airplane-mode toggle

## Data, security and privacy
Money in kobo, ledger append-only, no IMSI in operational logs.

## Testing
Unit, failure-path, integration, lab.
