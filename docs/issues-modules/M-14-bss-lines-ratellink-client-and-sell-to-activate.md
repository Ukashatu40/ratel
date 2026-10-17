# RatelBSS lines: the RatelLink client and the sell-to-activate flow
Labels: type:feature, area:bss-lines, priority:p1, risk:high

**Module:** RatelBSS lines | **Roadmap week:** 2 to 3 | **Owner:** TODO | **Reviewer:** TODO | **Target:** TODO
**Ready:** yes against the mock. The lab run is part of lab session 1, section F.
**Source:** Build Plan, RatelBSS: lines "Done when"; #27 (software part); `services/app/bss_lines/domain.py` (the state machine, merged in #46); DECISIONS_PENDING question 6.

## Objective
Selling a SIM and activating it produces exactly one `/activate` call on RatelLink, through the state machine and nowhere else.

## Scope
- RatelLink client (base URL, API key, `Idempotency-Key`) configured by environment: the mock locally, the lab RatelLink on the lab.
- Activation sends the plan's speeds and `voice` true as the contract says.
- Only the state machine calls RatelLink. Each transition has an audit entry (who, why).
- KYC must be verified before activation (Build Plan rule). Its fields: TODO(PRD).
- **Before building the failure path**, propose to the project lead what state a line keeps if RatelLink fails mid-transition (DECISIONS_PENDING question 6).

## Out of scope
Rating, `out_of_data` (M-17). Live changes. Screens (M-20).

## Depends on
The mock (current). RatelLink on the lab for the lab run (M-03).

## Contract impact
None, unless a `TODO(contract)` item is touched.

## Acceptance criteria
- [ ] The flow produces exactly one `/activate` call (test counts calls at the mock)
- [ ] A retry with the same `Idempotency-Key` has no second effect (test)
- [ ] RatelBSS's database holds no `ki` or `opc` (schema test); SIM import keeps ICCID, IMSI and batch only
- [ ] No code path other than the state machine changes a line's state (architecture or unit test)
- [ ] The lab run is recorded in lab session 1, section F

## Data, security and privacy
Customer and KYC data stay in RatelBSS. RatelLink API key from an owner-only environment file.

## Testing
Unit, contract (mock), integration (PostgreSQL). Lab: session 1.
