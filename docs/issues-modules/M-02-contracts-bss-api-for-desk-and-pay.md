# Contracts: specify RatelBSS's own API for RatelDesk and RatelPay
Labels: type:feature, area:contracts, priority:p2, risk:high

**Module:** Contracts | **Roadmap week:** 4 | **Owner:** TODO | **Reviewer:** TODO | **Target:** TODO
**Ready:** no, needs the PRD (the four journeys, the screens, the customer and KYC fields)
**Source:** Build Plan ("frontend developers code against a mock of the API"); DECISIONS_PENDING open question 4; `TODO(PRD)`.

## Objective
The operations RatelDesk and RatelPay call on RatelBSS are in `contracts/openapi.yaml` with a mock, so the web modules can start without the backend.

## Scope
Operations for the four journeys the PRD defines, no more. Which journeys and fields: TODO(PRD). Do not invent fields.

## Out of scope
Any operation no journey needs. Self-care and dealer apps (Build Plan, "What not to build yet").

## Depends on
The PRD (ask the network lead for it). M-01 is independent.

## Contract impact
Changes `openapi.yaml`, `not_implemented.txt` and the mock together.

## Acceptance criteria
- [ ] Every journey in the PRD is walkable against the mock, listed in the issue
- [ ] RatelPay's operations expose nothing personal about a line's owner (PRD TOP-2, to confirm)
- [ ] Contract tests pass; drift test passes with the new operations listed as not implemented

## Data, security and privacy
Customer and KYC data never reach RatelLink or RatelMeter. Money in whole kobo.

## Testing
Contract tests. No lab.
