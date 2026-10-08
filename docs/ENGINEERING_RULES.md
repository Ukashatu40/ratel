# Engineering rules

These apply to every workstream and every change. Rules marked **[Build Plan]** come straight from
the Build Plan's "Engineering rules" and must not be weakened. Others are team conventions that make
those rules checkable.

## Source control

- **One repository.** The contract is shared, a change to it lands on both sides in the same commit. [Build Plan]
- `main` is protected. No direct pushes, no force pushes, no deleting it. Pull request, passing CI and review are required to merge.
- Squash merge only. No `develop` branch.
- Branch names and PR titles follow [CONTRIBUTING.md](../CONTRIBUTING.md).
- Never rewrite shared history. Never commit secrets, dumps or real data.

## Code review

- One reviewer for most changes. **Two reviewers for RatelLink (keys) and RatelBSS: money.** RatelVoice configuration needs one. [Build Plan]
- The author owns the change. AI-generated code gets the same review as hand-written code. See [CODE_REVIEW_GUIDELINES.md](CODE_REVIEW_GUIDELINES.md).
- The author never approves their own PR. Stale approvals are dismissed on new pushes.

## CI

- CI runs lint, formatting, type checks, unit tests, contract tests (Schemathesis against `openapi.yaml`), secret scan and dependency audit. A red CI blocks merge. Do not disable or skip a check to get green. [Build Plan: lint, unit tests, contract tests]
- A change to CI or branch rules is a governance change: project lead reviews.

## API contracts

- `contracts/openapi.yaml` is the source of truth. If it changes API behavior, it changes in the same commit as the code. [Build Plan]
- Where a component spec and the contract disagree, the contract wins and the spec gets fixed. [Build Plan]
- No endpoint or field exists that is not in the contract. Unknowns are `TODO(contract)`, never guesses.
- Contracts return the standard error shape `{"error": {"code", "message"}}` and carry an API key in `Authorization` (`Authorization: Bearer <key>`), one key per calling system, rotated every 90 days. [Build Plan, [ADR 0007](adr/0007-api-key-verification-and-rotation.md)]
- Until live changes land, nothing in RatelBSS may assume a RatelLink change applies mid-session. It applies at the next attach. [Build Plan]

## Code organisation

- Code lives in layers inside each component: `api` (HTTP), `services` (use cases), `domain` (rules, no I/O), `repositories` (storage), `security` (keys and crypto). Imports flow inward only, with no cycles. Entry points and settings are the only files at a package root. [ADR 0008](adr/0008-code-organisation-inside-components.md)
- No `utils.py`, `helpers.py` or `misc.py` in a component: name a file for what it holds.
- Tests mirror the source tree (`tests/<component>/<layer>/test_<module>.py`).
- `tests/architecture/test_layers.py` fails the build when a layer imports what it may not. Do not weaken it to get green.

## Database changes and migrations

- Schema changes go through Alembic migrations in `services/app/migrations/`, reviewed like code.
- **No manual schema changes in production.** No developer has write access to production databases. [Build Plan]
- Conventions in [DATABASE_AND_MIGRATIONS.md](DATABASE_AND_MIGRATIONS.md). Every migration states its rollback.
- RatelLink's MongoDB documents for Open5GS are built from a template Open5GS created itself. Never handwrite the schema. [Build Plan]

## Data integrity

- **State changes happen only through the state machine**, and each one writes an audit entry saying who made it and why. No code updates a state column directly. [Build Plan]
- **Idempotency.** Every endpoint that changes state or moves money accepts `Idempotency-Key`; repeating a call with the same key returns the first result. RatelLink activation of an active line with the same settings succeeds and changes nothing. [Build Plan]
- **No double counting.** One usage record per line per 300-second interval, keyed `imsi + period_start`. Calls keyed on `call_id`. The API upserts, so a replay overwrites. [Build Plan]
- A rating pass marks a record rated in the same transaction as the deduction. A crash must never rate a record twice. [Build Plan]
- A payment webhook delivered twice credits once (`provider_ref` unique). A voucher redeemed twice credits once. [Build Plan]
- A wallet's balance always equals the sum of its ledger entries. A nightly job checks and alerts on mismatch. [Build Plan]
- SIM inventory cannot be in contradictory allocation states (database constraints, not only code).
- Never lose an interval or a call: the agent spools to disk and replays in order. [Build Plan]
- Where a rule can be a database constraint or a test, make it one. Documentation alone is not enforcement.

## Money

- **Whole kobo, never floating point.** Columns are `BIGINT`; API and Python types are `int`. [Build Plan]
- **The ledger is append-only.** A correction is a new entry, never an edit. [Build Plan]
- Apply VAT at the rate finance confirms and record it as its own ledger entry. TODO: confirm rate with finance (7.5% at the time of writing). [Build Plan]
- Voucher PINs are stored hashed. Mask card and PIN numbers to their last four digits in logs. [Build Plan]

## Time

- **Store and send UTC, as epoch seconds on the wire.** West Africa Time appears only in RatelDesk and RatelPay. [Build Plan]
- Intervals align to the clock (00:00, 00:05, 00:10 ...) in UTC. [Build Plan]
- NTP on every host; every record's key and every call's duration depend on it. [Build Plan]
- No naive datetimes (`ruff` rule DTZ is on).

## Logging and auditability

- Structured JSON logs. Never log keys or full PINs. [Build Plan] Conventions: [LOGGING_AND_OBSERVABILITY.md](LOGGING_AND_OBSERVABILITY.md).
- RatelLink's `audit_log` is append-only and records the calling system's key id for every change. It never contains Ki or OPc. [Build Plan]
- Call records are exported only with a logged reason. [Build Plan]

## Security and privacy

- **Ki and OPc exist only in RatelLink's store and in Open5GS's MongoDB.** Never in PostgreSQL, logs, tickets, chat, test fixtures, AI tools, or backups that leave core-cp unencrypted. [Build Plan] In RatelLink's store they are AES-256-GCM encrypted before persistence, and only RatelLink encrypts or decrypts ([ADR 0006](adr/0006-ki-opc-encryption-at-rest.md)). Any backup containing the `open5gs` database must be encrypted before it leaves core-cp.
- **RatelBSS never holds Ki or OPc.** A SIM import is split: keys go to RatelLink, RatelBSS keeps ICCID, IMSI and batch. [Build Plan]
- **RatelLink is the only writer to RatelCore's subscriber database.** Only RatelLink touches MongoDB, over localhost only. [Build Plan]
- **Every RatelLink `/v1` route requires a valid API key.** Routes are added to `new_v1_router()` so they are protected by default, and a test fails the build if one is not ([ADR 0007](adr/0007-api-key-verification-and-rotation.md)). Only `/healthz` is open.
- **No endpoint returns Ki or OPc, and neither the encryption key nor an API key is ever logged, put in an audit record or echoed in an error.** Sensitive fields are `SecretStr`.
- Customer records and call records are protected personal data. Same access rules for both. [Build Plan]
- Every API and RatelDesk is reachable only over the WireGuard VPN. Public: RatelPay and the payment webhook only. Verify every webhook signature, rate-limit both. [Build Plan]
- Credit a payment only after verifying the webhook signature and re-querying the provider. [Build Plan]
- No line activates until KYC is verified. Exact verification rules are compliance's call. TODO: confirm current NCC SIM registration requirements with compliance before the pilot. [Build Plan]
- Do not weaken security to make development easier. See [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md).

## Secrets

- API keys and RatelLink's encryption key live in files with owner-only permissions on each host, never in the repository. [Build Plan] The encryption key file is checked at startup (a regular file owned by the service user, no group or other access). API keys are stored hashed ([ADR 0006](adr/0006-ki-opc-encryption-at-rest.md), [ADR 0007](adr/0007-api-key-verification-and-rotation.md)).
- There is no default or fallback encryption key. Without a key, RatelLink does not start outside `local` and `test`.
- `.env.example` holds placeholders only. A secret scan runs in CI. A leaked secret is rotated, not just deleted.

## Testing

- Rating, state machines and check digits get unit tests. Contract tests run against `openapi.yaml` in CI. [Build Plan]
- **Anything that touches the network is tested against the lab core, never production.** Unit tests alone do not complete network work. [Build Plan]
- Test data is synthetic. Never real customers, keys or payments. See [TESTING_STRATEGY.md](TESTING_STRATEGY.md).

## Environments

- local, test, lab, staging/pilot, production. See [ENVIRONMENTS.md](ENVIRONMENTS.md).
- The lab is today's core-cp and core-up. TODO: decide before week 7 whether the pilot runs on these machines or new ones. [Build Plan]
- No developer has write access to production databases. [Build Plan]

## Production access, deployment, rollback

- Production changes go through the PR flow. Nobody edits production by hand.
- Configuration for RatelVoice and RatelOps lives in the repository so every change is reviewed and can be rolled back. [Build Plan]
- Every production-running component has a short runbook (health, failure, recovery). [Build Plan] Template: [runbooks/TEMPLATE.md](runbooks/TEMPLATE.md).
- Every deployment names its rollback before it starts. TODO: deployment procedure per host (`deploy/`).

## Scope discipline

- The Build Plan's "What not to build yet" list is binding until after the demo. Anything not needed for the demo waits.
