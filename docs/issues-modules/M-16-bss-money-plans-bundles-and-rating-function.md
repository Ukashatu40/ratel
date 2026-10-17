# RatelBSS money: plans, bundles and the rating function
Labels: type:feature, area:bss-money, priority:p1, risk:critical

**Module:** RatelBSS money | **Roadmap week:** 3 | **Owner:** TODO | **Reviewer:** TODO (two required, critical) | **Target:** TODO
**Ready:** no, waits for the PRD (the plan model, allowances, prices)
**Source:** Roadmap Week 3 ("plans and bundles; rating logic tested on synthetic records"); Build Plan, RatelBSS: money; `TODO(PRD)`.

## Objective
A pure function turns a line's usage records and its plan into an allowance remaining and a decision (stay, slow, cut), tested on synthetic records.

## Scope
Plan and bundle model, and the rating function with no database and no clock inside it. All product numbers: TODO(PRD). Do not invent plan names, prices or speeds.

## Out of scope
The job that runs it (M-17), charging for calls, postpaid and credit limits.

## Depends on
PRD. M-12 for the usage shape (the function can use the contract's shape now).

## Contract impact
None for the pure function.

## Acceptance criteria
- [ ] Table-driven tests on synthetic records, including exactly-zero, one byte over, and several bundles
- [ ] Money in whole kobo, no float; bytes are integers
- [ ] Replaying the same records gives the same result (idempotent)
- [ ] The function never raises on an empty or unsorted input

## Data, security and privacy
Synthetic data only.

## Testing
Unit.
