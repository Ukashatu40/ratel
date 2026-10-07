# RatelLink: SIM key store and POST /v1/sims
Labels: type:feature, area:ratel-link, priority:p0, risk:critical

**Week:** 2 | **Target date:** TODO (by Oct 8) | **Owner:** TODO | **Reviewers:** TODO + TODO (two required)
**Source:** Build Plan, Contract 1, RatelLink spec ("What it owns", "Data it keeps", "Rules"), Week 1 RatelLink bullets.

## Objective
SIM keys are stored in RatelLink, encrypted at rest, with no service created. RatelBSS never sees them.

## Context
Ki and OPc live only on the network side. `POST /v1/sims` takes `imsi`, `ki`, `opc` and "stores the SIM's keys in RatelLink. No service yet." `sim_key` fields: `imsi` (unique), `ki`, `opc`, `amf`, `created_at`; `ki` and `opc` encrypted at rest, with the key held outside the database. The Week 2 gate needs real SIM keys imported this way.

## Scope
- `ratel_link` MongoDB database with its own user; `sim_key` collection with unique `imsi`.
- Encryption of `ki` and `opc` at rest; key read from a file outside the database (`RATEL_LINK_KEY_FILE`).
- `POST /v1/sims` per the contract, idempotent, standard error shape.
- Remove `link_create_sim` from `contracts/not_implemented.txt`.

## Out of scope
Activation (W2-02). Key rotation tooling. Anything in RatelBSS. Returning keys from any endpoint, ever.

## Dependencies
- **Decision needed first:** encryption approach and key file format (docs/DECISIONS_PENDING.md, open question 1). Write the ADR.
- **Decision needed:** how API keys are verified (open question 2).
- `TODO(contract)`: `ki`/`opc`/`amf` format; whether `amf` is part of the request.
- MongoDB authentication on and bound to 127.0.0.1 (network team, Week 1). Confirm before any real key is imported.
- SIM keys settled with the supplier (network team, Week 2). Use synthetic keys until then.

## Acceptance criteria
- A stored document's `ki` and `opc` are not plaintext (test reads the raw document).
- Startup fails clearly if the key file is missing or unreadable; the key is never in MongoDB, logs or the repo.
- No endpoint returns Ki or OPc; the contract has no response field for them (existing contract check).
- Repeating the call with the same `Idempotency-Key` returns the first result; storing the same IMSI again does not create a second document.
- The suite-wide Ki/OPc sentinel guard stays green (nothing writes keys to logs).
- Schemathesis passes for `link_create_sim`.

## Data / integrity requirements
Unique `imsi`. Idempotent. Audit entry per write (without keys) with the calling key id.

## Security / privacy requirements
Write-only secrets. Local-only MongoDB. Never log request bodies. Synthetic keys in tests (`tests/synthetic.py`).

## Testing requirements
Unit and integration (local MongoDB with auth). Lab run when real keys are available, by the owner, with the project lead present.

## Operational requirements
Runbook note for ratel-link (health, restart, key file location and permissions: owner-only).

## Suggested skill level
Careful and security-minded. Python/FastAPI, MongoDB, applied cryptography basics. The Build Plan says this owner should be the most careful developer, not the fastest.
