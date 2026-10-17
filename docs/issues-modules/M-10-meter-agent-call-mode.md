# RatelMeter agent: call mode on the voice VM
Labels: type:feature, area:ratel-meter, priority:p2, risk:high

**Module:** RatelMeter agent | **Roadmap week:** 4 | **Owner:** TODO | **Reviewer:** TODO | **Target:** TODO
**Ready:** no. Do not start: waits for #26. On 2026-10-16 no table or file on the voice VM keeps a finished call (`docs/call-record-agreement.md`, lab finding).
**Source:** Build Plan, RatelMeter spec "How calls work"; `docs/call-record-agreement.md`; N7.

## Objective
Every 60 seconds the agent reads new finished-call records from the source the network team enabled, joins start and end, and posts them.

## Scope
To be written once the source and its table definition exist (columns, key, time zone). Do not guess them.

## Out of scope
Calls to other networks, SMS, emergency calls, charging for calls.

## Depends on
#26 signed (the network team enables a call-record source and sends the table definition); M-13 for the API side.

## Contract impact
`end_reason` enum in `openapi.yaml` in the same commit as the agreement.

## Acceptance criteria
To be written after sign-off. At minimum: replay of the same call overwrites; a restart mid-call is handled as the agreement says; UTC epoch seconds.

## Data, security and privacy
Call records are personal data. No number in operational logs.

## Testing
Unit, failure-path, lab.
