# RatelBSS money: one payment gateway end to end in the sandbox
Labels: type:feature, area:bss-money, priority:p2, risk:critical

**Module:** RatelBSS money | **Roadmap week:** 5 | **Owner:** TODO | **Reviewer:** TODO (two required, critical) | **Target:** TODO
**Ready:** no. Do not start before Week 4's loop works; the gateway choice is TODO(PRD or project lead).
**Source:** Roadmap Week 5; Build Plan (one gateway is enough to prove the flow; a second is "not before the demo").

## Objective
A sandbox payment credits a wallet once, and a webhook delivered twice credits once.

## Scope
Initiate, receive the webhook (public path, signed), verify, credit through the ledger. The gateway and its signature scheme: TODO.

## Out of scope
A second gateway, live payments, card data of any kind in our systems.

## Depends on
M-15, M-18, M-02.

## Contract impact
Yes.

## Acceptance criteria
- [ ] Webhook with a bad signature is rejected before anything is read
- [ ] The same webhook twice credits once (test)
- [ ] No card data, gateway secret or token in any log or the repository

## Data, security and privacy
Payment secrets only in owner-only environment files. The webhook is one of the only public paths.

## Testing
Unit, integration, contract.
