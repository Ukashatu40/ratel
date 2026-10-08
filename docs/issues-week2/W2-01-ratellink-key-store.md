# RatelLink: SIM key store and POST /v1/sims
Labels: type:feature, area:ratel-link, priority:p0, risk:critical

**Week:** 2 | **Target date:** 2026-10-09 | **Owner:** @Ukashatu40 | **Reviewers:** @CaptRaven + @capitanaserdel (two required)
**Source:** Build Plan, Contract 1, RatelLink spec ("What it owns", "Data it keeps", "Rules"), Week 1 RatelLink bullets.

## Objective
SIM keys are stored in RatelLink, encrypted at rest, with no service created. RatelBSS never sees them.

## Context
Ki and OPc live only on the network side. `POST /v1/sims` takes `imsi`, `ki`, `opc` and "stores the SIM's keys in RatelLink. No service yet." `sim_key` fields: `imsi` (unique), `ki`, `opc`, `amf`, `created_at`; `ki` and `opc` encrypted at rest, with the key held outside the database. The Week 2 gate needs real SIM keys imported this way.

## Already delivered (security PR: key encryption and API-key authentication)
Do not rebuild these. This issue builds on them.
- The encrypted SIM key store: `SimKeyStore.put_if_absent(imsi, ki, opc)` encrypts before persisting and never overwrites; `get_keys` decrypts (for W2-02 only). AES-256-GCM envelope, key from `RATEL_LINK_KEY_FILE`, startup fails closed outside local/test. See [ADR 0006](../adr/0006-ki-opc-encryption-at-rest.md).
- `SimImport` request model (`ki` and `opc` as `SecretStr`, exactly 32 hex characters: an assumption, see DECISIONS_PENDING.md #14), the `sim_key` Mongo repository and the unique-`imsi` index (`admin_cli init-db`).
- API-key authentication on `new_v1_router()`, so any route added there needs a valid `Authorization: Bearer <key>`. See [ADR 0007](../adr/0007-api-key-verification-and-rotation.md).
- The audit writer `AuditLog.append(action, imsi, before, after, api_key_id)` with its content guard.

## Scope
- `POST /v1/sims` on `new_v1_router()` per the contract: validate with `SimImport`, call `SimKeyStore.put_if_absent`, write an audit entry (no keys) with the caller's `api_key_id` (from the `ApiPrincipal`), standard error shape.
- Idempotency: `Idempotency-Key` handling, and a repeated import of the same IMSI.
- The response when the IMSI already exists **with different keys** is not decided (DECISIONS_PENDING.md #12). Propose an answer to the project lead before building it. `put_if_absent` only returns whether it stored.
- Remove `link_create_sim` from `contracts/not_implemented.txt`.

## Out of scope
Activation (W2-02). Re-encryption or rotation tooling for the encryption key, and any KMS. Anything in RatelBSS. Returning keys from any endpoint, ever.

## Dependencies
- Encryption and API-key verification are decided and built (ADR 0006 and 0007).
- `TODO(contract)`: `ki`/`opc` format (the code assumes 32 hex characters, DECISIONS_PENDING.md #14) and whether `amf` is part of the request (#15).
- An API key for the test caller (`admin_cli api-key create`, see the runbook).
- MongoDB authentication on and bound to 127.0.0.1 (network team, Week 1). Confirm before any real key is imported.
- SIM keys settled with the supplier (network team, Week 2). Use synthetic keys until then.

## Acceptance criteria
- A stored document's `ki` and `opc` are not plaintext (test reads the raw document). Already covered by `tests/ratel_link/test_sim_keys.py` and `test_integration_mongo.py`; the endpoint test repeats it through `POST /v1/sims`.
- Startup fails clearly if the key file is missing or unreadable; the key is never in MongoDB, logs or the repo. Already covered by `tests/ratel_link/test_key_provider.py`.
- `POST /v1/sims` without a valid key is 401, including with an invalid or malformed body (the route-protection and authentication tests keep passing).
- No endpoint returns Ki or OPc; the contract has no response field for them (existing contract check).
- Repeating the call with the same `Idempotency-Key` returns the first result; storing the same IMSI again does not create a second document.
- The suite-wide Ki/OPc sentinel guard stays green (nothing writes keys to logs).
- Schemathesis passes for `link_create_sim`.

## Data / integrity requirements
Unique `imsi`. Idempotent. Audit entry per write (without keys) with the calling system's `api_key_id`.

## Security / privacy requirements
Write-only secrets. Local-only MongoDB. Never log request bodies. Synthetic keys in tests (`tests/synthetic.py`).

## Testing requirements
Unit and integration (local MongoDB with auth). Lab run when real keys are available, by the owner, with the project lead present.

## Operational requirements
The ratel-link runbook exists ([runbooks/ratel-link.md](../runbooks/ratel-link.md)). Keep it current. Its key file backup procedure and owner are still TODO and must be settled before a real key is imported.

## Suggested skill level
Careful and security-minded. Python/FastAPI, MongoDB, applied cryptography basics. The Build Plan says this owner should be the most careful developer, not the fastest.
