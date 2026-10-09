# RatelLink: acceptance test suite
Labels: type:feature, area:ratel-link, priority:p1, risk:critical

**Week:** 2 | **Target date:** 2026-10-15 | **Owner:** @Ukashatu40 | **Reviewers:** @CaptRaven + @capitanaserdel (two required)
**Week:** 2 | **Target date:** TODO (by Oct 9) | **Owner:** @Ukashatu40 | **Reviewers:** @CaptRaven + @capitanaserdel (two required)
**Source:** Build Plan, RatelLink spec "Done when".

## Objective
The Build Plan's three "Done when" statements for RatelLink exist as repeatable tests.

## Scope
1. A line created through the API attaches through our radio, browses, and registers for calls (manual lab procedure, recorded; automated parts where possible). Depends on W2-07.
2. Its Open5GS document matches the template field for field, apart from its own values (automated, `lab` marker plus a local template-comparison unit test).
3. A test searches every log file after a full test run and finds no Ki or OPc value. The sentinel guard in `tests/conftest.py` covers the pytest log (Ki, OPc and API-key sentinels); extend it to RatelLink's process logs and any log files written by integration tests.

## Out of scope
New features.

## Dependencies
W2-01 to W2-03. Open5GS template from the network team. Radio joined RatelCore on Friday (Network team).

## Acceptance criteria
- Items 2 and 3 run in CI or `make check` (item 2 locally against a stored synthetic template fixture, and on the lab for real).
- Item 1 has a dated record in the PR or `docs/` of who ran it, on which SIM (identifier by last digits only), and the result.
- The log search proves it can fail: a deliberate sentinel in a scratch log makes it red.

## Security / privacy requirements
Use sentinel values or lab-issued test SIMs. No real subscriber data in fixtures. Never paste real Ki/OPc into the issue, PR or chat.

## Suggested skill level
Testing mindset; Python, pytest; comfortable on the lab.
