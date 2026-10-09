# RatelMeter agent: disk spool and ordered replay
Labels: type:feature, area:ratel-meter, priority:p1, risk:high

**Week:** 2 | **Target date:** 2026-10-16 | **Owner:** @ml-lawarn | **Reviewer:** @CaptRaven (mentor: @CaptRaven)
**Source:** Build Plan, RatelMeter "Rules": "Never lose an interval or a call. If the RatelMeter API is unreachable, spool to disk and replay in order." "Done when": taking the API offline for an hour and bringing it back delivers every spooled interval.

## Objective
When the RatelMeter API cannot be reached, batches of records are written to disk and sent later, oldest first, with nothing lost and nothing sent twice by mistake.

## Scope
- A spool directory (`METER_SPOOL_DIR`). One file per interval or batch.
- **Write safely:** write to a temporary file, then rename it, so a crash never leaves a half-written file that looks complete.
- **Replay in order, oldest first.** Delete a file only **after** the API has acknowledged it. (The API upserts on `imsi + period_start`, so a replay overwrites and cannot double count.)
- A file that cannot be read is **moved aside** (kept for a person to look at), never deleted, and replay continues with the next file.
- The sender is passed in as a function. The spool never opens a network connection itself, so tests need no network.
- Location: `services/meter_agent/spool/`. Tests: `tests/meter_agent/spool/`.

## Out of scope
The HTTP client, the schedule that calls the spool, the records themselves (W2-14).

## Dependencies
W2-14 for the record shape (agree it in W2-14 first, or use a plain dict in the tests).

## Acceptance criteria
- With the sender failing, records accumulate on disk; when it works again they arrive in the original order, once each (test with a fake sender and a temporary directory).
- A crash between "written" and "acknowledged" leaves the file on disk, so it is sent again (test).
- A corrupt file is quarantined and does not stop later files (test).
- Two files with the same key replay without error (the API handles the overwrite).
- `make check` is green.

## Data / integrity requirements
Never lose an interval. Replay order is oldest first. Files are written atomically.

## Security / privacy requirements
Records are personal data: no IMSI in logs, spool directory permissions owner-only. Never log file contents.

## Testing requirements
Unit and failure-path tests with a temporary directory and a fake sender. No lab needed for this issue.

## Suggested skill level
Python with file handling and careful error cases.
