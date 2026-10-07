# Testing strategy

Principle from the Build Plan: **anything that touches the network is tested against the lab core,
never production, and is not complete on unit tests alone.** Rating, state machines and check
digits get unit tests. Contract tests run against `openapi.yaml` in CI.

Run everything CI runs with `make check`. Lab and integration tests are excluded by default
(`-m 'not lab'`).

| Kind | What it proves | Where | Runs in CI |
| ---- | -------------- | ----- | ---------- |
| Unit | Pure logic: rating function, check digits, state transition table, kobo, time, log redaction | `tests/<component>/` | Yes |
| Integration | Code with real PostgreSQL, Redis, MongoDB (local containers) | marker `integration` | TODO: service containers once the first exist |
| Contract | `openapi.yaml` is valid and follows the conventions; services match it (drift); Schemathesis fuzzes implemented operations | `tests/contract/`, `scripts/ci/run_schemathesis.sh` | Yes |
| Architecture | Import boundaries, no float money | `tests/architecture/` | Yes |
| Database | Constraints, naming convention, migrations apply and roll back, no manual schema | `tests/app/`, integration | Partly (conventions yes, live DB TODO) |
| State machine | Every transition in the table works; **every transition not in the table is refused** | `tests/app/bss_lines/` (to write) | Yes |
| Idempotency | Same `Idempotency-Key` returns the first result; activating an active line with the same settings changes nothing | per component | Yes |
| Financial / ledger | Wallet balance equals sum of ledger entries; ledger rejects edits; VAT as its own entry; kobo ints | `tests/app/bss_money/` (to write) | Yes |
| Replay | Same usage interval twice counts once; same call twice appears once; webhook twice credits once; voucher twice credits once | per component | Yes |
| Failure-path | API down: agent spools and replays in order; crash mid-rating rates nothing twice; counter reset counts from zero; malformed input rejected | per component | Yes |
| Security | No Ki/OPc in logs (session guard); errors do not echo input; localhost-only Mongo; secrets scan; dependency audit | `tests/common/`, `tests/ratel_link/`, `security.yml` | Yes |
| Network / lab | Real behavior against core-cp/core-up: line created through RatelLink attaches and browses; subscriber document matches the Open5GS template field for field; counters match within 1% | `tests/lab/`, marker `lab` | **No.** Run by a developer on the lab; record the result in the PR |
| Frontend | RatelDesk journeys against the mock API; RatelPay page weight and load time on 3G | `web/` | Yes once `package.json` exists |
| Regression | Every fixed bug gets a test that fails without the fix | with the fix | Yes |

## Conventions

- Test data is synthetic (`tests/synthetic.py`). Never real customers, keys, NINs or payments.
- Keys in tests use the sentinels `SENTINEL_KI` and `SENTINEL_OPC`. If either reaches the captured test log, the whole run fails (`tests/conftest.py`).
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
