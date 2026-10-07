# RatelPlus Subscriber Platform

The business and network software behind Ratelplus's own LTE network: provisioning, usage
metering, subscribers, charging, wallets, vouchers, payments and the staff and customer screens.

**Objective.** On **November 26, 2026**, a line sold in RatelDesk browses on LTE, makes VoLTE
calls, is charged for its data, and is topped up on RatelPay, all on real SIMs.

**Current phase: Week 2 of 8 (Oct 5 to Oct 9).** Week 2 gate: *a real SIM, created through
RatelLink, attaches, browses and registers for calls.* See [docs/ROADMAP.md](docs/ROADMAP.md).

## Authoritative documents

1. The Ratel Plus Subscriber Platform PRD (product behavior). Not in this repo yet, see [docs/source/README.md](docs/source/README.md).
2. [docs/source/Ratelplus_Build_Plan.pdf](docs/source/Ratelplus_Build_Plan.pdf) (the how). Where the PRD and the Build Plan disagree about the product, the PRD wins.
3. [contracts/openapi.yaml](contracts/openapi.yaml) (the two cross-system contracts). Where a component spec and the contract disagree, the contract wins.
4. [docs/ENGINEERING_RULES.md](docs/ENGINEERING_RULES.md) (rules that apply to every change).

## What we build

| Component | What it is | Lives in |
| --------- | ---------- | -------- |
| RatelLink | Provisioning API. The only writer to RatelCore's subscriber database. Holds SIM keys. | `services/ratel_link/` |
| RatelMeter | Agent (core-up and voice) plus an API that serves `/v1/usage` and `/v1/calls`. | `services/meter_agent/`, `services/app/meter_api/` |
| RatelBSS: lines | Customers, SIM and number stock, plans, bundles, lines and their state machine. | `services/app/bss_lines/` |
| RatelBSS: money | Rating job, allowances, wallets, ledger, vouchers, payments. | `services/app/bss_money/` |
| RatelDesk | Staff web app (React, TypeScript). | `web/desk/` |
| RatelPay | Public top-up page, light enough for 3G. | `web/pay/` |

The **network team** owns RatelCore, RatelVoice and RatelOps (configuration in `network/` and
`ops/`). The software team never writes to the network except through RatelLink, and never reads
from it except through RatelMeter. Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Three deployables: `ratel-link` (core-cp), `meter-agent` (core-up and voice), `app` (bss-app).
Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL, Redis, and the MongoDB driver
for RatelLink. React and TypeScript for RatelDesk. No Kubernetes, no message bus, no extra
microservices.

## Repository layout

```
contracts/openapi.yaml    the two contracts, source of truth (+ not_implemented.txt ratchet)
services/
  common/                 shared error shape, JSON logging, UTC time, kobo (no business logic)
  ratel_link/             deploys to core-cp
  meter_agent/            data mode on core-up, call mode on voice
  app/                    one process on bss-app
    bss_lines/ bss_money/ meter_api/ migrations/
web/desk/  web/pay/       RatelDesk, RatelPay (README only for now)
network/voice/            RatelVoice configuration (network team)
ops/                      RatelOps configuration (network team)
deploy/                   per-host deployment files: core-cp core-up voice bss-app ops
tests/                    unit, contract, architecture and tooling tests; lab/ for lab-only tests
docs/                     rules, architecture, roadmap, runbooks, ADRs, Week 2 issues
.github/                  CI, templates, CODEOWNERS, labels, branch ruleset
scripts/                  CI helpers and GitHub setup helpers
```

## Local setup

Requires Python 3.12. Docker is optional (only for local PostgreSQL, Redis and MongoDB).

```
cp .env.example .env        # local placeholders only; pick throwaway passwords
make install                # creates .venv, installs pinned dependencies
make check                  # lint, types, tests, contract checks (what CI runs)
make mock                   # serves contracts/openapi.yaml on http://127.0.0.1:4010 (needs Node)
make up                     # optional: local PostgreSQL, Redis, MongoDB (127.0.0.1 only)
```

You never need production credentials, real SIM keys or real customer data to develop here.
Full guide: [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md).

## Testing

`make test` runs unit tests (no databases). `make contract` validates `openapi.yaml`, checks it
against the services, and runs Schemathesis on implemented operations. Anything that touches the
network must also be shown working against the **lab** core (`tests/lab/`, marker `lab`); unit
tests alone do not make network work done. See [docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md).

## Contributing

Issue, branch, implementation, tests, pull request, review, CI, merge. No direct pushes to `main`.
Read [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/DEFINITION_OF_DONE.md](docs/DEFINITION_OF_DONE.md).
RatelLink and RatelBSS: money changes need **two reviewers**.

## Security expectations

Ki and OPc never appear in PostgreSQL, logs, tickets, chat, test fixtures, AI prompts or
unencrypted backups outside core-cp. RatelBSS never holds them. Money is whole kobo. The ledger is
append-only. Time is UTC. Report vulnerabilities privately, see [SECURITY.md](SECURITY.md) and
[docs/SECURITY_AND_PRIVACY.md](docs/SECURITY_AND_PRIVACY.md).

## AI assistants

Allowed as assistants, never as owners. You answer for every line you merge. Never send secrets,
Ki/OPc, NINs, real customer records or production logs to an AI tool. See
[docs/AI_ENGINEERING_POLICY.md](docs/AI_ENGINEERING_POLICY.md) and [CLAUDE.md](CLAUDE.md).

## Status of this scaffold

Foundation only: project layout, tooling, CI, contract, governance and docs. No business logic
is implemented. Open decisions and TODOs are listed in [docs/DECISIONS_PENDING.md](docs/DECISIONS_PENDING.md).
