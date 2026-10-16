# Contracts: specify the agent's ingest call to the RatelMeter API
Labels: type:feature, area:contracts, priority:p1, risk:high

**Module:** Contracts | **Roadmap week:** 3 | **Owner:** TODO | **Reviewer:** TODO | **Target:** TODO
**Ready:** no, needs the project lead's decision on the shape (DECISIONS_PENDING, open question 4)
**Source:** Build Plan, RatelMeter spec (record shape and key); #25 ("the agent-to-API ingest call is not in the frozen contracts").

## Objective
The call the data agent makes to deliver 300-second records is in `contracts/openapi.yaml`, served by the mock, so the agent and the API can be built independently.

## Scope
- One new operation. Record: `imsi`, `period_start`, `period_end`, `bytes_up`, `bytes_down` (integers, UTC epoch seconds). The key is `imsi + period_start`: sending the same interval again overwrites, never duplicates.
- Batch size, authentication of the agent to this API, and error codes: TODO, proposed in the issue by the person who takes it, decided by the project lead.
- The operation is listed in `contracts/not_implemented.txt` until M-11 implements it.

## Out of scope
The storage and the endpoint's code (M-11), call records (M-13).

## Depends on
A decision on the points marked TODO. Nothing else.

## Contract impact
Changes `openapi.yaml`, `not_implemented.txt` and the mock in one commit.

## Acceptance criteria
- [ ] The operation validates (`make contract`) and follows the contract conventions test
- [ ] The mock accepts a valid batch and rejects an invalid one
- [ ] Replay of an identical interval is documented as an overwrite, with the example in the contract
- [ ] No IMSI appears in any example outside the synthetic fixtures

## Data, security and privacy
Records are personal data. Integers only for bytes. UTC epoch seconds.

## Testing
Contract tests. No lab.
