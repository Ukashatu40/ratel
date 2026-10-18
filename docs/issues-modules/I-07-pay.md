# Module pay: RatelPay is demo-ready and tested
Labels: type:feature, area:ratel-pay, priority:p2, risk:medium

**Module:** pay (`web/pay`) | **Owner:** TODO (one person owns this module) | **Backup:** TODO | **Reviewer(s):** TODO
**Blocked or unsure? Ask the project lead.** Do not wait: say what you are waiting for, in this issue.
**Source:** `docs/DEMO_SCRIPT.md`; `docs/issues-modules/README.md`; the deliverables below.

## What this module is for
The part of the demo finish line this module serves, and nothing else. The deliverables below are the work; this issue is the module's checklist. Each deliverable is described in full under "Deliverable details" below.

## Deliverables
- [ ] M-21 RatelPay: the top-up page

## The module is done when
- [ ] A voucher redeems from the page and credits once
- [ ] The page loads in under 3 seconds on a 3G profile; its weight is recorded
- [ ] Nothing personal about the line's owner is shown
- [ ] Times are shown in West Africa Time; PINs are never shown or logged beyond the last four digits
- [ ] A wrong code shows one generic message; redemption attempts are rate-limited
- [ ] The gateway path works in the sandbox if M-19 is done; otherwise the voucher-only path is the demo
- [ ] `make check` is green on `main` with this module's changes
- [ ] Its runbook or README is accurate and was followed once

## What this module needs from others
The PRD (TOP-2, TOP-3, wording); M-18 and M-02; M-19 for the gateway.

## Not in this module
Anything on the Build Plan's "What not to build yet" list.

## Deliverable details

### M-21 RatelPay: the top-up page

**Ready:** no, waits for M-02, M-18 and the PRD
**Source:** Roadmap Week 5; PRD TOP-2 (nothing personal about a line's owner shown) and TOP-3 (loads in under 3 seconds on 3G), both to be read from the PRD.

#### Objective
A customer redeems a voucher (and later pays in the sandbox) from a plain page that is fast and shows nothing personal.

#### Scope
Voucher redeem page first; the gateway path after M-19. Wording and result screens: TODO(PRD).

#### Out of scope
Self-care features, accounts, dealer features.

#### Depends on
M-02, M-18; M-19 for the gateway path.

#### Contract impact
None for the page.

#### Acceptance criteria
- [ ] The page loads in under 3 seconds on a 3G profile and its weight is recorded in the PR
- [ ] No name, number or address of the line's owner is shown
- [ ] A wrong code shows one generic message

#### Data, security and privacy
Public page: rate limits and no personal data.

#### Testing
Frontend tests; page weight and load time check.
