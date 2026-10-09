# GitHub setup

What the repository files define, what has been applied, and how to apply the rest.

**Status checked against GitHub on 2026-10-08** (read-only; the project lead applied the setup on
Oct 7):

| Item | State |
| ---- | ----- |
| Repository | `Ukashatu40/ratel`, **public** (see "Repository visibility" below) |
| Collaborators | All six people have write access; @Ukashatu40 is admin |
| Ruleset `main-protection` | Applied, active, no bypass actors. Squash only, 1 approval, code-owner review, last-push approval, conversations resolved, linear history, required checks `ci-success`, `critical-review-gate`, `secret-scan` |
| Labels | Applied (36). This change adds `type:onboarding`, `area:repository` and `good first issue`: run `scripts/github/setup_labels.sh` again (it is safe to repeat) |
| Labels | Applied (36) |
| `CODEOWNERS` | Active, with real usernames (this change fixes the single-owner deadlock) |
| `critical-reviewers.txt` | Was empty until this change: PR #10 ran with the gate accepting any two approvers |
| Issues | None created yet (`scripts/github/create_issues.sh` not run) |
| Project and views | Not checked (the `gh` token lacks the `read:project` scope) |
| Repository settings | "Automatically delete head branches" is off. Squash-only comes from the ruleset |
| CI on `main` | Green (`CI`, `security`) after the Oct 7 fixes |

## Files and what they do

| File | Purpose | Applied? |
| ---- | ------- | -------- |
| `.github/workflows/ci.yml` | lint, types, tests, contract, config checks, PR title/branch check, aggregate `ci-success` | Runs once pushed |
| `.github/workflows/security.yml` | `secret-scan` (gitleaks, pinned and checksum-verified), dependency audits | Runs once pushed |
| `.github/workflows/critical-review-gate.yml` | Two approvals on RatelLink and BSS money paths | Runs once pushed |
| `.github/CODEOWNERS` | Review routing. Every rule has two or more owners (a test enforces it) | Active |
| `.github/critical-paths.txt`, `critical-reviewers.txt` | Paths needing two reviewers; named required reviewers (@Ukashatu40, @CaptRaven) | Active once merged |
| `.github/rulesets/main-protection.json` | Branch rules for `main` | Applied |
| `.github/labels.yml` | Label taxonomy | Applied |
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

## Repository visibility

The repository is public because a free GitHub account only enforces rulesets and branch protection
on public repositories: with a private repo, `apply_ruleset.sh` does not enforce anything. Making it
private on the free plan would switch off the review gate and the "no direct push to `main`" rule
for six people with write access, which is worse for the SIM-key code than a public repository
without sensitive files.

So the repository stays public for now, and the sensitive document is out of it:

- The Build Plan PDF is no longer tracked (`.gitignore` keeps `docs/source/*.pdf` out). The lab's
  addresses were removed from `docs/ARCHITECTURE.md`. It remains in Git history from Oct 7: treat
  it as exposed. See [source/README.md](source/README.md).
- Nothing in the repository is a credential. Secret scanning runs on every change and on history.
- **The way back to private** is a paid plan: GitHub Pro on the owner account (rulesets then work on
  private repos), or a paid organization plan. After upgrading, make the repository private and run
  `scripts/github/apply_ruleset.sh` again to confirm the ruleset shows as enforced. Cost is the
  project lead's decision (DECISIONS_PENDING.md #7 and #11, risk R-15).

## What the ruleset enforces

`main-protection` (target: default branch, no bypass actors): blocks deletion and force pushes;
requires linear history; requires a pull request with **1 approval**, code-owner review, approval of
the latest push by someone other than the pusher, stale approvals dismissed on push, review
conversations resolved, **squash merge only**; requires status checks `ci-success`,
`critical-review-gate`, `secret-scan` with the branch up to date.

Not in the ruleset because GitHub cannot express it: "2 reviewers for these paths". That is the
`critical-review-gate` workflow, see [ADR 0004](adr/0004-two-reviewer-enforcement.md).

**Caveats. Checked on PR #10 (Oct 7):** the gate re-ran on `pull_request_review`, failed after the first approval and turned green after the second without a re-push, so that works. Still open:

- The ruleset has **no bypass actors**: not even admins can merge around it. Decide whether you want an emergency bypass for the project lead (TODO, see [DECISIONS_PENDING.md](DECISIONS_PENDING.md)).
- Rulesets on **private** repositories need a paid GitHub plan. On a free private repo, branch protection is not available at all (see "Repository visibility").
- **Merging a change that touches `/.github/` or the gate files.** Those need an approval from a code owner other than the author. If the project lead writes it, @capitanaserdel (or @CaptRaven for the gate files) approves. If the lead is the only possible approver the PR cannot merge, because the ruleset has no bypass. That is by design.

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
