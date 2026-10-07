# RatelBSS lines: run the line flow against the real RatelLink
Labels: type:feature, area:bss-lines, priority:p1, risk:high

**Week:** 2 | **Target date:** TODO (by Oct 9) | **Owner:** TODO | **Reviewer:** TODO
**Source:** Build Plan, RatelBSS: lines spec "Done when"; week one "line flow ... against a mock of RatelLink"; week two "RatelBSS's line flow calling the real RatelLink".
**TODO confirm:** whether the Week 1 line flow against the mock (customer, SIM, number, plan, activate) exists. If not, it is a prerequisite.

## Objective
The sell-to-activate flow runs against the real RatelLink on the lab and produces **exactly one** `/activate` call.

## Scope
- RatelLink client (base URL, API key, `Idempotency-Key`) configured by environment: mock locally, lab RatelLink on the lab.
- Activation sends the plan's speeds and `voice` true, per the contract.
- Only the state machine calls RatelLink; no other code path does.
- Verify with `GET /v1/lines/{imsi}` that BSS's view matches the network's after activation.

## Out of scope
Rating and `out_of_data` (Week 4). Live changes. Suspension flows beyond what exists. Frontend screens.

## Dependencies
W2-02 and W2-03 on the lab (or contract-compatible). W2-12 for the mock. KYC must be verified before activation (Build Plan rule). `TODO(contract)` items the client touches. **Open question:** what state a line keeps if RatelLink fails mid-transition is not specified (docs/DECISIONS_PENDING.md, question 6): propose to the project lead before building the failure path.

## Acceptance criteria
- The flow produces exactly one `/activate` call (test counts calls at the mock and on the lab).
- A retry of the same activation is idempotent (same `Idempotency-Key`, no second effect).
- RatelBSS's database holds no `ki` or `opc` anywhere (schema test; SIM import keeps ICCID, IMSI and batch only).
- State changes happen only through the state machine, each with an audit entry; every transition not in the table is refused (tests; confirm they exist from Week 1).
- Runs against the lab RatelLink once, recorded in the PR.

## Data / integrity requirements
State machine only; audit entry with who and why; no direct state column updates; money not involved yet.

## Security / privacy requirements
Customer and KYC data stays in BSS. The RatelLink API key comes from an owner-only env file.

## Testing requirements
Unit, contract (mock), integration (local PostgreSQL), **lab** (required).

## Suggested skill level
Application backend: FastAPI, SQLAlchemy, state machines, API clients.
