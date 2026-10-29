# ADR 0012: Changes to one line take turns, and the line stays locked while RatelLink answers

- **Status:** Proposed (written 2026-10-28 for the project lead to accept or change)
- **Date:** 2026-10-28
- **Deciders:** the project lead
- **Related:** [PRODUCT_RULES.md](../PRODUCT_RULES.md) (Line lifecycle), [ADR 0009](0009-ledger-append-only-in-the-database.md)

## Context

Every change to a line (activate, suspend, reinstate, terminate, and the rating job's out of
data, expire and restore) loads the line, checks the state machine, calls RatelLink, then writes
the new state and an audit entry. Nothing stopped two of them running at once. A test on a real
PostgreSQL showed two activations of one line, with different `Idempotency-Key`s, both
succeeding: two RatelLink calls and two audit entries. SQLite hides this because it has no row
locks. The same gap existed for every other change, and for staff against the rating job.

## Decision

Loading a line to change it (`LinesRepository.get`) takes `SELECT ... FOR UPDATE` and holds the
row until the transaction ends. Two changes to one line take turns, and the second sees the
state the first left, so the state machine refuses what no longer applies.

The lock is held **across the RatelLink call**. RatelLink's client times out after 5 seconds, so
a stuck RatelLink delays other changes and purchases on that one line by at most about that long.
The rating job's own transactions still end before they call RatelLink; the lock is taken by the
lifecycle flow it then calls.

## Alternatives considered

| Option | Why not |
| ------ | ------- |
| Compare the state when writing (`UPDATE ... WHERE state = from_state`), no long lock | RatelLink has already been called by then. Suspend and activate racing could leave the network and RatelBSS disagreeing, and the loser's call cannot be undone. |
| Lock only while checking, call RatelLink after releasing | The same disagreement: the state checked may be stale when the call is made. |
| A Redis lock per line | A second system to keep right, and not tied to the transaction that writes the state. |

## Consequences

- Correct under concurrency, proven on PostgreSQL (`tests/app/bss_money/api/test_desk_postgres_integration.py`,
  `tests/app/bss_money/services/test_rating_concurrency_postgres_integration.py`).
- A purchase for a line waits while that line is being changed. A slow RatelLink is felt by that
  line's customer and nobody else's.
- A same-key repeat that races the first is still stopped by the state machine, not by the key.

## Security implications

None new. It prevents a line being left in a state the network does not match.

## Data implications

The audit trail stays a chain: each entry's `from_state` is the previous entry's `to_state`.

## Operational implications

If changes to a line seem stuck, look at RatelLink first. See `docs/runbooks/bss-lines.md`.
