# RatelLink: line status, assignments, audit log and API-key authentication
Labels: type:feature, area:ratel-link, priority:p0, risk:critical

**Week:** 2 | **Target date:** TODO (by Oct 8) | **Owner:** TODO | **Reviewers:** TODO + TODO (two required)
**Source:** Build Plan, Contract 1 (`GET /v1/lines/{imsi}`, `GET /v1/assignments`), RatelLink spec ("Interfaces", "Rules"), Access rule.

## Objective
RatelBSS can check its view against the network's, RatelMeter can map addresses to IMSIs, and every change is audited with the calling system's key id.

## Context
`GET /v1/lines/{imsi}` returns status, APNs, IP address, speeds and MSISDN, never keys. `GET /v1/assignments` lists every current IP address with its IMSI; RatelMeter's agent caches it and refreshes it every interval. `audit_log`: `at`, `api_key_id`, `action`, `imsi`, `before`, `after`; append-only; never contains `ki` or `opc`. Every call carries an API key in `Authorization`, one key per calling system.

## Scope
- The two GET endpoints per the contract.
- `audit_log` writes for every change made by W2-01 and W2-02.
- API-key authentication on every endpoint; unknown or missing key gives 401 in the standard error shape.
- Remove `link_get_line` and `link_list_assignments` from `contracts/not_implemented.txt`.

## Out of scope
Key rotation tooling. Rate limiting (revisit with the security review in Week 6). Live changes.

## Dependencies
W2-01, W2-02. **Decision needed:** API key storage, hashing and header format (docs/DECISIONS_PENDING.md, open question 2). `TODO(contract)`: response fields, `apns` shape, assignments wrapper.

## Acceptance criteria
- Response schemas contain no key material (contract conventions test plus a runtime test).
- `assignments` returns every current address with its IMSI, including after deactivate (released) and re-activate.
- Each write produces one audit entry with the calling key id, and no audit entry ever contains Ki or OPc (test).
- Schemathesis passes for both operations, **including its authentication checks** (the earlier probe showed unauthenticated routes are caught).
- Without a valid key every endpoint returns 401 with `{"error": {"code", "message"}}`.

## Data / integrity requirements
Audit log append-only (no update or delete path in code; MongoDB user permissions if possible, TODO decide).

## Security / privacy requirements
One key per calling system; keys outside the repo; keys never logged. IMSIs are not written to operational logs.

## Testing requirements
Unit, integration, contract. Lab run for `assignments` against real activated lines.

## Suggested skill level
Careful; Python/FastAPI, MongoDB, API authentication basics.
