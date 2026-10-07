# Database and migrations

Applies to PostgreSQL on bss-app (SQLAlchemy 2 + Alembic). RatelLink uses MongoDB directly and has
its own rules, below.

## PostgreSQL / Alembic

Foundation: `services/app/db.py` (naming convention, `TimestampMixin`), `services/app/alembic.ini`,
`services/app/migrations/`. Every model module is imported in `services/app/models.py`.

```
DATABASE_URL=... alembic -c services/app/alembic.ini revision --autogenerate -m "add sim table"
DATABASE_URL=... alembic -c services/app/alembic.ini upgrade head
make migrate-heads        # offline, no database needed
```

### Conventions

- **Never change the schema by hand, in any environment that matters. Not in production, ever.** Schema changes are migrations, in review, applied by the deploy.
- **Names.** Lowercase `snake_case`, singular table names (`sim`, `line`, `ledger_entry`). Constraint names come from the naming convention in `db.py` (`pk_`, `fk_`, `uq_`, `ix_`, `ck_`); do not override them. Migration files: `YYYYMMDD_<rev>_<slug>.py`.
- **Autogenerate is a draft.** Read it, edit it, and check it. It misses renames and some constraints.
- **One concern per migration.** Small and reversible. State the rollback in the file header. If a migration cannot be reversed (dropping data), say so in the PR and take a backup first.
- **Transactions.** Each migration runs in its own transaction (`transaction_per_migration`). Do not mix data backfills with large locking DDL in one step.
- **Primary keys** on every table. Use surrogate keys unless a natural key is the Build Plan's key (for example `msisdn`, `iccid`).
- **Foreign keys** declared, with an explicit `ON DELETE` choice. Prefer `RESTRICT`. Records the business must keep (ledger, audit) are never cascade-deleted.
- **Unique constraints carry business rules.** `usage_record (imsi, period_start)`, `call_record (call_id)`, `payment (provider_ref)`. These make replays safe. Do not rely on application checks alone.
- **Check constraints** for invariants the database can state: non-negative balances where applicable, valid state values, `ck_*_amount_kobo` integer ranges, allocation consistency for SIM and number stock.
- **Indexes.** Add for lookups the Build Plan requires (find a line by MSISDN, ICCID or IMSI in under a second). Name via convention. Do not index speculatively.
- **Timestamps.** `timestamptz` only, UTC. Use `TimestampMixin` (`created_at`, `updated_at`). Epoch seconds are an API wire format, not a column type.
- **Money.** `BIGINT` kobo. Never `FLOAT`, `REAL`, `NUMERIC` for money. A test fails the build if a `*_kobo` column is not `BIGINT` (`tests/app/test_db_conventions.py`).
- **Append-only tables** (`ledger_entry`, audit entries): enforce with database permissions or triggers that reject `UPDATE` and `DELETE`, not only with code. TODO: decide the mechanism when the ledger migration is written.
- **State columns** are changed only by the state machine code path, which also writes the audit entry in the same transaction.
- **Audit records.** `who`, `why`, `before`, `after`, `at`. Never contain Ki, OPc or PINs.
- **Order of deploys.** Backward-compatible migration first, then code that uses it, then clean up. Never ship a migration and code that must change together without saying how to roll back.
- **No real data in tests or fixtures.** Tests that need PostgreSQL use `compose.dev.yaml`.

### Review checklist for a migration

- Does it match the issue and the model? Is the downgrade real?
- Locks: could it block writes on a large table? How long?
- Constraints and indexes named by convention?
- Does it touch money, ledger or audit tables? Then two reviewers.
- Tested on a copy of the schema from `main` (upgrade, then downgrade, then upgrade).

## MongoDB (RatelLink only)

- Only RatelLink touches MongoDB, over `127.0.0.1`, authentication on. Config validation enforces localhost.
- `ratel_link` database (own MongoDB user): `sim_key` (unique `imsi`, `ki`, `opc`, `amf`, `created_at`; Ki and OPc encrypted at rest, key held outside the database), `line_state`, `audit_log` (append-only, never Ki/OPc).
- The `open5gs` database is touched only for subscriber documents. Build each document from a template taken from a subscriber Open5GS created itself (with the ims APN). Never handwrite the schema.
- Indexes and unique constraints on `imsi` are created by RatelLink's startup or an explicit reviewed script. TODO: decide the mechanism with the RatelLink owner. No manual changes in production.
