# Repository: decide the offline backup of the RatelLink key file and name its owner (R-14)
Labels: type:documentation, area:repository, priority:p0, risk:critical

**Module:** Repository, CI and docs | **Roadmap week:** 2 (before any real SIM key) | **Owner:** TODO (project lead) | **Reviewer:** TODO | **Target:** TODO
**Ready:** yes
**Source:** `docs/RISK_REGISTER.md` R-14; `docs/runbooks/ratel-link.md` ("Backup: TODO(owner)").

## Objective
Losing `ratel_link.key` cannot lose every stored Ki and OPc, and one named person is responsible for the copy.

## Scope
Choose where the copy lives (offline, apart from database backups), who holds it, and how a restore is tested. Write it in the runbook. No key value in the issue.

## Out of scope
Re-encryption tooling, a second key.

## Depends on
The project lead's decision.

## Contract impact
None.

## Acceptance criteria
- [ ] The runbook names the owner and the procedure (no value)
- [ ] A restore was rehearsed once with a throwaway key, not the real one
- [ ] R-14 is updated

## Data, security and privacy
The copy is never stored with database backups and never travels in a ticket or chat.

## Testing
A restore rehearsal.
