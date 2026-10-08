# RatelLink: line status, assignments and audit entries on writes
Labels: type:feature, area:ratel-link, priority:p0, risk:critical

**Week:** 2 | **Target date:** 2026-10-14 | **Owner:** @Ukashatu40 | **Reviewers:** @CaptRaven + @capitanaserdel (two required)
**Source:** Build Plan, Contract 1 (`GET /v1/lines/{imsi}`, `GET /v1/assignments`), RatelLink spec ("Interfaces", "Rules"), Access rule.

## Objective
RatelBSS can check its view against the network's, RatelMeter can map addresses to IMSIs, and every change is audited with the calling system's key id.

## Context
`GET /v1/lines/{imsi}` returns status, APNs, IP address, speeds and MSISDN, never keys. `GET /v1/assignments` lists every current IP address with its IMSI; RatelMeter's agent caches it and refreshes it every interval. `audit_log`: `at`, `api_key_id`, `action`, `imsi`, `before`, `after`; append-only; never contains `ki` or `opc`. Every call carries an API key as `Authorization: Bearer <key>`, one key per calling system.

**API-key authentication, the audit writer and the key administration CLI are delivered by the security PR** ([ADR 0007](../adr/0007-api-key-verification-and-rotation.md)). This issue applies them; it does not build them.

## Scope
- The two GET endpoints per the contract.
- `audit_log` writes (through `AuditLog.append`, with the caller's `api_key_id`) for every change made by W2-01 and W2-02, if not already added there.
- Put both GET endpoints on `new_v1_router()`. Authentication then applies by default; unknown or missing key gives 401 in the standard error shape (already tested for any route on that router).
- **Schemathesis CI authentication.** RatelLink now rejects every `/v1` request without a valid key, and CI has no backend that accepts `RATEL_TEST_API_KEY`. `scripts/ci/run_schemathesis.sh` already sends `Authorization: Bearer $KEY` and skips everything while nothing is implemented. When the first RatelLink operation is implemented, CI needs a way to seed a test `api_key`: an in-memory test mode or a MongoDB service container (DECISIONS_PENDING.md #19, #20). Do not make the service accept an unauthenticated or fixed key to get CI green.
- Remove `link_get_line` and `link_list_assignments` from `contracts/not_implemented.txt`.

## Out of scope
Rate limiting of failed authentication (Week 6 security review). Live changes. Making `audit_log` append-only inside MongoDB (DECISIONS_PENDING.md #13).

## Dependencies
W2-01, W2-02, and the security PR (authentication, audit writer). `TODO(contract)`: response fields, `apns` shape, assignments wrapper.

## Acceptance criteria
- Response schemas contain no key material (contract conventions test plus a runtime test).
- `assignments` returns every current address with its IMSI, including after deactivate (released) and re-activate.
- Each write produces one audit entry with the calling system's `api_key_id`, and no audit entry ever contains Ki or OPc (test; the guard in `audit.py` also refuses ciphertext and tokens).
- Schemathesis passes for both operations, **including its authentication checks** (the earlier probe showed unauthenticated routes are caught).
- Without a valid key every endpoint returns 401 with `{"error": {"code", "message"}}` and `WWW-Authenticate: Bearer`.

## Data / integrity requirements
Audit log append-only (no update or delete path in code; MongoDB user permissions if possible, TODO decide).

## Security / privacy requirements
One key per calling system (`bss-app`, `meter-agent`); keys outside the repo; keys never logged. The agent calls `GET /v1/assignments` with its own key (`METER_AGENT_RATEL_LINK_API_KEY`), not RatelBSS's. IMSIs are not written to operational logs.

## Testing requirements
Unit, integration, contract. Lab run for `assignments` against real activated lines.

## Suggested skill level
Careful; Python/FastAPI, MongoDB, API authentication basics.
