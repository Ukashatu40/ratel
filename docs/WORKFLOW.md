# How work flows: from a task to merged code

This is the one page to read first. It explains the whole path and who does what. The details live
in the documents it links to; this page does not repeat them.

## The picture

```
Build Plan  ->  Weekly gate  ->  Epic  ->  Issue  ->  Branch  ->  Pull request  ->  Review + CI  ->  Merge  ->  Done
 (the plan)     (pass/fail      (one      (one        (your         (your change,     (people and     (squash)   (docs and
                 test of the     workstream  piece of   copy of       explained)        robots check             runbook
                 week)           in a gate)  work)      the code)                       it)                      updated)
```

| Step | Who does it | What "finished" looks like |
| ---- | ----------- | -------------------------- |
| Weekly gate | Fixed by the Build Plan | A test that passes or fails, such as "a real SIM, created through RatelLink, attaches and browses" |
| Epic | Project lead | One GitHub issue per workstream per week that lists its child issues |
| Issue | Project lead writes it and assigns it | Meets the [Definition of Ready](DEFINITION_OF_READY.md) |
| Branch and code | The assignee | `make check` is green on your machine |
| Pull request | The assignee | Template filled in, "Closes #123" in it, reviewers requested |
| Review | Reviewers, chosen by CODEOWNERS | Approved, every comment answered |
| CI | GitHub, automatically | `ci-success`, `critical-review-gate` and `secret-scan` are green |
| Merge | The author or the project lead | Squash merge into `main`, branch deleted |
| Done | The assignee | The [Definition of Done](DEFINITION_OF_DONE.md) holds, including docs and a runbook note |

## The people and their jobs

| Role | Job in the flow |
| ---- | --------------- |
| **Project lead** | Writes and prioritises issues, assigns owners, decides architecture and contract questions, runs the weekly gate review. Nobody else assigns critical work. |
| **Assignee (owner)** | Does the issue: branch, code, tests, pull request, answers review comments, updates docs. Owns the change until it is merged. |
| **Reviewer** | Reads the change and either approves or asks for changes. Looks at correctness, tests, security and clarity, not only style. |
| **Independent reviewer** | A required approver on the two critical areas (RatelLink and RatelBSS: money). |
| **CI (GitHub Actions)** | Runs lint, types, tests, contract checks, secret scan and the two-reviewer gate on every pull request. A red check blocks the merge. |
| **Network team** | Owns RatelCore, RatelVoice, RatelOps and the radio. Software work that touches the network is shown working on the lab. |

Who reviews what is in [TEAM_STRUCTURE.md](TEAM_STRUCTURE.md) and `.github/CODEOWNERS`.

## Step by step

### 0. Once, when you join

Follow [TEAM_ONBOARDING.md](TEAM_ONBOARDING.md). In short: turn on two-factor authentication on GitHub, clone
the repository, run `make install` then `make check`, and do the practice pull request.

### 1. Pick up an issue

- Open the Project board (view **Delivery Board**). Work comes from the **Ready** column, assigned to you.
- Do not start work that is not assigned to you. Do not assign yourself to anything marked
  `risk:critical` (RatelLink, money, keys, identity data). Ask the project lead.
- Move your card to **In Progress** when you start.

### 2. Read the issue until it is clear

Every issue has an objective, scope, out of scope, dependencies, acceptance criteria and a testing
requirement. If anything is unclear or missing, **ask in the issue** (a comment, mentioning the project
lead). Asking on day one costs minutes. A wrong guess costs days. If the issue seems to need
something the Build Plan does not mention, stop and ask: nobody invents endpoints, fields or
product behavior.

### 3. Make a branch

```
git switch main
git pull
git switch -c feature/short-description     # prefix is one of: feature fix refactor chore docs security
```

One issue, one branch, one pull request. Never work on `main` directly: GitHub will refuse the push.

### 4. Do the work in small steps

- Put code in the layer it belongs to (api, services, domain, repositories, security). The rules are in the code organisation ADR (0008) and the layer folders each explain themselves in their `__init__.py`. A test fails if you import across layers the wrong way.
- Write the test first or with the code. A change without a test that would fail without it is not ready.
- Commit often with a message that says what and why: `feat: add line state transition table`.
- Run `make check` before every push. It is exactly what CI runs.
- Never commit secrets, keys, Ki, OPc, real customer data. Use `tests/synthetic.py`.

### 5. Open a pull request

```
git push -u origin feature/short-description
```

GitHub shows a link to open the pull request. Then:

- **Title:** `type: summary` in the imperative, for example `feat: add line state machine`. The title becomes the commit on `main`, and CI checks its format.
- **Description:** fill in the whole template. Say what you did **not** change. Write "Closes #123" (the issue number) so the issue closes by itself on merge.
- **Not finished but you want feedback early?** Open it as a **Draft**. Reviewers are not asked until you mark it ready.
- Reviewers are requested automatically from CODEOWNERS. Check the list on the right and add anyone missing.
- Move the card to **Review**.

### 6. CI runs

| Check | What it tells you |
| ----- | ----------------- |
| Lint and format | Code style (`make format` fixes most things) |
| Type check (mypy) | Type mistakes |
| Unit tests | Your tests and everyone's |
| Contract | `openapi.yaml` is valid and the code matches it |
| Config, workflows, links | YAML, Markdown links, shell scripts |
| PR title and branch name | Naming rules |
| `secret-scan` | A key or token was committed (history is scanned too) |
| `critical-review-gate` | RatelLink or money was touched: two approvals are required |
| `ci-success` | One check that is green only when all the others are |

Red means fix it. Open the failed job, read the first error, reproduce it locally with the same
command. Never disable a check or a test to get green.

### 7. Review

- A reviewer reads, asks questions, and approves or requests changes. Answer **every** comment:
  fix it, or explain why not. Resolve the conversation when it is settled.
- **A new push removes earlier approvals.** After you push fixes, tell the reviewer (re-request review).
- You never approve your own pull request. The project lead cannot either.
- RatelLink and RatelBSS: money need **two** approvals: the independent reviewer plus one more person.
  When you review one, say in your review which invariants you checked
  ([CODE_REVIEW_GUIDELINES.md](CODE_REVIEW_GUIDELINES.md)).
- Reviewing well is learned. Start with comments-only reviews and ask the mentor to read yours
  ([TEAM_ONBOARDING.md](TEAM_ONBOARDING.md)).

### 8. Merge

When CI is green, approvals are in, and conversations are resolved, press **Squash and merge**. It is
the only option GitHub offers. Delete the branch. The linked issue closes by itself and the card
moves to **Done**.

### 9. Finish properly

Done is more than merged: documentation and the runbook updated, and for network work the lab run
recorded in the pull request. See the [Definition of Done](DEFINITION_OF_DONE.md).

## Issues: how they are written and used

**Which form.** Create issues from the forms (New issue button): Feature / implementation task,
Bug report, Investigation / spike, Documentation task, Infrastructure, Security-sensitive task,
Refactor, Onboarding. They add the first label for you. A vulnerability is never an issue: use the
private channel in [SECURITY.md](../SECURITY.md).

**Size.** An issue is finished, reviewed and demonstrated in a few days at most. "Build RatelBSS" is
not an issue. "Implement the line state machine" is. If it is too big, split it
([TASK_MANAGEMENT.md](TASK_MANAGEMENT.md) shows how).

**Epics and child issues.** An epic is an issue that only lists other issues as a task list
(`- [ ] #12`). GitHub shows progress. The epic closes when its children do.

**Linking.** `Closes #12` in a pull request closes the issue on merge. `Relates to #12` only links.
Write "Blocked by #12" in the issue and set the card to **Blocked** with a comment saying why.

**Assignee versus owner text.** Use GitHub's **Assignee** field for the person doing the work. The
"Owner" line inside the issue text is a record for the project lead.

**Spikes.** An investigation has a timebox and a written answer. It produces no code to merge.

## Labels

Every issue carries one label from each family. Workflow state (Backlog, Ready, In Progress, Review,
Blocked, Done) is **not** a label: it is the Project's **Status** field.

| Family | Values | Who sets it | Meaning |
| ------ | ------ | ----------- | ------- |
| `type:` | `feature` `bug` `refactor` `security` `database` `infrastructure` `documentation` `investigation` `onboarding` | The form sets the first one | What kind of work |
| `area:` | `contracts` `ratel-link` `ratel-meter` `bss-lines` `bss-money` `ratel-desk` `ratel-pay` `network` `ops` `deployment` `repository` | The creator | Which part of the system. More than one is fine |
| `priority:` | `p0` blocks the weekly gate or the demo, `p1` needed this week, `p2` normal (default), `p3` low | Project lead | How soon. See [PRIORITY_RISK_FRAMEWORK.md](PRIORITY_RISK_FRAMEWORK.md) |
| `risk:` | `critical` keys, money, identity data, RatelLink, production. `high` hard to reverse. `medium` contained. `low` small and safe | Project lead | How careful. **Risk decides how many reviewers.** |
| `good first issue` | (GitHub standard) | Project lead | Small, clear, low risk: suitable for someone new |

Priority and risk are separate: a typo in RatelDesk is `p3` and `risk:low` even if the demo is close;
a quiet change to RatelLink logging is `p2` but `risk:critical`. Do not inflate risk.

Useful searches (paste into the Issues search box):

```
is:open label:"risk:critical"                     everything that needs two reviewers
is:open label:"priority:p0"                       what blocks the gate
is:open assignee:@me                            my work
is:open label:"area:ratel-link" label:"type:bug"    open RatelLink bugs
is:open no:assignee                             not picked up
```

## The Project board

Views: **Delivery Board** (columns by Status), **Roadmap** (by Target Date), **Team Workload** (who
has what) and **Risks / Blockers**. Fields: Priority, Risk, Workstream, Week, Type, Target Date, plus
Assignee and Reviewers.

| Status | Meaning | Who moves the card |
| ------ | ------- | ------------------ |
| Backlog | Known, not ready | Created here automatically |
| Ready | Meets the Definition of Ready, assigned | Project lead |
| In Progress | Someone is working on it | The assignee |
| Review | A pull request is open and waiting | The assignee |
| QA / Integration | Merged or nearly, waiting for a lab run or integration check | The assignee |
| Blocked | Cannot move. A comment says why and what unblocks it | Anyone, then tell the lead |
| Done | Merged and the Definition of Done holds | Automatic when the issue closes |

If a card has not moved in two days, say why in a comment. A blocked card nobody knows about is the
most expensive kind.

## Branches, commits, pull request titles

| Thing | Format | Example |
| ----- | ------ | ------- |
| Branch | `<type>/<short-description>`, lowercase with hyphens. Types: `feature` `fix` `refactor` `chore` `docs` `security` | `feature/line-state-machine` |
| Commit | `<type>: <what changed>`, imperative, about 72 characters. Types: `feat` `fix` `refactor` `test` `docs` `chore` `security` `infra` | `feat: add line state transition table` |
| Pull request title | Same as a commit. It becomes the commit on `main` | `feat: add line state machine` |

Details: [CONTRIBUTING.md](../CONTRIBUTING.md).

## The project lead's routine

This is how the flow is kept moving. It is also what to hand over if someone covers for you.

| When | What |
| ---- | ---- |
| **Friday before the week** | Draft next week's issues from the roadmap row and the Build Plan "Done when" lines. Not earlier: plans change when spikes answer questions. |
| **Monday** | Check each draft against the Definition of Ready and the "What not to build yet" list. Set priority and risk, assign owners, move to **Ready**. Make the epic. |
| **Every day** | Look at **Review** first: waiting pull requests cost the most. Look at **Blocked** second. Answer questions in issues. |
| **When a critical pull request opens** | Make sure both required reviewers know and have time. Agree a review slot so it does not wait. |
| **Friday, the gate** | Run the week's gate test. Review what slipped, update [RISK_REGISTER.md](RISK_REGISTER.md), tell management early if a gate is at risk. |

Reviews are the bottleneck of a small team. Agree two review windows a day (for example late
morning and late afternoon) so nobody waits more than half a day.

## Words you will hear

| Word | Meaning |
| ---- | ------- |
| Repository | The project folder and its history, on GitHub |
| Branch | Your private line of changes, separate from `main` |
| Commit | One saved set of changes with a message |
| Pull request (PR) | A request to merge your branch into `main`, with discussion and checks |
| Review | Another person reading your PR and approving or asking for changes |
| CI | Robots that run the checks on every PR |
| Merge, squash | Joining the branch into `main`. Squash turns all your commits into one |
| CODEOWNERS | A file saying who must review which folders |
| Draft PR | A PR not ready for review yet |
| Issue | One piece of work, or a bug, or a question to answer |
| Epic | An issue that lists other issues |
| Spike | A time-boxed investigation that ends in a written answer |
| Gate | The pass/fail test that ends a week |
| ADR | A short record of a design decision and why |
| Runbook | A short page saying how to tell a service is healthy and what to do when it is not |

## Where to read more

[CONTRIBUTING.md](../CONTRIBUTING.md) · [TASK_MANAGEMENT.md](TASK_MANAGEMENT.md) ·
[DEFINITION_OF_READY.md](DEFINITION_OF_READY.md) · [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) ·
[PRIORITY_RISK_FRAMEWORK.md](PRIORITY_RISK_FRAMEWORK.md) · [CODE_REVIEW_GUIDELINES.md](CODE_REVIEW_GUIDELINES.md) ·
[GITHUB_SETUP.md](GITHUB_SETUP.md) · [TEAM_STRUCTURE.md](TEAM_STRUCTURE.md)
