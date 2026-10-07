# ADR 0004: Enforce "two reviewers" for critical paths with a status check

- **Status:** Proposed (needs project lead approval and a test on the first real PR)
- **Date:** 2026-10-06
- **Related:** Build Plan "Engineering rules: Review"; [GITHUB_SETUP.md](../GITHUB_SETUP.md); [DECISIONS_PENDING.md](../DECISIONS_PENDING.md) #4

## Context

The Build Plan: changes to RatelLink (keys) and RatelBSS: money need two reviewers; everything else
needs one. GitHub branch rules require one approval count for the whole branch. A CODEOWNERS rule
with several owners is satisfied by any one of them.

## Decision

Branch rules require 1 approval plus code-owner review. A required status check,
`critical-review-gate` (`scripts/ci/critical_review_gate.py`), fails a pull request that touches
the paths in `.github/critical-paths.txt` unless two distinct people, neither the author, approved
the latest commit and every login in `.github/critical-reviewers.txt` has approved. The workflow
checks out the base branch so a PR cannot weaken the gate in the same PR.

## Alternatives considered

| Option | Why not |
| ------ | ------- |
| Require 2 approvals on every PR | Slows all work and ignores the Build Plan's one-reviewer rule for everything else; with six people, review load matters. A reasonable temporary fallback. |
| CODEOWNERS only | Cannot demand two people. |
| Convention without enforcement | The Build Plan calls it a rule. |

## Consequences

One small script to maintain (unit-tested). Governance files are in the critical review set via
CODEOWNERS (project lead). The check's behavior on `pull_request_review` events was not tested
against live GitHub when written; verify on the first PR.

## Security implications

Raises the bar for the two areas that hold keys and money. A broken gate fails closed on PRs touching those paths.

## Data implications

None.

## Operational implications

Needs usernames filled in. Docs: GitHub setup checklist.
