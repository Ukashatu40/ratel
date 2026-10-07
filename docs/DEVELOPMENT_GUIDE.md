# Development guide

## Local setup

Requirements: Python 3.12, git, make. Optional: Docker (local databases), Node 20+ (mock server).

```
git clone <repo> && cd <repo>
cp .env.example .env          # placeholders only. Choose throwaway local passwords.
make install                  # .venv + pinned dependencies (requirements/constraints.txt)
make check                    # lint, types, tests, contract: must be green before you push
```

No production credentials, real SIM keys or real customer data are ever needed. If something
seems to need them, stop and ask.

Optional local services (bound to 127.0.0.1, passwords from your `.env`): `make up` / `make down`.
The dev MongoDB is a stand-in without an Open5GS schema.

Run a service locally (needs the matching env vars exported, for example `set -a; . ./.env; set +a`):

```
PYTHONPATH=services .venv/bin/uvicorn --factory ratel_link.main:create_app --port 8081
PYTHONPATH=services .venv/bin/uvicorn --factory app.main:create_app --port 8082
curl http://127.0.0.1:8081/healthz
```

Mock of the two contracts for BSS and frontend work: `make mock` (http://127.0.0.1:4010). The mock
requires an `Authorization` header and serves example responses from `contracts/openapi.yaml`.

## Code style

- Python 3.12, type hints everywhere. `mypy --strict` over `services/`.
- `ruff` for lint and format (line length 100). `make format` fixes most things.
- Security-related lint (`S`), naive-datetime lint (`DTZ`) and `print` lint (`T20`) are on. Do not silence them without a comment explaining why.
- Money: `int` kobo, `common.money.Kobo`. Time: UTC, `common.timeutil`. Errors: `common.errors.ApiError`. Logs: `common.logging.log_event`.
- Keep modules small and boring. No new framework or service without an ADR.
- Mind the import rules in [DEPENDENCIES.md](DEPENDENCIES.md). They are tested.

## Branches and commits

```
git switch main && git pull
git switch -c feature/line-state-machine     # feature|fix|refactor|chore|docs|security / short-name
# ... work ...
git add -p && git commit -m "feat: add line state transition table"
git push -u origin feature/line-state-machine
```

PR title follows `type: summary` because merges are squashed. See [CONTRIBUTING.md](../CONTRIBUTING.md).

## Testing

```
make test               # unit tests
make contract           # openapi validity, drift, Schemathesis for implemented operations
make test-integration   # needs make up
pytest -m lab           # lab only; read TESTING_STRATEGY.md first. Never against production.
```

Add a test that fails without your change. Failure paths too. See [TESTING_STRATEGY.md](TESTING_STRATEGY.md).

## Implementing a contract operation

1. Make sure the operation in `contracts/openapi.yaml` has no unresolved `TODO(contract)` you depend on; if it does, ask.
2. Implement the route in the owning service (RatelLink operations in `ratel_link`, `/v1/usage` and `/v1/calls` in `app`).
3. Delete its `operationId` from `contracts/not_implemented.txt` in the same PR.
4. `make contract`: the drift test and Schemathesis now check your route. Fix real disagreements in the code, not by weakening the contract.

## Migrations

See [DATABASE_AND_MIGRATIONS.md](DATABASE_AND_MIGRATIONS.md). Never change production schema by hand.

## Environment variables

Documented in `.env.example` and [ENVIRONMENTS.md](ENVIRONMENTS.md). Add new ones to both, with a
placeholder value, in the same PR.

## Pull requests

Fill the whole template. Run `make check`. Say what you tested and, for network work, what you ran
on the lab. Request the required reviewers (two for RatelLink and RatelBSS: money).

## Review

Respond to every comment. Do not merge with unresolved conversations. Push fixes as new commits;
approvals are dismissed on push, so re-request review. See [CODE_REVIEW_GUIDELINES.md](CODE_REVIEW_GUIDELINES.md).

## Debugging conventions

- Start from the **actual error output**. Reproduce first, with synthetic data; then form a hypothesis; then change one thing.
- Use the `x-request-id` header to follow one request across log lines and services.
- Logs are JSON. Filter with `jq`, for example `... | jq 'select(.event=="http.request" and .status>=500)'`.
- Never paste a secret, Ki/OPc, NIN, real customer data or an unredacted production log into a ticket, chat or AI tool while debugging.
- A bug in network behavior is reproduced on the lab, not guessed from unit tests.
- When you find the cause, write the test first, then the fix.

## Updating pinned dependencies

`requirements/*.txt` declare ranges; `requirements/constraints.txt` pins what was verified.
To upgrade: create a venv, `pip install -r requirements/dev.txt -U`, run `make check` and
`make audit`, then regenerate `constraints.txt` with `pip freeze` (keep its header). Dependabot
opens PRs for this weekly.
