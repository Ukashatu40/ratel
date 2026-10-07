# Task management

## From the Build Plan to merged code

```
Build Plan
 -> Weekly Gate
  -> Epic
   -> Issue
    -> Branch
     -> PR
      -> Review
       -> CI
        -> QA / Integration
         -> Merge
          -> Documentation / Runbook
           -> Done
```

| Level | What it is | Example |
| ----- | ---------- | ------- |
| Build Plan | The plan of record. | "RatelBSS: lines" component spec |
| Weekly gate | The pass/fail test that ends the week. | Week 2: a real SIM, created through RatelLink, attaches, browses and registers for calls |
| Epic | One workstream's contribution to a gate. A GitHub issue that links its child issues. | "RatelLink complete against the lab" |
| Issue | One deliverable-sized piece of work. Meets [DEFINITION_OF_READY.md](DEFINITION_OF_READY.md). | "Implement RatelLink activate endpoint" |
| Branch, PR | One issue, one branch, one PR. | `feature/link-activate` |
| Review, CI | One reviewer, or two for RatelLink and RatelBSS: money. | |
| QA / Integration | Lab run for network work; contract and integration tests. | |
| Done | [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) satisfied, including runbook. | |

## Split work into deliverable-sized issues

An issue can be finished, reviewed and demonstrated in a few days at most. If it cannot, split it.

Avoid: "Build RatelBSS." "Do the usage thing." "Security."

Prefer, for RatelBSS: lines:

- Implement Line state machine (transition table, refusal of every other transition, audit entry)
- Implement SIM inventory (states `in_stock`, `in_use`, `retired`; no contradictory allocation)
- Implement number stock and MSISDN assignment (states `available`, `in_use`, `quarantined`)
- Implement customer and KYC status
- Implement RatelLink client for `/activate`, `/data`, `/deactivate` with `Idempotency-Key`
- Implement RatelLink activation integration (sell-to-activate produces exactly one `/activate`)
- Implement line search by MSISDN, ICCID or IMSI

Rules of thumb: one state machine, one table, one endpoint, one integration, or one screen per
issue. Separate "write the code" from "prove it against the lab" only if the lab run depends on
someone else; otherwise the lab run is in the same issue's acceptance criteria.

## Backlog generation strategy

Do not write the full backlog up front. Plans change as spikes answer questions.

1. **Each Monday**, read the week's row in [ROADMAP.md](ROADMAP.md) and the matching Build Plan component specs.
2. For each workstream's bullet, write the **"Done when"** lines from the Build Plan as the epic's acceptance criteria.
3. Split the epic into issues by the rule above. Each issue cites its Build Plan section.
4. Check each against "What not to build yet". Delete what is not needed for the gate.
5. Mark dependencies, especially on other teams (SIM keys, ims APN, call record fields) and on contract `TODO(contract)` items.
6. Set priority and risk ([PRIORITY_RISK_FRAMEWORK.md](PRIORITY_RISK_FRAMEWORK.md)). Critical-risk issues get two reviewers.
7. The project lead assigns owners and reviewers. Nobody self-assigns critical areas.
8. Move issues to **Ready** only when they meet the Definition of Ready.
9. At the gate, review what slipped, update the [RISK_REGISTER.md](RISK_REGISTER.md), and generate next week's issues. Draft the next week's issues no earlier than the Friday before; two weeks ahead is too far.

## GitHub Project

"RatelPlus Subscriber Platform". Views: Delivery Board, Roadmap, Team Workload, Risks / Blockers.
Status: Backlog, Ready, In Progress, Review, QA / Integration, Blocked, Done. Fields: Priority
(P0 to P3), Risk (Critical to Low), Workstream, Assignee, Reviewer, Week, Target Date, Type.
Workflow state lives in the Status field, not in labels. Setup: [GITHUB_SETUP.md](GITHUB_SETUP.md).

## Week 2 seed

The most immediate issues, derived strictly from the Build Plan's Week 2 objectives, are in
[issues-week2/](issues-week2/). Owners are not assigned. `scripts/github/create_issues.sh` creates
them on GitHub after review by the project lead.
