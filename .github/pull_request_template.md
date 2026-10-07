<!-- Fill this in honestly. Reviewers will ask you to explain anything you leave blank.
     Do NOT paste secrets, Ki/OPc, NINs, real customer data, or sensitive production logs. -->

## What changed?

## Why?

## Issue / task
Closes #

## What was intentionally not changed?

## How was it tested?
<!-- Commands run, tests added, lab run if the network is touched (include date and what you saw). -->

## Impact

- **API / contract changes:** none / yes (describe; `contracts/openapi.yaml` updated in this PR)
- **Database changes:** none / yes (migration name, rollback plan)
- **Security implications:** none / yes (describe)
- **Privacy implications:** none / yes (what personal data is read, stored, logged or exposed)
- **Data-integrity implications:** none / yes (idempotency, replay, state machine, ledger, kobo)
- **Operational / deployment implications:** none / yes (config, env vars, runbook, restart order)
- **Migration or rollback concerns:** none / yes

## Author checklist

**Code quality**
- [ ] I can explain every line of this change, including any AI-generated code
- [ ] No unrelated changes, no dead code, no new dependency without a reason

**Testing**
- [ ] Tests added or updated, and they pass locally (`make check`)
- [ ] Failure paths are tested, not only the happy path
- [ ] If this touches the network: shown working against the **lab**, not only in unit tests

**Data integrity**
- [ ] State changes go through the state machine; changes that move money or usage are idempotent
- [ ] Money is whole kobo (int); time is UTC (epoch seconds on the wire)

**Security and privacy**
- [ ] No secrets, keys, tokens or real customer data in code, tests, fixtures, logs or this PR
- [ ] Ki and OPc are not logged, returned, or sent to RatelBSS
- [ ] Inputs validated; access control checked; errors do not leak internals

**API / contract**
- [ ] If API behavior changed, `contracts/openapi.yaml` and `contracts/not_implemented.txt` changed in this PR

**Documentation and observability**
- [ ] Docs / runbook updated where behavior or operations changed
- [ ] Structured log events added for meaningful state changes (no sensitive fields)

**Migration safety**
- [ ] Migration is reversible or the rollback plan is written above; no manual schema changes in production

**Review**
- [ ] Reviewers requested. RatelLink and RatelBSS: money changes need **two** approvals
