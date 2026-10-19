# ADR 0009: The ledger is append-only in the database itself

- **Status:** Proposed. The project lead accepts or changes it. It governs money, so two reviewers (the critical-review gate).
- **Date:** 2026-10-19
- **Deciders:** Project lead
- **Related:** Build Plan, RatelBSS: money ("Ledger and wallet"); [DATABASE_AND_MIGRATIONS.md](../DATABASE_AND_MIGRATIONS.md), which left this mechanism as a TODO "when the ledger migration is written"; module issue M-15 (#61); [ADR 0008](0008-code-organisation-inside-components.md)

## Context

The Build Plan says the ledger is append-only and that a wallet's balance always equals the sum of
its entries. Code that never updates a row is not a guarantee: a later change, a hand-run query or
a migration mistake can still edit or delete one. The database doc asked for enforcement "with
database permissions or triggers", and left the choice to this change.

## Decision

1. **Triggers refuse changes.** On `ledger_entry`, a row trigger refuses every `UPDATE` and `DELETE`,
   and a statement trigger refuses `TRUNCATE` (row triggers do not see it). Each raises an integrity
   error whose message says the ledger is append-only. They apply to the table's owner and to a
   superuser too.
2. **A wallet cannot be removed while it has entries.** `ledger_entry.line_id` is a foreign key to
   `wallet.line_id` with `ON DELETE RESTRICT`.
3. **A replayed event is one entry.** `(line_id, kind, reference)` is unique, so a payment or voucher
   posted twice (a retry, a duplicate webhook) cannot credit twice. A purchase and its VAT share a
   reference and differ by kind.
4. **Corrections are new entries.** Nothing is edited. A mistake is fixed by posting an entry of kind
   `correction` that reverses it.
5. **The wallet is kept in step by one statement.** Posting inserts the entry and then adds its
   amount to the wallet in a single `UPDATE ... SET balance = balance + amount`, inside one
   savepoint. Two postings to one line at the same moment cannot lose one. A nightly check
   (`python -m app.bss_money.check_cli`) compares every wallet with the sum of its entries and exits
   non-zero on any difference.
6. **The migration will not drop a ledger that holds entries.** `downgrade()` refuses while
   `ledger_entry` has any row; a ledger with real entries is restored from a backup.

## Why triggers, not privileges alone

Privileges would be the stronger wall, but they need separate database roles: one for the
application (insert and select only) and another for migrations. Those roles do not exist yet; they
belong to the bss-app deployment (M-27). Triggers work now, in every environment and in the tests,
and cost nothing at runtime that matters.

## What this does not stop

A database superuser or the table's owner can still drop or disable a trigger (`ALTER TABLE ...
DISABLE TRIGGER`, `session_replication_role = replica`) or change the files on disk. The triggers
stop mistakes and application bugs. They do not stop a malicious administrator.

The second layer is TODO(project lead, M-27): in production the application connects as a role with
`SELECT` and `INSERT` on `ledger_entry` and nothing else, migrations run as a different role, and
backups leave the host. Someone who edits both a wallet and the ledger consistently is not caught
by the nightly check; that residual risk is accepted for the demo and recorded here.

## Still open (nothing here invents them)

- **TODO(PRD): the entry kinds.** `top_up`, `purchase`, `vat` and `correction` are provisional. The
  ledger is append-only, so a wrong kind could never be edited afterwards: **no real entry may be
  written until the PRD fixes the list.**
- **TODO(finance): VAT.** The rate (7.5% when the Build Plan was written) and whether prices include
  it. VAT is its own entry; this change records it and does not compute it.
- **TODO(PRD): may a wallet go negative?** Nothing here forbids it. The purchase flow decides.
- **TODO(M-25): foreign keys** from `line_id` to the `line` table and from `source_id` to the plan
  and bundle tables, once the bss_lines schema is merged.

## Consequences

- The guarantees are proved on a real PostgreSQL (`tests/app/bss_money/repositories/test_sql_postgres_integration.py` and `tests/app/bss_money/test_check_cli_postgres_integration.py`),
  not only in SQLite. They run when `RATEL_TEST_POSTGRES_URI` is set. **CI's integration job has no
  PostgreSQL service yet, so those tests are skipped there** until the project lead approves adding
  one (a CI change).
- Every future money table follows the same pattern: constraints that state the rule, a trigger where
  a row must never change, and a test that tries to break it.

## Alternatives considered

- **Permissions only.** Needs the production roles first; no protection in tests or before M-27.
- **Application code only.** What the Build Plan describes, and exactly what a bug defeats.
- **A hash chain over the entries.** Detects tampering by an administrator too, but it is more
  machinery than the demo needs. Worth revisiting before real customer money.
