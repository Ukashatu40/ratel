# RatelDesk: project scaffold and the sell-a-SIM screens against the mock
Labels: type:feature, area:ratel-desk, priority:p2, risk:medium

**Module:** RatelDesk | **Roadmap week:** 4 | **Owner:** TODO | **Reviewer:** TODO | **Target:** TODO
**Ready:** no, waits for M-02 (the API) and the PRD (journeys, screen content); a decision on the web stack (a new framework needs an ADR)
**Source:** Roadmap Week 4 ("first RatelDesk screens"); `docs/DEMO_SCRIPT.md` act 1; PRD ACC-3 (history tab on screens that change data).

## Objective
Staff can create a customer, pick a SIM, number and plan, and activate, against the mock.

## Scope
Screens for the sell journey only. Content and fields: TODO(PRD). RatelDesk is reachable over the VPN only.

## Out of scope
Reports, dealer and self-care apps, anything a PRD journey does not need.

## Depends on
M-02; web stack ADR (`web/desk/README.md`).

## Contract impact
None for the web code.

## Acceptance criteria
- [ ] The sell journey runs end to end against the mock
- [ ] No Ki, OPc or full secret is ever shown
- [ ] Every screen that changes data has a history tab if the PRD says so
- [ ] `package.json` exists and CI runs the frontend tests

## Data, security and privacy
Staff authentication and roles: TODO(PRD). No customer data in logs or fixtures.

## Testing
Frontend journey tests against the mock.
