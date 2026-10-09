# RatelBSS lines: the line state machine (transition table and tests)
Labels: type:feature, area:bss-lines, priority:p1, risk:high, good first issue

**Week:** 2 | **Target date:** 2026-10-13 | **Owner:** @Abbalolo | **Reviewer:** @Ukashatu40 (mentor: @Ukashatu40, pair for the first hour)
**Source:** Build Plan, RatelBSS: lines, "Line states" table and rules ("State changes happen only through the state machine"); "Done when": "Tests prove every transition not in the table above is refused."

## Objective
One small piece of code decides whether a line may move from one state to another, and which RatelLink call that move implies. Every move that is not in the Build Plan's table is refused.

## Context
Lines have six states: `awaiting_activation`, `active`, `out_of_data`, `expired`, `suspended`, `terminated`. The Build Plan lists each allowed move and the RatelLink call it needs:

| From | To | When | Call to RatelLink |
| ---- | -- | ---- | ----------------- |
| awaiting_activation | active | first plan paid for and KYC verified | `/activate` with the plan's speeds and voice true |
| active | out_of_data | allowance used up before the plan expires | `/data` with mode slow (plan's slow speeds) or mode off, per `on_exhaustion` |
| out_of_data | active | customer buys a bundle or a new plan | `/data` with mode full and the plan's speeds |
| active or out_of_data | expired | plan validity ends without renewal | `/deactivate` |
| expired | active | customer buys a plan | `/activate` |
| active or out_of_data | suspended | customer care action, with a reason | `/deactivate` |
| suspended | the state it had before | customer care action, with a reason | `/activate`, then `/data` if it was out_of_data |
| any other state | terminated | care action or end of contract | `/deactivate`; SIM retired, number quarantined |

This is a pure rule: it needs no database, no web framework and no network. That is why it is a good first task, and why it goes in the `domain` layer.

## Scope
- A transition table as data, and a function that answers "is this move allowed?" and "what does it imply?".
- An error type for a refused move.
- Handling "suspended goes back to the state it had before" (the previous state is passed in; storing it is a later issue).
- Location: `services/app/bss_lines/domain.py` (or `domain/` if it grows). Tests: `tests/app/bss_lines/domain/test_line_state_machine.py`.

## Out of scope
The database, the API endpoints, calling RatelLink, audit entries, KYC checks, `state_before_suspension` storage. Those are later issues that use this module.

## Dependencies
None. If a row of the table seems ambiguous, ask in this issue before choosing. One known question: "any other state to terminated" - does it include `terminated` itself, and `awaiting_activation`? Propose an answer and ask the project lead.

## Acceptance criteria
- Every row of the table has a passing test.
- A test covers **all 36 pairs of states** and asserts that exactly the allowed pairs pass and every other pair raises the refusal error.
- Each allowed move reports the RatelLink call it implies, and a test checks it.
- The module imports nothing from FastAPI, SQLAlchemy or `ratel_link`.
- `make check` is green.

## Data / integrity requirements
This module is the only place that says what a legal transition is. Nothing else may update a state directly.

## Security / privacy requirements
None. No personal data is involved.

## Testing requirements
Unit tests only. Failure paths are the point: refused moves must be tested as carefully as allowed ones.

## Suggested skill level
Python basics and pytest. A good first task: the spec is a table, the answer is checkable, and the review will teach the flow.
