# RatelLink: apply the lab answer on deactivate (bar or delete) and on re-activation
Labels: type:feature, area:ratel-link, priority:p2, risk:critical

**Module:** RatelLink | **Roadmap week:** 3 | **Owner:** TODO | **Reviewer:** TODO (two required) | **Target:** TODO
**Ready:** no, waits for lab session 1, sections B (barring, re-activation after delete)
**Source:** DECISIONS_PENDING items 51 and 52; N4; `docs/issues-week2/W2-05-spike-subscriber-status-barring.md`.

## Objective
Deactivate and re-activate behave as the lab proved, and the decision is written down.

## Scope
Decided by the lab answer, one of:
- **Delete stays** (the source reading says the MME seems to ignore barring): only if re-activation attaches again. If it does not (lost `security.sqn`), RatelLink must not write a fresh `sqn` blindly: propose a way to the project lead and the network team first.
- **Bar:** only if the lab shows the MME rejects a barred line and calls are cut too. Then deactivate sets `subscriber_status` instead of deleting.

## Out of scope
Live changes (M-06).

## Depends on
Lab session 1, section B.

## Contract impact
Probably none; if the response or the `line_state` meaning of `barred` changes, `openapi.yaml` in the same commit.

## Acceptance criteria
- [ ] The decision is recorded in DECISIONS_PENDING with the lab record that supports it
- [ ] Behaviour matches the lab result, with tests for both deactivate and re-activate
- [ ] `docs/runbooks/ratel-link-lab-acceptance.md` step 4.8 updated to what actually happens
- [ ] `make check` is green

## Data, security and privacy
A deactivated line must stop working. No key is logged. The SIM's stored keys are kept.

## Testing
Unit plus the lab.
