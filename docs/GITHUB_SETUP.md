# GitHub setup

What the repository files define, what has been applied, and how to apply the rest.

**Status when this scaffold was created (Oct 6, 2026): nothing below has been applied to GitHub.**
The setup was done without GitHub credentials, so no ruleset, label, project, issue or setting was
created. Everything is prepared as files and scripts. The scripts were syntax-checked and
shellchecked, not run.

## Files and what they do

| File | Purpose | Applied? |
| ---- | ------- | -------- |
| `.github/workflows/ci.yml` | lint, types, tests, contract, config checks, PR title/branch check, aggregate `ci-success` | Runs once pushed |
| `.github/workflows/security.yml` | `secret-scan` (gitleaks, pinned and checksum-verified), dependency audits | Runs once pushed |
| `.github/workflows/critical-review-gate.yml` | Two approvals on RatelLink and BSS money paths | Runs once pushed |
| `.github/CODEOWNERS` | Review routing. **All rules commented out (TODO usernames)** | Needs your usernames |
| `.github/critical-paths.txt`, `critical-reviewers.txt` | Paths needing two reviewers; named required reviewers | Needs usernames in the second |
| `.github/rulesets/main-protection.json` | Branch rules for `main` | Apply with `scripts/github/apply_ruleset.sh` |
| `.github/labels.yml` | Label taxonomy | Apply with `scripts/github/setup_labels.sh` |
| `.github/ISSUE_TEMPLATE/*`, `pull_request_template.md` | Templates | Active once pushed to the default branch |
| `.github/dependabot.yml` | Weekly dependency PRs | Active once pushed |

## Order of operations

1. **Create the repository** (private) and push the initial commit to `main` *before* turning on branch rules, because the ruleset blocks direct pushes. If the repository already has history, open the setup as a PR instead and reconcile any files that conflict.
2. **Let CI run once** (open any PR or push to `main`) so the required checks exist: `ci-success`, `critical-review-gate`, `secret-scan`.
3. **Fill in usernames:** `.github/CODEOWNERS` (uncomment rules), `.github/critical-reviewers.txt`. Everyone listed needs write access.
4. `gh auth login` as a repository admin, then:
   ```
   scripts/github/setup_labels.sh
   scripts/github/apply_ruleset.sh
   ```
5. **Repository settings** (web UI, no script): Settings, General, Pull Requests: allow **squash merging only**; "Automatically delete head branches" on. Settings, Code security: enable private vulnerability reporting, Dependabot alerts, secret scanning and push protection if your plan offers them. Settings, Actions, General: restrict to actions you trust and set default workflow permissions to read-only.
6. **Project:** see below.
7. **Seed issues:** after the project lead reviews `docs/issues-week2/`, run `scripts/github/create_issues.sh`.

## What the ruleset enforces

`main-protection` (target: default branch, no bypass actors): blocks deletion and force pushes;
requires linear history; requires a pull request with **1 approval**, code-owner review, approval of
the latest push by someone other than the pusher, stale approvals dismissed on push, review
conversations resolved, **squash merge only**; requires status checks `ci-success`,
`critical-review-gate`, `secret-scan` with the branch up to date.

Not in the ruleset because GitHub cannot express it: "2 reviewers for these paths". That is the
`critical-review-gate` workflow, see [ADR 0004](adr/0004-two-reviewer-enforcement.md).

**Caveats to verify on the first real PR** (I could not test against live GitHub):

- The gate re-runs on `pull_request_review` events. Confirm the `critical-review-gate` check turns green on the PR after the second approval without a re-push. If it does not, re-run the job from the Actions tab and tell the project lead; the fallback is temporarily requiring 2 approvals on every PR.
- The ruleset has **no bypass actors**: not even admins can merge around it. Decide whether you want an emergency bypass for the project lead (TODO, see [DECISIONS_PENDING.md](DECISIONS_PENDING.md)).
- Rulesets on **private** repositories need a paid GitHub plan. On a free private repo, branch protection is not available at all.

### Fallback: classic branch protection

If rulesets are not available but classic branch protection is:

```
gh api -X PUT repos/OWNER/REPO/branches/main/protection --input .github/rulesets/classic-branch-protection.json
```

(also set squash-only merging in repository settings; classic protection cannot).

## GitHub Project

Create with `scripts/github/create_project.sh <owner>` (needs `gh auth refresh -s project`). It
creates the project and the fields Priority, Risk, Workstream, Week, Type and Target Date.
Assignee and Reviewers are built in. **The `gh` CLI cannot do two things, so do them by hand:**

1. **Status options.** Project settings, Status field: set the options to Backlog, Ready, In Progress, Review, QA / Integration, Blocked, Done.
2. **Views.** Create four views:
   - **Delivery Board**: layout Board, group by Status, filter `-status:Done` (or show Done collapsed), card fields Priority, Risk, Workstream, Assignee.
   - **Roadmap**: layout Roadmap, date field Target Date, group by Workstream, zoom to weeks.
   - **Team Workload**: layout Table, group by Assignee, filter `-status:Done`, show Priority, Week, Status.
   - **Risks / Blockers**: layout Table, filter `status:Blocked OR risk:Critical OR priority:P0`, sort by Priority.
3. Turn on the built-in workflows (Project, Workflows): item added to project sets Status to Backlog; item closed sets Status to Done.
4. Add the repository's issues to the project (project settings, or `gh project item-add`).

## Branch naming and PR titles

Enforced by the `pr-hygiene` CI job (see `CONTRIBUTING.md`). Dependabot PRs are exempt.

## Manual checklist after applying

- [ ] Open a trivial docs PR: CI runs, `ci-success` and `secret-scan` appear, direct push to `main` is refused.
- [ ] A PR touching `services/ratel_link/` shows `critical-review-gate` failing until two others approve.
- [ ] CODEOWNERS shows "owners" on a changed file in the PR UI (no "unknown owner" warnings).
- [ ] Merge button offers squash only.
