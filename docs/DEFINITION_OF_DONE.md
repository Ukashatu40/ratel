# Definition of Done

A task is not done until **all** of these are true. Start from the Build Plan's list, made practical.

1. Acceptance criteria in the issue pass.
2. Required tests pass (unit, contract, and others the issue names), including failure paths.
3. CI is green.
4. Required reviewers approved: one reviewer, or **two** for RatelLink and RatelBSS: money. [Build Plan: merged through review with CI passing]
5. If API behavior changed, `contracts/openapi.yaml` changed in the same commit (and `contracts/not_implemented.txt` is current). [Build Plan]
6. If it touches the network, it has been **shown working against the lab core**, not only in unit tests. The PR says what was run and when. [Build Plan]
7. If it runs in production, it has a short runbook note covering how to tell it is healthy and what to do when it isn't. [Build Plan] Template: [runbooks/TEMPLATE.md](runbooks/TEMPLATE.md).
8. Documentation updated where behavior, operations or architecture changed. Architectural decisions have an ADR.
9. Migrations are reviewed and have a rollback plan.
10. No known critical security, privacy or data-integrity issue remains open. If one is found, it is fixed or recorded in [RISK_REGISTER.md](RISK_REGISTER.md) with an owner before merge.
11. The weekly gate test the work serves is not made harder to pass (see [ROADMAP.md](ROADMAP.md)).

"It works on my machine" and "tests pass" are not done. Merged is not done until the lab check (6) and the runbook (7) are satisfied where they apply.
