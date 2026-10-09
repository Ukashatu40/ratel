# RatelMeter agent: interval alignment and counter delta logic (pure functions)
Labels: type:feature, area:ratel-meter, priority:p1, risk:high, good first issue

**Week:** 2 | **Target date:** 2026-10-13 | **Owner:** @ml-lawarn | **Reviewer:** @CaptRaven (mentor: @CaptRaven, with @Ukashatu40 for Python questions)
**Source:** Build Plan, RatelMeter spec "How data works" and "Rules": align intervals to the clock in UTC, never double count, handle counter resets, skip intervals with zero bytes.

## Objective
The rules that turn two counter readings into one correct 300-second record exist as small, tested functions, before any code reads real counters.

## Scope
- **Interval alignment.** Given a reading time (epoch seconds, UTC), return the interval `period_start` and `period_end`, aligned to 00:00, 00:05, 00:10 and so on. Use `common.timeutil.interval_start`; do not write the arithmetic again.
- **Increase between readings.** Given the previous reading and the current one for one address (`bytes_up_total`, `bytes_down_total`), return the increase. **If the current total is lower than the previous one, the host restarted: the new reading counts from zero** (the increase is the new reading), never a negative number.
- **Skip zero.** An interval with zero bytes up and zero bytes down produces no record.
- **Record shape.** `imsi`, `period_start`, `period_end`, `bytes_up`, `bytes_down`, as integers. A record is keyed on `imsi + period_start`, so the same interval always produces the same key.
- Location: `services/meter_agent/domain/` (pure; no file, network or database access). Tests: `tests/meter_agent/domain/`.

## Out of scope
Reading real counters (W2-08, W2-09). Mapping address to IMSI. The disk spool (W2-15). The API. Call mode.

## Dependencies
`common.timeutil` (exists). **Open question to settle before coding that part:** what happens on the very first reading, when there is no previous reading? The Build Plan does not say. Proposal: store it as the baseline and count zero for that interval, so nothing is ever double counted. Ask @CaptRaven and the project lead, and write the answer in this issue.

## Acceptance criteria
- Alignment: readings on, just before and just after an interval boundary land in the right interval (tests for 299, 300, 301 seconds past a boundary).
- Increase: normal case, equal readings (zero), a reset (lower reading) all tested. No negative value is ever returned (a property-style test over many random pairs is welcome).
- A replayed interval produces the same key and the same values.
- Zero-byte intervals produce no record.
- All numbers are integers, times are UTC epoch seconds.
- `make check` is green.

## Data / integrity requirements
Never lose an interval, never double count. These functions are where that is decided, so test the edges.

## Security / privacy requirements
IMSIs are personal data: never log them. These functions do not log at all.

## Testing requirements
Unit tests, including failure and edge cases. No lab needed.

## Suggested skill level
Python with careful thinking about numbers and time. Pairs well with someone who knows Linux counters (@CaptRaven).
