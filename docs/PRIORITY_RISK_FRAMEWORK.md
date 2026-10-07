# Priority and risk

## Priority (how soon)

| Label | Meaning |
| ----- | ------- |
| **P0** Critical | Blocks the current weekly gate or the demo, or a live security/data-integrity problem. Drop other work. |
| **P1** High | Needed this week for the gate, or a high-impact bug. |
| **P2** Normal | Planned work for its week. Default. |
| **P3** Low | Nice to have. Probably after the demo. |

## Risk (how careful)

| Label | Meaning | Review |
| ----- | ------- | ------ |
| **Critical** | Touches SIM keys, authentication/authorization, payments, wallet/ledger, customer identity data, production infrastructure, RatelLink, or sensitive network integration. | Two reviewers. Invariants verified in review. Security checklist. |
| **High** | High blast radius or hard to reverse: migrations on money tables, contract changes, RatelMeter counting, state machine changes. | One reviewer, plus the project lead is told. |
| **Medium** | Contained and reversible. Most application code. | One reviewer. |
| **Low** | Small and safe: copy, docs, tests, tooling. | One reviewer. |

Priority and risk are separate. A typo in RatelDesk is P3/Low even if the demo is soon. A quiet
change to RatelLink logging is P2 but Critical.

**Do not inflate.** A small UI change is not Critical because the screen is important. Critical is
reserved for the areas listed above. When unsure, ask the project lead, and write the reason in the issue.

GitHub labels: `priority:p0..p3`, `risk:critical|high|medium|low`. Project fields: Priority and Risk.
