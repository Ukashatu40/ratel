# ADR 0005: Contract drift ratchet and mock server

- **Status:** Proposed (needs project lead approval)
- **Date:** 2026-10-06
- **Related:** Build Plan "Day one: openapi.yaml and a mock server", "CI runs ... Schemathesis"; [DECISIONS_PENDING.md](../DECISIONS_PENDING.md) #5

## Context

The Build Plan wants the contract merged first, a mock so BSS developers do not wait, and CI that
fails when code and contract drift. At setup time no endpoint is implemented, so Schemathesis would
have nothing valid to test, yet the contract must already be protected.

## Decision

- `contracts/openapi.yaml` (OpenAPI 3.1) holds both contracts, tagged `RatelLink` and `RatelMeter`.
- `contracts/not_implemented.txt` lists operationIds nobody implements yet. `tests/contract/test_drift.py` fails if a service exposes a route the contract lacks, if a listed operation is implemented, or an unlisted one is not. Schemathesis (`scripts/ci/run_schemathesis.sh`) fuzzes only operations not listed.
- Static convention checks on the contract (API key auth, `Idempotency-Key` on state-changing calls, error shape, no `ki`/`opc` in responses, integer epoch times, 5,000 record cap) are tests that are themselves proven able to fail.
- The mock is Prism (`make mock`) serving the contract.

## Alternatives considered

| Option | Why not |
| ------ | ------- |
| Run Schemathesis against the mock | Tests the contract against itself, proves nothing about code. |
| Generate the contract from FastAPI | The Build Plan says the contract is the source of truth and wins over the code. |
| Skip contract tests until endpoints exist | Drift starts on day one. |

## Consequences

Implementing an endpoint means a one-line deletion in `not_implemented.txt` in the same PR.
Prism needs Node (developers already have it). Unspecified details stay `TODO(contract)`.

## Security implications

Schemathesis checks authentication enforcement and error leakage on implemented operations.

## Data implications

The contract fixes epoch-second integer times and byte units on the wire.

## Operational implications

CI job `contract`. Mock is for local development only.
