# Contracts: reconcile with the merged contract, close TODOs, keep the mock current
Labels: type:documentation, area:contracts, priority:p1, risk:high

**Week:** 2 | **Target date:** TODO (by Oct 8) | **Owner:** TODO | **Reviewer:** TODO (controlled review: project lead, network lead consulted)
**Source:** Build Plan, "The two contracts to freeze on day one", week one gate ("`openapi.yaml` is merged"), "Where a spec and a contract disagree, the contract wins".
**TODO confirm:** whether a contract was merged in Week 1. `contracts/openapi.yaml` in this repository is a draft created at setup from the Build Plan text. Reconcile with whatever was merged; the merged one wins, do not keep two.

## Objective
One contract, with every `TODO(contract)` resolved by the people who own the answer, and a mock that BSS and frontend developers rely on.

## Scope
- Reconcile this draft with the Week 1 merged contract (if different).
- Resolve open items with RatelLink and RatelMeter owners: POST response bodies; `ki`, `opc`, `amf`, `msisdn` formats; speeds integer or decimal; `reason` values; `from`/`to` semantics; cursor parameter name; `apns` shape; assignments response shape; `Idempotency-Key` format; `Authorization` header format; 422 versus 400.
- Decide where the agent's ingest call to the RatelMeter API and RatelBSS's own API (for RatelDesk and RatelPay) are specified (docs/DECISIONS_PENDING.md, question 4).
- Keep the mock (`make mock`) in step; confirm BSS developers use it.
- Update code and contract in the **same commit** whenever a decision touches an implemented operation.

## Out of scope
New endpoints not in the Build Plan or PRD.

## Acceptance criteria
- `grep -c "TODO(contract)" contracts/openapi.yaml` goes down; remaining ones each have an owner and a date in the issue.
- `make contract` is green.
- The mock serves examples that match the agreed shapes.
- The network lead has reviewed the parts that touch RatelCore or RatelVoice.

## Suggested skill level
API design, attention to detail, comfortable negotiating with both teams.
