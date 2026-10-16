# RatelBSS money: vouchers redeem exactly once
Labels: type:feature, area:bss-money, priority:p1, risk:critical

**Module:** RatelBSS money | **Roadmap week:** 4 | **Owner:** TODO | **Reviewer:** TODO (two required, critical) | **Target:** TODO
**Ready:** no, waits for M-15 and the PRD (voucher value, format, expiry)
**Source:** Roadmap Week 4 ("vouchers redeem"); Build Plan acceptance ("a voucher redeemed twice credits exactly once"); PRD TOP-2 and TOP-3 for RatelPay.

## Objective
A voucher credits a wallet once, however many times or how concurrently it is redeemed.

## Scope
Voucher creation (staff), redeem operation, ledger entry. Format, value and expiry: TODO(PRD). Codes are secrets: stored hashed, never logged.

## Out of scope
The payment gateway (M-19), dealer vouchers and wallets.

## Depends on
M-15, M-02 for the API shape, PRD.

## Contract impact
Yes, once M-02 defines the BSS API.

## Acceptance criteria
- [ ] Redeeming twice, and twice at the same moment, credits once (test on a real PostgreSQL)
- [ ] A wrong or used code gives one generic error and no hint
- [ ] The code never appears in a log line
- [ ] Out of data is reversed after a redeem when the wallet covers it (with M-17)

## Data, security and privacy
Codes are credentials. Rate-limit redemption attempts.

## Testing
Unit, integration, concurrency.
