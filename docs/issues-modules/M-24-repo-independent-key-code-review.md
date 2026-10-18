# Repository: independent review of the RatelLink key code before customer keys
Labels: type:security, area:repository, priority:p3, risk:critical

**Module:** Repository, CI and docs | **Roadmap week:** 6 | **Owner:** TODO | **Reviewer:** TODO | **Target:** TODO
**Ready:** no, scheduled for Week 6; must be done before any customer key, and not before the Week 6 security review
**Source:** `docs/DECISIONS_PENDING.md` item 56 (proposed); `docs/RISK_REGISTER.md` R-17; closed #32.

## Objective
Someone who did not write or approve PR #10 reads the key code and its tests and reports what they checked.

## Scope
`services/ratel_link/security/` (crypto, key provider, authentication), the Ki/OPc store, ADR 0006 and 0007. An AI-assisted pass may be added but does not count as the independent human review.

## Out of scope
Rewriting the code. Findings become their own issues.

## Depends on
A reviewer who is not the author and not CaptRaven's approval-only habit. Named by the project lead.

## Contract impact
None.

## Acceptance criteria
- [ ] A written review lists what was read and what was not
- [ ] Each finding is a labelled issue or marked as accepted with the project lead's name
- [ ] R-17 is closed or re-rated

## Data, security and privacy
Review with synthetic keys only. Do not paste real keys anywhere.

## Testing
n/a
