# Module bss_money: RatelBSS money is demo-ready and tested
Labels: type:feature, type:database, area:bss-money, priority:p1, risk:critical

**Module:** bss_money (`services/app/bss_money`) | **Owner:** TODO (one person owns this module) | **Backup:** TODO | **Reviewer(s):** TODO
**Blocked or unsure? Ask the project lead.** Do not wait: say what you are waiting for, in this issue.
**Source:** `docs/DEMO_SCRIPT.md`; `docs/issues-modules/README.md`; the deliverables below.

## What this module is for
The part of the demo finish line this module serves, and nothing else. The deliverables below are the work; this issue is the module's checklist. Each deliverable is described in full under "Deliverable details" below.

## Deliverables
- [ ] M-15 RatelBSS money: the ledger and the wallet
- [ ] M-16 RatelBSS money: plans, bundles and the rating function
- [ ] M-17 RatelBSS money: the rating job and the out-of-data trigger
- [ ] M-18 RatelBSS money: vouchers redeem exactly once
- [ ] M-19 RatelBSS money: one payment gateway end to end in the sandbox

## The module is done when
- [ ] The ledger is append-only and every wallet balance equals the sum of its entries; the nightly check alerts on a mismatch
- [ ] Money is whole kobo everywhere; no float anywhere (architecture test)
- [ ] A voucher redeemed twice, and a webhook delivered twice, each credit exactly once
- [ ] A crash mid-run of the rating job rates nothing twice and loses nothing
- [ ] At zero a line is slowed or cut once, calls still work, and a top-up restores data with out of data reversed (lab)
- [ ] Two real reviewers approved every PR; the security review (M-30) found nothing open
- [ ] `make check` is green on `main` with this module's changes
- [ ] Its runbook or README is accurate and was followed once

## What this module needs from others
The PRD (plans, prices, vouchers); M-12 (usage); M-14 and E-01 (the data operation); M-02.

## Not in this module
Anything on the Build Plan's "What not to build yet" list.

## Deliverable details

### M-15 RatelBSS money: the ledger and the wallet

**Ready:** yes for the tables and rules (Build Plan, RatelBSS: money). Only the list of entry kinds is TODO(PRD).
**Source:** Build Plan, RatelBSS: money; `docs/TESTING_STRATEGY.md` (financial / ledger row).

#### Objective
Money moves only by appending ledger entries, and every wallet balance equals the sum of its entries.

#### Scope
- Tables from the Build Plan: `allowance_bucket` (bucket_id, line_id, source plan or bundle, data_bytes_total, data_bytes_used, valid_from, valid_to), `wallet` (line_id, balance_kobo), `ledger_entry` (entry_id, line_id, amount_kobo, kind, reference, created_at).
- Ledger: append-only (no update, no delete), whole kobo (`int`), UTC time. A correction is a new entry, never an edit. A wallet's balance always equals the sum of its entries.
- VAT is recorded as its own ledger entry at the rate finance confirms (7.5% at the time the plan was written, check it). Entry kinds: TODO(PRD).
- A nightly wallet-versus-ledger check that alerts on mismatch.
- Migration under `services/app/migrations/`.

#### Out of scope
Vouchers (M-18), gateway (M-19), rating (M-17), dealer wallets and hierarchy (not before the demo).

#### Depends on
PRD for entry types, VAT and wallet rules. Project lead approves the migration.

#### Contract impact
None for this issue.

#### Acceptance criteria
- [ ] An UPDATE or DELETE on a ledger row is refused (test on a real PostgreSQL)
- [ ] No float anywhere in money code (the architecture test passes)
- [ ] Balance equals the sum of entries after a mixed sequence, including concurrent writes (test)
- [ ] The nightly check reports a deliberately corrupted balance (test proves the check can fail)
- [ ] Migration applies and rolls back

#### Data, security and privacy
Critical area: two reviewers, security checklist. No real payment data anywhere.

#### Testing
Unit, integration (PostgreSQL), concurrency.

### M-16 RatelBSS money: plans, bundles and the rating function

**Ready:** the function and its entities yes (Build Plan fields below); the actual plans, prices and speeds are TODO(PRD)
**Source:** Roadmap Week 3 ("plans and bundles; rating logic tested on synthetic records"); Build Plan, RatelBSS: money; `TODO(PRD)`.

#### Objective
A pure function turns a line's usage records and its plan into an allowance remaining and a decision (stay, slow, cut), tested on synthetic records.

#### Scope
The rating function with no database and no clock inside it. Deduct each usage record from the line's allowance buckets, **soonest expiry first**. Plan fields (Build Plan): plan_id, name, price_kobo, validity_days, data_bytes, speed_ul_mbps, speed_dl_mbps, channels, on_exhaustion (slow or stop), slow_ul_mbps, slow_dl_mbps. Bundle: bundle_id, name, price_kobo, validity_days, data_bytes, channels. The actual plans, prices and speeds: TODO(PRD). Do not invent them. Data left in an expired bucket is lost (no rollover in the first release). Calls are not rated for the demo.

#### Out of scope
The job that runs it (M-17), charging for calls, postpaid and credit limits.

#### Depends on
PRD. M-12 for the usage shape (the function can use the contract's shape now).

#### Contract impact
None for the pure function.

#### Acceptance criteria
- [ ] Table-driven tests on synthetic records, including exactly-zero, one byte over, and several bundles
- [ ] Money in whole kobo, no float; bytes are integers
- [ ] Replaying the same records gives the same result (idempotent)
- [ ] The function never raises on an empty or unsorted input

#### Data, security and privacy
Synthetic data only.

#### Testing
Unit.

### M-17 RatelBSS money: the rating job and the out-of-data trigger

**Ready:** no, waits for M-12, M-15, M-16 and M-14
**Source:** Roadmap Week 4 gate (the full prepaid loop); `docs/DEMO_SCRIPT.md` act 4.

#### Objective
When a line's allowance reaches zero, the job moves it to out of data through the state machine and RatelLink slows or cuts data while calls keep working.

#### Scope
- A job every 300 seconds reading usage (M-12), rating it (M-16), writing ledger entries (M-15).
- At zero: the state machine transition, then `POST /v1/lines/{imsi}/data` through the RatelLink client (M-14).
- **Each usage record is marked rated in the same database transaction as its deduction**, so a crash can never rate one twice.
- On `on_exhaustion` slow: `/data` with mode slow and the plan's slow speeds; on stop: mode off.
- **Expiry:** when a plan's validity ends without renewal, move the line to `expired` through the state machine (calls `/deactivate`).
- Reversal when data is restored (a bundle or new plan bought), `/data` with mode full and the plan's speeds.
- Changes reach the phone at its next attach until live changes exist (M-06): say so in the runbook.

#### Out of scope
Real-time online charging. A faster loop for the demo (a deviation the project lead approves). Charging for calls (VOI-7, designed after the demo).

#### Depends on
M-12, M-14, M-15, M-16. Lab for the end-to-end run.

#### Contract impact
None expected.

#### Acceptance criteria
- [ ] A crash mid-run rates nothing twice and loses nothing (test)
- [ ] A line at zero is moved once, however many times the job runs (idempotent)
- [ ] Voice is untouched by the data change (test at the RatelLink client boundary)
- [ ] On the lab, a line used past zero is slowed or cut and a call still works after an airplane-mode toggle

#### Data, security and privacy
Money in kobo, ledger append-only, no IMSI in operational logs.

#### Testing
Unit, failure-path, integration, lab.

### M-18 RatelBSS money: vouchers redeem exactly once

**Ready:** no, waits for M-15 (the format is in the Build Plan; face values and expiry are TODO(PRD))
**Source:** Roadmap Week 4 ("vouchers redeem"); Build Plan acceptance ("a voucher redeemed twice credits exactly once"); PRD TOP-2 and TOP-3 for RatelPay.

#### Objective
A voucher credits a wallet once, however many times or how concurrently it is redeemed.

#### Scope
Voucher batches and redemption. Build Plan: a 20-digit card number, a 13-digit PIN plus one Luhn check digit; states requested, approved, sent_to_printer, in_stock, on_sale, used, expired, and locked for lost or stolen cards; **at most 5 failed redemption attempts per number per hour**. The PIN is stored hashed, never in plain text, and in logs only masked to its last four digits. Face values and expiry: TODO(PRD).

#### Out of scope
The payment gateway (M-19), dealer vouchers and wallets.

#### Depends on
M-15, M-02 for the API shape, PRD.

#### Contract impact
Yes, once M-02 defines the BSS API.

#### Acceptance criteria
- [ ] Redeeming twice, and twice at the same moment, credits once (test on a real PostgreSQL)
- [ ] The check digit is validated (unit test with known good and bad numbers)
- [ ] The sixth failed attempt for one number within an hour is refused (test with an injected clock)
- [ ] A wrong or used code gives one generic error and no hint
- [ ] The code never appears in a log line
- [ ] Out of data is reversed after a redeem when the wallet covers it (with M-17)

#### Data, security and privacy
Codes are credentials. Rate-limit redemption attempts.

#### Testing
Unit, integration, concurrency.

### M-19 RatelBSS money: one payment gateway end to end in the sandbox

**Ready:** no. Do not start before Week 4's loop works; the gateway choice is TODO(PRD or project lead).
**Source:** Roadmap Week 5; Build Plan (one gateway is enough to prove the flow; a second is "not before the demo").

#### Objective
A sandbox payment credits a wallet once, and a webhook delivered twice credits once.

#### Scope
Initiate, receive the webhook (public path, rate-limited), **verify its signature, then re-query the transaction with the provider before crediting anything**, credit through the ledger. `payment` table: payment_id, provider, provider_ref (unique), amount_kobo, status, line_id. A webhook delivered twice credits once because `provider_ref` is unique. The gateway and its signature scheme: TODO.

#### Out of scope
A second gateway, live payments, card data of any kind in our systems.

#### Depends on
M-15, M-18, M-02.

#### Contract impact
Yes.

#### Acceptance criteria
- [ ] Webhook with a bad signature is rejected before anything is read
- [ ] The same webhook twice credits once (test)
- [ ] No card data, gateway secret or token in any log or the repository

#### Data, security and privacy
Payment secrets only in owner-only environment files. The webhook is one of the only public paths.

#### Testing
Unit, integration, contract.
