# Module issues (drafts for the project lead to assign)

Written 2026-10-16. One issue per deliverable inside one module, replacing the old
workstream-by-week lists. **Owners, reviewers and target dates are all `TODO`**: the project lead
assigns them (Definition of Ready: never self-assigned for critical areas). Nothing here is posted
until the project lead runs the script.

How an issue is written: [module_deliverable.yml](../../.github/ISSUE_TEMPLATE/module_deliverable.yml).
What "ready" means: [DEFINITION_OF_READY.md](../DEFINITION_OF_READY.md). Who reviews what, by
risk: [PRIORITY_RISK_FRAMEWORK.md](../PRIORITY_RISK_FRAMEWORK.md).

## Posting

Read each file first. Run once; running again creates duplicates.

```
ISSUE_FILES="docs/issues-modules/M-*.md" scripts/github/create_issues.sh
```

Post a subset by listing the files (`ISSUE_FILES="docs/issues-modules/M-04-*.md docs/issues-modules/M-14-*.md"`).
The script assigns an issue only when its file has `**Owner:** @login`; edit that line to assign
while posting, or assign on GitHub afterwards.

## The list

"Ready" follows the Definition of Ready. Review is the number of approvals the risk needs.
"Lab" means the work is complete only after a lab run (see the lab-session issue).

| Id | Module | Deliverable | Risk | Review | Ready | Waits for | Lab |
| -- | ------ | ----------- | ---- | ------ | ----- | --------- | --- |
| M-01 | Contracts | Agent ingest call | High | 1 | No | Decision on the call's shape | No |
| M-02 | Contracts | BSS API for RatelDesk and RatelPay | High | 1 | No | PRD | No |
| M-03 | RatelLink | Install on core-cp, prove the runbook | Critical | 2 | No | N3, N9, N2, N1 (network team) | Yes |
| M-04 | RatelLink | Readiness check, scheduled expiry check | Critical | 2 | Yes | Nothing | Confirm in M-03 |
| M-05 | RatelLink | Apply the bar-or-delete and re-activation answer | Critical | 2 | No | Lab session 1, B | Yes |
| M-06 | RatelLink | Live changes (detach and re-attach) | Critical | 2 | No, do not start | Lab session 1, C; decision 57 | Yes |
| M-07 | RatelMeter agent | Real counter reader | High | 1 | Partly | Lab session 1, D | Yes |
| M-08 | RatelMeter agent | Assignments client and ingest poster | High | 1 | Partly | M-01 for the poster | No |
| M-09 | RatelMeter agent | Entry point, service, runbook on core-up | High | 1 | No | M-07, M-08 | Yes |
| M-10 | RatelMeter agent | Call mode | High | 1 | No, do not start | #26 | Yes |
| M-11 | RatelMeter API | Ingest endpoint and record store | High | 1 | No | M-01 | No |
| M-12 | RatelMeter API | `GET /v1/usage` | High | 1 | No | M-11 | Yes (1% check) |
| M-13 | RatelMeter API | Call records and `GET /v1/calls` | High | 1 | No, do not start | #26 | No |
| M-14 | RatelBSS lines | RatelLink client and sell-to-activate | High | 1 | Yes (mock) | Nothing for the mock | Yes |
| M-15 | RatelBSS money | Ledger and wallet | Critical | 2 | Partly | PRD for entry types | No |
| M-16 | RatelBSS money | Plans, bundles, rating function | Critical | 2 | No | PRD | No |
| M-17 | RatelBSS money | Rating job and out-of-data trigger | Critical | 2 | No | M-12, M-14, M-15, M-16 | Yes |
| M-18 | RatelBSS money | Vouchers redeem once | Critical | 2 | No | M-15, PRD | No |
| M-19 | RatelBSS money | Payment gateway in the sandbox | Critical | 2 | No, do not start | M-15, M-18 | No |
| M-20 | RatelDesk | Scaffold and sell-a-SIM screens | Medium | 1 | No | M-02, PRD, web stack ADR | No |
| M-21 | RatelPay | Top-up page | Medium | 1 | No | M-02, M-18, PRD | No |
| M-22 | Repository | MongoDB integration job in CI | High | 1 | Yes (project lead approves CI change) | Nothing | No |
| M-23 | Repository | Key file backup owner (R-14) | Critical | project lead | Yes | The project lead | No |
| M-24 | Repository | Independent review of the key code | Critical | 2 | No, Week 6 | Time | No |

Network-team work is not listed as module issues: it is [L-01](L-01-lab-session-1.md) (the lab
session, absorbing #21, #22, #23, #24, #25 and #27), #26 (call records) and the requests to the
network lead. `ISSUE_FILES="docs/issues-modules/L-01-*.md"` posts the lab-session issue alone.

## Assignment sheet (fill in; this is the project lead's decision)

Copy into an issue or a spreadsheet. The Owner and Reviewer columns are deliberately empty.

| Module | Issues | Owner | Backup | Reviewer(s) |
| ------ | ------ | ----- | ------ | ----------- |
| Contracts | M-01, M-02 | | | |
| RatelLink | M-03 to M-06 | | | |
| RatelMeter agent | M-07 to M-10 | | | |
| RatelMeter API | M-11 to M-13 | | | |
| RatelBSS lines | M-14 | | | |
| RatelBSS money | M-15 to M-19 | | | |
| RatelDesk | M-20 | | | |
| RatelPay | M-21 | | | |
| Repository, CI and docs | M-22 to M-24 | | | |

Update [OWNERSHIP_MATRIX.md](../OWNERSHIP_MATRIX.md) and `.github/CODEOWNERS` to match when you decide.
