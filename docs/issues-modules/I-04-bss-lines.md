# Module bss_lines: RatelBSS lines is demo-ready and tested
Labels: type:feature, type:database, area:bss-lines, area:contracts, priority:p1, risk:high

**Module:** bss_lines (`services/app/bss_lines`) | **Owner:** TODO (one person owns this module) | **Backup:** TODO | **Reviewer(s):** TODO
**Blocked or unsure? Ask the project lead.** Do not wait: say what you are waiting for, in this issue.
**Source:** `docs/DEMO_SCRIPT.md`; `docs/issues-modules/README.md`; the deliverables below.

## What this module is for
The part of the demo finish line this module serves, and nothing else. The deliverables below are the work; this issue is the module's checklist. Each deliverable is described in full under "Deliverable details" below.

## Deliverables
- [ ] M-02 Contracts: specify RatelBSS's own API for RatelDesk and RatelPay
- [ ] M-14 RatelBSS lines: the RatelLink client and the sell-to-activate flow
- [ ] M-25 RatelBSS lines: the schema and the stock (customer, SIM, number, plan, bundle, line)
- [ ] M-26 RatelBSS lines: the line and customer API that RatelDesk calls
- [ ] M-32 RatelBSS lines: the whole line lifecycle, every transition calls RatelLink

## The module is done when
- [ ] Selling a SIM and activating produces exactly one /activate call, through the state machine only (mock and lab)
- [ ] A retry with the same Idempotency-Key has no second effect
- [ ] Every transition not in the table is refused (the 36-pair test stays green)
- [ ] A SIM or number cannot be taken twice, even by simultaneous requests
- [ ] The database holds no ki or opc; activation is refused without verified KYC
- [ ] Customer care can find any line by MSISDN, ICCID or IMSI in under a second
- [ ] Every state change has an audit entry; a failure mid-transition leaves the state the project lead decided
- [ ] `make check` is green on `main` with this module's changes
- [ ] Its runbook or README is accurate and was followed once

## What this module needs from others
The PRD (customer and KYC fields); M-02 (the API); RatelLink on the lab (E-01); M-12 for usage on the line page.

## Not in this module
Anything on the Build Plan's "What not to build yet" list.

## Deliverable details

### M-02 Contracts: specify RatelBSS's own API for RatelDesk and RatelPay

**Ready:** no, needs the PRD (the four journeys, the screens, the customer and KYC fields)
**Source:** Build Plan ("frontend developers code against a mock of the API"); DECISIONS_PENDING open question 4; `TODO(PRD)`.

#### Objective
The operations RatelDesk and RatelPay call on RatelBSS are in `contracts/openapi.yaml` with a mock, so the web modules can start without the backend.

#### Scope
Operations for the four journeys the PRD defines, no more. Which journeys and fields: TODO(PRD). Do not invent fields.

#### Out of scope
Any operation no journey needs. Self-care and dealer apps (Build Plan, "What not to build yet").

#### Depends on
The PRD (ask the network lead for it). M-01 is independent.

#### Contract impact
Changes `openapi.yaml`, `not_implemented.txt` and the mock together.

#### Acceptance criteria
- [ ] Every journey in the PRD is walkable against the mock, listed in the issue
- [ ] RatelPay's operations expose nothing personal about a line's owner (PRD TOP-2, to confirm)
- [ ] Contract tests pass; drift test passes with the new operations listed as not implemented

#### Data, security and privacy
Customer and KYC data never reach RatelLink or RatelMeter. Money in whole kobo.

#### Testing
Contract tests. No lab.

### M-14 RatelBSS lines: the RatelLink client and the sell-to-activate flow

**Ready:** yes against the mock. The lab run is part of lab session 1, section F.
**Source:** Build Plan, RatelBSS: lines "Done when"; #27 (software part); `services/app/bss_lines/domain.py` (the state machine, merged in #46); DECISIONS_PENDING question 6.

#### Objective
Selling a SIM and activating it produces exactly one `/activate` call on RatelLink, through the state machine and nowhere else.

#### Scope
- RatelLink client (base URL, API key, `Idempotency-Key`) configured by environment: the mock locally, the lab RatelLink on the lab.
- Activation sends the plan's speeds and `voice` true as the contract says.
- Only the state machine calls RatelLink. Each transition has an audit entry (who, why).
- KYC must be verified before activation (Build Plan rule). Its fields: TODO(PRD).
- **Before building the failure path**, propose to the project lead what state a line keeps if RatelLink fails mid-transition (DECISIONS_PENDING question 6).

#### Out of scope
Rating, `out_of_data` (M-17). Live changes. Screens (M-20).

#### Depends on
The mock (current). RatelLink on the lab for the lab run (M-03).

#### Contract impact
None, unless a `TODO(contract)` item is touched.

#### Acceptance criteria
- [ ] The flow produces exactly one `/activate` call (test counts calls at the mock)
- [ ] A retry with the same `Idempotency-Key` has no second effect (test)
- [ ] RatelBSS's database holds no `ki` or `opc` (schema test); SIM import keeps ICCID, IMSI and batch only
- [ ] No code path other than the state machine changes a line's state (architecture or unit test)
- [ ] The lab run is recorded in lab session 1, section F

#### Data, security and privacy
Customer and KYC data stay in RatelBSS. RatelLink API key from an owner-only environment file.

#### Testing
Unit, contract (mock), integration (PostgreSQL). Lab: session 1.

### M-25 RatelBSS lines: the schema and the stock (customer, SIM, number, plan, bundle, line)

**Ready:** partly. The tables and rules can start; every customer and KYC field is TODO(PRD).
**Source:** Build Plan, RatelBSS: lines; `docs/DEMO_SCRIPT.md` act 1 ("create a customer, pick a free SIM and number, pick a plan, activate"); `services/app/bss_lines/domain.py` (the state machine).

#### Objective
RatelBSS holds the customers, the stock of SIMs and numbers, and the KYC status that the sell-to-activate flow (M-14) needs.

#### Scope
- Tables from the Build Plan: customer (name, phone, email, id type and number, address, `kyc_status` pending, verified or rejected, `blocked` as a separate flag), sim (iccid, imsi, batch; in_stock, in_use, retired), number (msisdn; available, in_use, quarantined), plan, bundle (fields in M-16), line (line_id, customer_id, iccid, imsi, msisdn, plan_id, expires_at, state, state_before_suspension).
- The customer's NIN is captured at registration. The exact verification rules are compliance's call: confirm the current NCC SIM registration requirements before the pilot (TODO(compliance)).
- A number taken back from a terminated line is quarantined for the period compliance sets.
- A line cannot be activated until KYC is verified.
- SIM stock: ICCID, IMSI and batch only. **Never Ki or OPc.**
- Number stock: the stored form `234` plus ten digits. A number and a SIM are each taken once.
- Migration under `services/app/migrations/`, model in `models.py`.
- Open question for the project lead: how a batch of SIM keys reaches RatelLink without passing through RatelBSS (today: the manual import in the lab runbook).

#### Out of scope
Importing existing customers. Dealer hierarchy. The screens (M-20).

#### Depends on
PRD. M-14 for the flow that uses the stock.

#### Contract impact
Yes, through M-02 (the operations the screens call).

#### Acceptance criteria
- [ ] A SIM or number cannot be taken twice, even by two requests at once (test on a real PostgreSQL)
- [ ] The schema has no `ki` or `opc` column anywhere (schema test)
- [ ] Activation is refused for a customer whose KYC is not verified (test)
- [ ] Every change has an audit entry with who and why
- [ ] Migration applies and rolls back

#### Data, security and privacy
Customer and KYC data are personal data: never in RatelLink, RatelMeter or logs.

#### Testing
Unit, integration (PostgreSQL), concurrency.

### M-26 RatelBSS lines: the line and customer API that RatelDesk calls

**Ready:** no, waits for M-02 (operations) and M-25 (the data)
**Source:** `services/app/main.py` (TODO: mount bss_lines, bss_money and meter_api routers); M-02.

#### Objective
The operations M-02 defines for customers, stock, lines and the line page (status, plan, usage) are served by RatelBSS and mounted in the app.

#### Scope
Implement and mount the lines side of M-02: `/v1/customers`, `/v1/lines`, `/v1/plans`, `/v1/bundles`, `/v1/stock` (Build Plan). Also:
- **Staff accounts and sign-in.** Roles and permissions: TODO(PRD).
- **Find any line by MSISDN, ICCID or IMSI in under a second** (indexed lookups).
- Every state-changing endpoint accepts `Idempotency-Key` (keys kept in Redis); repeating a call returns the first result.
- The usage on the line page comes from the RatelMeter API (M-12), never from the network directly.

#### Out of scope
Money operations (M-18, M-19). Screens.

#### Depends on
M-02, M-25, M-14, M-12.

#### Contract impact
Yes: `not_implemented.txt` in the same PRs.

#### Acceptance criteria
- [ ] Each operation matches the contract (drift test and Schemathesis pass)
- [ ] RatelBSS never opens a connection to MongoDB or the network (architecture tests pass)
- [ ] Only the state machine changes a line's state
- [ ] Lookup by MSISDN, ICCID and IMSI returns in under a second on 100,000 synthetic lines (test)
- [ ] A repeated call with the same `Idempotency-Key` returns the first result and changes nothing (test)
- [ ] Auth first: every route rejects a missing or wrong credential before reading input

#### Data, security and privacy
Reachable only over the VPN (RatelPay and the payment webhook are the only public paths).

#### Testing
Unit, integration, contract.

### M-32 RatelBSS lines: the whole line lifecycle, every transition calls RatelLink

**Ready:** no, waits for M-14 (the client), M-15 (wallet) and M-25
**Source:** Build Plan, RatelBSS: lines, "Line states" table; `services/app/bss_lines/domain.py` (the 15 allowed pairs).

#### Objective
Every allowed transition in the Build Plan's table is reachable from RatelBSS and makes the right call to RatelLink. M-14 covers only the first (activate).

#### Scope
| From | To | When | Call to RatelLink |
| ---- | -- | ---- | ----------------- |
| awaiting_activation | active | First plan paid for and KYC verified | `/activate` with the plan's speeds and voice true |
| active | out_of_data | Allowance used up before the plan expires (decided by money, M-17) | `/data` slow with the plan's slow speeds, or off, per `on_exhaustion` |
| out_of_data | active | Customer buys a bundle or a new plan | `/data` full with the plan's speeds |
| active or out_of_data | expired | Plan validity ends without renewal | `/deactivate` |
| expired | active | Customer buys a plan | `/activate` |
| active or out_of_data | suspended | Customer care action, with a reason | `/deactivate` |
| suspended | the state it had before | Customer care action, with a reason | `/activate`, then `/data` if it was out_of_data |
| any other state | terminated | Care action or end of contract | `/deactivate`; SIM retired, number quarantined |

Buying a plan or bundle from the wallet (the purchase itself, through the ledger) is part of this issue where it triggers a transition.

#### Out of scope
Live changes (M-06). Charging for calls.

#### Depends on
M-14, M-15, M-25, M-17 for the out-of-data trigger.

#### Contract impact
None expected (RatelLink's operations already exist). The BSS operations are in M-02.

#### Acceptance criteria
- [ ] A test for every row above: the transition happens, the right RatelLink call is made exactly once, an audit entry says who and why
- [ ] The 36-pair test still refuses every transition not in the table
- [ ] Suspend then unsuspend restores `state_before_suspension` and the data mode it had
- [ ] A RatelLink failure mid-transition leaves the state the project lead decided (DECISIONS_PENDING question 6)
- [ ] Terminate retires the SIM and quarantines the number

#### Data, security and privacy
Care actions need a reason, recorded. No code updates a state column directly.

#### Testing
Unit, integration, contract (mock). Lab: part of the end-to-end dry run (M-31).
