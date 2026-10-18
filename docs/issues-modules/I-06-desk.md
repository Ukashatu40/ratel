# Module desk: RatelDesk is demo-ready and tested
Labels: type:feature, area:ratel-desk, priority:p2, risk:medium

**Module:** desk (`web/desk`) | **Owner:** TODO (one person owns this module) | **Backup:** TODO | **Reviewer(s):** TODO
**Blocked or unsure? Ask the project lead.** Do not wait: say what you are waiting for, in this issue.
**Source:** `docs/DEMO_SCRIPT.md`; `docs/issues-modules/README.md`; the deliverables below.

## What this module is for
The part of the demo finish line this module serves, and nothing else. The deliverables below are the work; this issue is the module's checklist. Each deliverable is described in full under "Deliverable details" below.

## Deliverables
- [ ] M-20 RatelDesk: project scaffold and the sell-a-SIM screens against the mock
- [ ] M-29 RatelDesk: the line page with usage, and the side-by-side with the network's counters

## The module is done when
- [ ] The sell journey runs end to end against the mock, then against the real API on the lab
- [ ] The line page shows data used and updates within one interval
- [ ] The reconciliation view makes a difference over 1% visible
- [ ] Every screen that changes data has the history tab the PRD asks for
- [ ] Times are shown in West Africa Time; the wire stays UTC
- [ ] CI runs the frontend tests; no secret or customer data in fixtures
- [ ] Customer care can complete each journey with the written runbook
- [ ] `make check` is green on `main` with this module's changes
- [ ] Its runbook or README is accurate and was followed once

## What this module needs from others
The PRD; M-02 (the API); a decision on the web stack (an ADR); M-26 and M-28 for real data.

## Not in this module
Anything on the Build Plan's "What not to build yet" list.

## Deliverable details

### M-20 RatelDesk: project scaffold and the sell-a-SIM screens against the mock

**Ready:** no, waits for M-02 (the API) and the PRD (journeys, screen content); a decision on the web stack (a new framework needs an ADR)
**Source:** Roadmap Week 4 ("first RatelDesk screens"); `docs/DEMO_SCRIPT.md` act 1; PRD ACC-3 (history tab on screens that change data).

#### Objective
Staff can create a customer, pick a SIM, number and plan, and activate, against the mock.

#### Scope
Screens for the sell journey only. Content and fields: TODO(PRD). RatelDesk is reachable over the VPN only.

#### Out of scope
Reports, dealer and self-care apps, anything a PRD journey does not need.

#### Depends on
M-02; web stack ADR (`web/desk/README.md`).

#### Contract impact
None for the web code.

#### Acceptance criteria
- [ ] The sell journey runs end to end against the mock
- [ ] No Ki, OPc or full secret is ever shown
- [ ] Every screen that changes data has a history tab if the PRD says so
- [ ] `package.json` exists and CI runs the frontend tests

#### Data, security and privacy
Staff authentication and roles: TODO(PRD). No customer data in logs or fixtures.

#### Testing
Frontend journey tests against the mock.

### M-29 RatelDesk: the line page with usage, and the side-by-side with the network's counters

**Ready:** no, waits for M-26, M-28 and the PRD (what the line page shows)
**Source:** `docs/DEMO_SCRIPT.md` acts 2 and 6; PRD ACC-3 (history tab).

#### Objective
Staff open a line and see its status, plan, data used so far and calls, and a view that sets our numbers next to the network's.

#### Scope
Line page and one reconciliation view. Fields and wording: TODO(PRD). Nothing from the cut list beyond one reconciliation view.

#### Out of scope
Report suites, dealer or self-care screens.

#### Depends on
M-20, M-26, M-28.

#### Contract impact
None for the web code.

#### Acceptance criteria
- [ ] The line page shows data used and updates within one interval of 300 seconds
- [ ] The reconciliation view shows a difference over 1% in a visible way (test with a fake)
- [ ] No Ki, OPc or secret is ever shown

#### Data, security and privacy
Staff only, over the VPN. No customer data in test fixtures.

#### Testing
Frontend journey tests against the mock.
