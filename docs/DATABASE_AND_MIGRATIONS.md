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
- `ratel_link` database (own MongoDB user), collections:
  - `sim_key`: unique `imsi`, `ki` and `opc` (each an encrypted envelope `{v, alg, kid, nonce, ct}`, never plaintext), `created_at` (UTC). No `amf`: it is an open contract TODO. [ADR 0006](adr/0006-ki-opc-encryption-at-rest.md)
  - `api_key`: unique `api_key_id`, `system_name`, `status` (`active` or `disabled`), `generations` (`generation`, `secret_hash`, `created_at`, `expires_at`, `revoked_at`), `created_at`. Hashes only. Documents are never deleted. [ADR 0007](adr/0007-api-key-verification-and-rotation.md)
  - `audit_log`: `at`, `api_key_id`, `action`, `imsi`, `before`, `after`. Insert only: the code has no update or delete path, and a guard refuses Ki, OPc, ciphertext and tokens. **TODO (project lead):** enforce append-only in MongoDB too, with a user that may only insert into `audit_log`.
  - `ip_allocation`: unique `ue_ip` and unique `imsi` (an address belongs to one line, a line holds one address), `state` (`active` or `released`), `allocated_at`, `released_at`. Claims are single atomic MongoDB operations, so two activations at the same moment cannot get the same address. A released address is taken over by another line only after 24 hours.
  - `line_state` (W2-02).
- The `open5gs` database is touched only for subscriber documents. Build each document from a template taken from a subscriber Open5GS created itself (with the ims APN). Never handwrite the schema.
- Indexes (unique `sim_key.imsi`, `api_key.api_key_id`, `ip_allocation.ue_ip` and `ip_allocation.imsi`) are created by an explicit, idempotent command, never as an automatic side effect: `python -m ratel_link.admin_cli init-db`, run on core-cp as the service user. At startup RatelLink only checks for them and logs `startup.indexes.missing` as an error. No manual changes in production.
- Storing the same IMSI again never creates a second document or overwrites the first.
