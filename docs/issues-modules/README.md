# Module issues (drafts for the project lead to assign)

Written 2026-10-17. **Ten issues cover the whole demo**: one per module, one for the network team,
one for the project lead's own work, plus lab session 1 (already opened by hand). Each module issue
holds its deliverables in full (objective, scope, dependencies, pass/fail acceptance criteria), so
there is nothing else to open. **Owners, reviewers and dates are all `TODO`**: the project lead
assigns them. Nothing here is posted until the project lead runs the script.

Deliverables keep their `M-` numbers inside the issues so they can refer to one another
(for example "waits for M-12"). A deliverable that is not ready says so and says what it waits for.

How "ready" is judged: [DEFINITION_OF_READY.md](../DEFINITION_OF_READY.md). Review by risk:
[PRIORITY_RISK_FRAMEWORK.md](../PRIORITY_RISK_FRAMEWORK.md). For a single new task later, the issue
form is [module_deliverable.yml](../../.github/ISSUE_TEMPLATE/module_deliverable.yml).

## Posting

Read each file first. Run once; running again creates duplicates.

```
ISSUE_FILES="docs/issues-modules/I-*.md" scripts/github/create_issues.sh
```

`L-01-lab-session-1.md` is not matched, on purpose: that issue was opened by hand and is the live
copy. The script assigns an issue only when its file has `**Owner:** @login`; edit that line while
posting, or assign on GitHub afterwards. Put blocked deliverables in the project's Backlog column,
not Ready.

## The ten issues

| File | Issue | Where | Deliverables | Risk |
| ---- | ----- | ----- | ------------ | ---- |
| [I-01](I-01-ratel-link.md) | ratel_link | services | M-03 install on core-cp, M-04 readiness and expiry check, M-05 bar-or-delete answer, M-06 live changes | Critical |
| [I-02](I-02-meter-agent.md) | meter_agent | services | M-07 counter reader, M-08 API clients, M-09 service on core-up, M-10 call mode | High |
| [I-03](I-03-meter-api.md) | meter_api | services | M-01 ingest contract, M-11 ingest and store, M-12 usage, M-13 calls, M-28 reconciliation | High |
| [I-04](I-04-bss-lines.md) | bss_lines | services | M-02 BSS API contract, M-14 RatelLink client and sell flow, M-25 schema and stock, M-26 API for RatelDesk, M-32 line lifecycle | High |
| [I-05](I-05-bss-money.md) | bss_money | services | M-15 ledger and wallet, M-16 plans and rating function, M-17 rating job, M-18 vouchers, M-19 payment sandbox | Critical |
| [I-06](I-06-desk.md) | desk | web | M-20 sell-a-SIM screens, M-29 line page and reconciliation view | Medium |
| [I-07](I-07-pay.md) | pay | web | M-21 top-up page | Medium |
| [I-08](I-08-network-team.md) | network team | RatelCore, RatelVoice, RatelOps | One checklist of what the demo needs from the network team | High |
| [I-09](I-09-project-lead.md) | project lead | repository | M-22 CI, M-23 key backup owner, M-24 and M-30 reviews, M-27 bss-app deployment, M-31 demo readiness | High |
| [L-01](L-01-lab-session-1.md) | lab session 1 | lab | The Week 2 gate and the open lab questions | High |

## Assignment sheet (fill in; this is the project lead's decision)

| Issue | Owner | Backup | Reviewer(s) |
| ----- | ----- | ------ | ----------- |
| ratel_link | | | |
| meter_agent | | | |
| meter_api | | | |
| bss_lines | | | |
| bss_money | | | |
| desk | | | |
| pay | | | |

Update [OWNERSHIP_MATRIX.md](../OWNERSHIP_MATRIX.md) and `.github/CODEOWNERS` to match when you decide.
