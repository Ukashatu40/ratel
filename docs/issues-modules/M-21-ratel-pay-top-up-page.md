# RatelPay: the top-up page
Labels: type:feature, area:ratel-pay, priority:p2, risk:medium

**Module:** RatelPay | **Roadmap week:** 5 | **Owner:** TODO | **Reviewer:** TODO | **Target:** TODO
**Ready:** no, waits for M-02, M-18 and the PRD
**Source:** Roadmap Week 5; PRD TOP-2 (nothing personal about a line's owner shown) and TOP-3 (loads in under 3 seconds on 3G), both to be read from the PRD.

## Objective
A customer redeems a voucher (and later pays in the sandbox) from a plain page that is fast and shows nothing personal.

## Scope
Voucher redeem page first; the gateway path after M-19. Wording and result screens: TODO(PRD).

## Out of scope
Self-care features, accounts, dealer features.

## Depends on
M-02, M-18; M-19 for the gateway path.

## Contract impact
None for the page.

## Acceptance criteria
- [ ] The page loads in under 3 seconds on a 3G profile and its weight is recorded in the PR
- [ ] No name, number or address of the line's owner is shown
- [ ] A wrong code shows one generic message

## Data, security and privacy
Public page: rate limits and no personal data.

## Testing
Frontend tests; page weight and load time check.
