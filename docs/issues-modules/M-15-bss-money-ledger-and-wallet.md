# RatelBSS money: the ledger and the wallet
Labels: type:feature, type:database, area:bss-money, priority:p1, risk:critical

**Module:** RatelBSS money | **Roadmap week:** 3 | **Owner:** TODO | **Reviewer:** TODO (two required, critical) | **Target:** TODO
**Ready:** partly. The ledger rules are in the Build Plan and `docs/ENGINEERING_RULES.md`; the entry types and fields beyond them are TODO(PRD).
**Source:** Build Plan, RatelBSS: money; `docs/TESTING_STRATEGY.md` (financial / ledger row).

## Objective
Money moves only by appending ledger entries, and every wallet balance equals the sum of its entries.

## Scope
- Ledger table: append-only (no update, no delete), amounts in whole kobo (`int`), UTC time, a reason and an actor on every entry.
- Wallet balance derived from or checked against the entries. VAT is its own entry. Entry types and VAT rate: TODO(PRD).
- A nightly wallet-versus-ledger check that alerts on mismatch.
- Migration under `services/app/migrations/`.

## Out of scope
Vouchers (M-18), gateway (M-19), rating (M-17), dealer wallets and hierarchy (not before the demo).

## Depends on
PRD for entry types, VAT and wallet rules. Project lead approves the migration.

## Contract impact
None for this issue.

## Acceptance criteria
- [ ] An UPDATE or DELETE on a ledger row is refused (test on a real PostgreSQL)
- [ ] No float anywhere in money code (the architecture test passes)
- [ ] Balance equals the sum of entries after a mixed sequence, including concurrent writes (test)
- [ ] The nightly check reports a deliberately corrupted balance (test proves the check can fail)
- [ ] Migration applies and rolls back

## Data, security and privacy
Critical area: two reviewers, security checklist. No real payment data anywhere.

## Testing
Unit, integration (PostgreSQL), concurrency.
