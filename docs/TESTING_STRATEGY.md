# Testing strategy

Principle from the Build Plan: **anything that touches the network is tested against the lab core,
never production, and is not complete on unit tests alone.** Rating, state machines and check
digits get unit tests. Contract tests run against `openapi.yaml` in CI.

Run everything CI runs with `make check`. Lab and integration tests are excluded by default
(`-m 'not lab and not integration'`).

| Kind | What it proves | Where | Runs in CI |
| ---- | -------------- | ----- | ---------- |
| Unit | Pure logic: rating function, check digits, state transition table, kobo, time, log redaction | `tests/<component>/` | Yes |
| Integration | Code with real PostgreSQL, Redis, MongoDB (local containers). RatelLink's repositories, indexes, the admin CLI and startup checks against a real MongoDB: `tests/ratel_link/repositories/test_mongo_integration.py`, run with `RATEL_TEST_MONGO_URI` set | marker `integration` | **Not yet.** TODO: a MongoDB service container job (a CI change for the project lead) |
| Contract | `openapi.yaml` is valid and follows the conventions; services match it (drift); Schemathesis fuzzes implemented operations | `tests/contract/`, `scripts/ci/run_schemathesis.sh` | Yes |
| Architecture | Import boundaries between components, layer rules inside a component, no import cycles, nothing but entry points at a package root, no float money, production code never imports `tests/` | `tests/architecture/` | Yes |
| Database | Constraints, naming convention, migrations apply and roll back, no manual schema | `tests/app/`, integration | Partly (conventions yes, live DB TODO) |
| State machine | Every transition in the table works; **every transition not in the table is refused** | `tests/app/bss_lines/` (to write) | Yes |
| Idempotency | Same `Idempotency-Key` returns the first result; activating an active line with the same settings changes nothing | per component | Yes |
| Financial / ledger | Wallet balance equals sum of ledger entries; ledger rejects edits; VAT as its own entry; kobo ints | `tests/app/bss_money/` (to write) | Yes |
| Replay | Same usage interval twice counts once; same call twice appears once; webhook twice credits once; voucher twice credits once | per component | Yes |
| Failure-path | API down: agent spools and replays in order; crash mid-rating rates nothing twice; counter reset counts from zero; malformed input rejected | per component | Yes |
| Security | No Ki/OPc or API key in logs (session guard); errors do not echo input; localhost-only Mongo; secrets scan; dependency audit | `tests/common/`, `tests/ratel_link/`, `security.yml` | Yes |
| Crypto | Round trip; tampered ciphertext, tag, nonce fail; a ciphertext moved to another IMSI, from `ki` to `opc`, or to another `kid` fails; wrong or unknown key fails closed; 10,000 nonces are unique; wrong key length rejected; no secret in any exception | `tests/ratel_link/security/test_crypto.py`, `test_key_provider.py`, `tests/ratel_link/services/test_sim_keys.py` | Yes |
| Authentication | Every rejection case gives the same 401; rotation overlap, revocation, expiry and the 90-day ceiling, on an injected clock; comparison goes through `hmac.compare_digest` for every generation; the key never reaches a log line | `tests/ratel_link/services/test_authentication.py`, `test_api_key_admin.py`, `tests/ratel_link/api/test_auth_http.py`, `tests/ratel_link/test_admin_cli.py` | Yes |
| Route protection (ratchet) | Walks the real app: every `/v1` route requires an API key, every other route is allowlisted. The checker is proven able to fail on an unprotected route | `tests/ratel_link/api/test_route_protection.py`, `tests/route_walk.py` | Yes |
| SIM import and addresses | The endpoint end to end (created, unchanged, conflict, 401 first, 422, 503, audit failure); key comparison in constant time; the allocator (unique, 24-hour hold, own address back, exhausted pool, lost races); atomic claims and concurrency on real MongoDB | `tests/ratel_link/api/test_sims.py`, `services/test_sim_import.py`, `services/test_ip_allocation.py`, `domain/test_ip_pool.py`, `repositories/test_mongo_integration.py` | Yes (integration job for the MongoDB part) |
| Deployment files and database privileges | RatelLink does its whole job with exactly the MongoDB privileges in the roles file, and every operation outside them is refused (change or delete a stored key, read or change the audit log, delete a subscriber, any other collection or database); the unit keeps its hardening; the settings template covers every setting; no file holds a secret or a real address; the proxy log omits paths | `tests/ratel_link/repositories/test_mongo_roles_integration.py`, `tests/tooling/test_deploy_files.py`. The full install was also run once in a clean Linux container (install, start, use, upgrade, rollback), by hand | Yes for the MongoDB part. **A first install on core-cp is still the real test** |
| Activate, data and deactivate | Speed conversion; the exact document and its BSON types; HSS-owned fields survive; `internet` first; calling untouched by every data change; repeats change nothing; nothing written on any failure; auth first; strict input; deactivate deletes one document only, keeps the keys, releases the address and is repeatable; tests on real MongoDB including simultaneous requests | `tests/ratel_link/domain/test_subscriber.py`, `services/test_line_activation.py`, `services/test_data_mode.py`, `services/test_line_deactivation.py`, `repositories/test_voice_template.py`, `api/test_line_operations.py`, `repositories/test_mongo_integration.py` | Yes (integration job for MongoDB), and **the lab run is still required** |
| Line status and assignments | Status for unknown, provisioned and stored lines; the 24-hour hold in the address list; numeric order; auth before IMSI validation; no key in any response; MongoDB round trips and concurrent writes | `tests/ratel_link/api/test_lines_and_assignments.py`, `services/test_line_status.py`, `services/test_assignments.py`, `domain/test_line_state.py`, `repositories/test_mongo_integration.py` | Yes (integration job for the MongoDB part) |
| Audit | Append-only interface (insert only); content guard rejects forbidden fields at any depth; failed authentication writes no audit entry | `tests/ratel_link/services/test_audit_log.py` | Yes |
| RatelLink acceptance (W2-04) | The document RatelLink writes matches a template field for field, type for type, apart from the line's own values (and the comparison is proven able to fail: 16 deliberate breaks); the same on the types MongoDB stores; **no Ki, OPc or caller key in any log of a real RatelLink process (debug level), its admin command line, or the database outside the core**, after a full life of a line and every failure; the MongoDB driver is kept quiet at any log level; the search itself is proven able to fail | `tests/ratel_link/acceptance/` (the template comparison also runs against the network team's export when `RATEL_LINK_TEMPLATE_COMPARE_FILE` is set) | Yes. The process and database tests need MongoDB (integration job) |
| Network / lab | Real behavior against core-cp/core-up: line created through RatelLink attaches and browses; subscriber document matches the Open5GS template field for field; counters match within 1% | `tests/lab/`, marker `lab` | **No.** Run by a developer on the lab; record the result in the PR |
| Frontend | RatelDesk journeys against the mock API; RatelPay page weight and load time on 3G | `web/` | Yes once `package.json` exists |
| Regression | Every fixed bug gets a test that fails without the fix | with the fix | Yes |

## Conventions

- Test data is synthetic (`tests/synthetic.py`). Never real customers, keys, NINs or payments.
- Keys in tests use the sentinels `SENTINEL_KI`, `SENTINEL_OPC` and `SENTINEL_API_KEY`. If any reaches the captured test log, the whole run fails (`tests/conftest.py`). Valid-format fake Ki and OPc for the store are `SYNTHETIC_KI_HEX` and `SYNTHETIC_OPC_HEX`, and **they are searched for too, in both cases** (the core's document holds them in upper case). A test that talks to MongoDB itself with the keys in a query or a document must keep the driver's logger quiet (`tests/ratel_link/acceptance/conftest.py`), because the driver copies documents into the log at DEBUG; RatelLink does this in its own process and a test proves it.
- Tests mirror the source tree: `services/ratel_link/<layer>/x.py` is tested in `tests/ratel_link/<layer>/test_x.py`. Shared helpers for the authentication tests are in `tests/ratel_link/helpers.py`.
- In-memory fakes for RatelLink's repositories are in `tests/ratel_link/fakes.py`. They are test code and production code never imports them. Time is injected (`FakeClock`), so no test sleeps.
- Route walking in tests goes through `tests/route_walk.py`, because current FastAPI does not list included routers in `app.routes`.
- A test must be able to fail. Where a rule is a checker (contract conventions, boundaries, schema rules), there is a test showing the checker catches a deliberately broken input.
- Contract ratchet: `contracts/not_implemented.txt` lists operations not built yet. Implementing one means removing its line in the same PR; the drift test and Schemathesis then pick it up.
- Mock for independent development: `make mock` serves the contract (Prism). BSS developers code against it; the mock is not a test of RatelLink.

## Lab testing

Lab tests need `core-cp` and `core-up` reachable and are never pointed at production. Mark them
`@pytest.mark.lab`. Record in the PR: date, what ran, what you saw. Required for: RatelLink
activation (template match, attach, browse, registration), RatelMeter accuracy (within 1% of
interface counters), anything that changes a subscriber document. TODO: lab access and credentials
handled outside the repo.

## Acceptance tests from the Build Plan (to automate or run by hand)

- RatelLink: a test searches every log file after a full test run and finds no Ki or OPc value.
- RatelMeter: stopping the agent mid-interval and restarting loses nothing and counts nothing twice; API offline for an hour then back delivers every spooled interval and call.
- BSS lines: sell-to-activate produces exactly one `/activate` call; tests prove every transition not in the table is refused.
- BSS money: a webhook delivered twice and a voucher redeemed twice each credit exactly once; nightly wallet-vs-ledger check alerts on mismatch.
