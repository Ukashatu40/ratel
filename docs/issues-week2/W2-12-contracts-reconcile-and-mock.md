# Contracts: reconcile with the merged contract, close TODOs, keep the mock current
Labels: type:documentation, area:contracts, priority:p1, risk:high

**Week:** 2 | **Target date:** 2026-10-09 for the items W2-01 and W2-02 need; the rest 2026-10-13 | **Owner:** @Ukashatu40 | **Reviewer:** @CaptRaven (controlled review: project lead, network lead consulted)
**Source:** Build Plan, "The two contracts to freeze on day one", week one gate ("`openapi.yaml` is merged"), "Where a spec and a contract disagree, the contract wins".
**TODO confirm:** whether a contract was merged in Week 1. `contracts/openapi.yaml` in this repository is a draft created at setup from the Build Plan text. Reconcile with whatever was merged; the merged one wins, do not keep two.

## Objective
One contract, with every `TODO(contract)` resolved by the people who own the answer, and a mock that BSS and frontend developers rely on.

## Status 2026-10-14 (contract clean-up pull request)
Settled and removed from the contract: the `amf` question (a constant the core's document holds, not a request field), the MSISDN form (N6, decided 2026-10-13) and the Ki/OPc width (the core stores 32 hex characters; whether the SIM supplier delivers that form is risk R-01, not a contract question). Every RatelLink operation now documents the statuses it really returns (409 on `/data`, 503 on `/sims` and `/activate`), and the mock serves realistic examples (a line, an assignment, and each error) instead of `"string"`. Checked by starting the mock and calling every operation: valid requests get the example, and invalid ones (bad number, speeds missing, reason too long) are rejected by the mock exactly as RatelLink rejects them.

**Remaining `TODO(contract)` items.** What is built is described in the contract; each row needs the named owner's yes or a change. Dates are proposals, not agreements.

| # | Item | Built as | Proposal | Owner | Proposed date |
| - | ---- | -------- | -------- | ----- | ------------- |
| 1 | Body of a successful POST | `{}` | Keep `{}` | RatelBSS lines (@Abbalolo) | 2026-10-16 |
| 2 | 422 versus 400 for validation failures | 422 everywhere | Keep 422 | RatelBSS lines (@Abbalolo) | 2026-10-16 |
| 3 | `Idempotency-Key` format, length, retention | Accepted, must be non-empty, not stored; every operation is idempotent by construction | Say so in the contract (done) and ask BSS to send a UUID per intent and keep the body identical on a retry. Note the old wording "returns the first result" is not literally true when the body changes | RatelBSS lines (@Abbalolo) with the project lead | 2026-10-16 |
| 4 | `reason` values on deactivate | Free text, 1 to 200 characters, audit log only | Keep free text unless BSS wants codes | RatelBSS lines (@Abbalolo) | 2026-10-16 |
| 5 | Fields and `apns` shape of `GET /v1/lines/{imsi}` | status, msisdn, apns (names), ue_ip, speeds | Keep. Agree before W2-11 reads it | RatelBSS lines (@Abbalolo) | 2026-10-16 |
| 6 | Assignments wrapper and field names | `{"assignments": [{"ue_ip", "imsi"}]}`, includes addresses held for 24 hours | Keep. The agent's owner must read it before W2-09 | RatelMeter agent owner (TODO, see OWNERSHIP_MATRIX) | 2026-10-17 |
| 7 | `from` and `to` meaning and the field they filter on | Not built | Half-open `[from, to)` on `period_start` (usage) and `started_at` (calls) is the least surprising; not decided | RatelMeter API (@ml-lawarn) | 2026-10-20 |
| 8 | `end_reason` values | Not built | Wait for N7 (where call records come from) | RatelMeter API (@ml-lawarn) with the network team | After N7 |
| 9 | Cursor parameter name | Not built | `cursor` | RatelMeter API (@ml-lawarn) | 2026-10-20 |
| 10 | Real base URLs and ports per environment | Mock only | Fill in when core-cp and bss-app addresses are shared privately (they stay out of this public file) | Project lead | When N3 is answered |
| 11 | Where the ingest call and BSS's own API live | Not in either contract | DECISIONS_PENDING question 4 | Project lead | 2026-10-20 |
| 12 | Maximum speed (10 Gbit/s) and speeds required for `full` and `slow` | Built and fuzzed | Project lead to confirm (DECISIONS_PENDING items 42 and 43) | Project lead | 2026-10-16 |

## Scope
- Reconcile this draft with the Week 1 merged contract (if different).
- Resolve open items with RatelLink and RatelMeter owners: POST response bodies; `ki`, `opc`, `amf`, `msisdn` formats; speeds integer or decimal; `reason` values; `from`/`to` semantics; cursor parameter name; `apns` shape; assignments response shape; `Idempotency-Key` format; 422 versus 400. (The `Authorization` header format is decided: `Bearer`, ADR 0007.)
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
