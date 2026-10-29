# ADR 0011: The project lead merges; no approval is required, checks still are

- **Status:** Accepted (project lead, 2026-10-28, on the network lead's suggestion)
- **Date:** 2026-10-28
- **Deciders:** the project lead
- **Related:** [ADR 0004](0004-two-reviewer-enforcement.md) (superseded in part), [GITHUB_SETUP.md](../GITHUB_SETUP.md)

## Context

The `main-protection` ruleset required one approval, a code owner's approval, approval of the
latest push and dismissed approvals on every push. `critical-review-gate` added two named
approvers for RatelLink and `bss_money`. With six people, two of them part-time on another team,
every PR waited for a review, and every fix pushed during review started the wait again. The
demo is 2026-11-26, with a freeze on 2026-11-23. GitHub also never counts an author's own
approval, so the project lead could not merge their own PRs without a second person.

## Decision

Pull requests stay mandatory: nobody pushes to `main`. The ruleset now requires **0 approvals**.
Code-owner review, last-push approval and stale-approval dismissal are off. Review conversations
must still be resolved, history stays linear, merges are squash only, and the required checks are
`ci-success` and `secret-scan`. `critical-review-gate` is no longer required.

The project lead decides what merges. Asking a reviewer is a choice, not a gate.
`CODEOWNERS` still routes review requests. `critical-review-gate` keeps running as information:
it is red on a RatelLink or money PR that has fewer than two approvals, and that does not block a
merge. Its script, paths and tests are unchanged, so the rule can be turned back on by adding the
check to the ruleset.

## Alternatives considered

| Option | Why not (or why it came second) |
| ------ | ------------------------------- |
| Keep the rules, add the project lead as a bypass actor (Repository admin, pull requests only) | Keeps the gate but lets one person skip it, which is the same outcome with a more complicated record. The simpler record is better. |
| Remove the gate only | The one-approval rule is the main cause of the wait. |
| Delete the gate's workflow, script and lists | Not needed to stop the wait. It would need a second decision and is harder to undo. |

## Consequences

- Merging is no longer slowed by review, including fixes during the demo freeze.
- **Nothing independent now looks at the code that holds SIM keys (RatelLink) or money
  (`bss_money`).** CI, the secret scan and the architecture tests still run, but they cannot say
  that a payment rule or a key-handling change is right. A mistake there reaches `main` unseen.
  The project lead accepted this. For those paths, asking the network lead or the second senior
  developer for a look before merging remains good practice, and `critical-review-gate` shows
  when it did not happen.
- Contract changes (`/contracts/`) are no longer forced through the network lead. Agree them by
  conversation, as before.
- `docs/OWNERSHIP_MATRIX.md` and `CODEOWNERS` describe who to ask, not who must approve.
