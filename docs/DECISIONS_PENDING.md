# Decisions and TODOs that need the project lead

Nothing here was decided silently except where marked "assumed", and assumptions are reversible.

## Decisions I made as proposals (change them if you disagree)

| # | Decision | Where | Why |
| - | -------- | ----- | --- |
| 1 | Layout follows the Build Plan tree (`services/app/{bss_lines,bss_money,meter_api}`), not your sketch (`services/bss_lines` ...), because the Build Plan says RatelBSS, the RatelMeter API and the front ends are modules of **one process**. `ops/` is top level, as in your sketch (the Build Plan's tree is ambiguous about `ops/` and `network/`). | [ADR 0001](adr/0001-repository-layout.md) | Do not silently reinterpret the architecture |
| 2 | Dependencies: plain `requirements/*.txt` plus a verified `constraints.txt`, `pip` and `make`. No Poetry or uv. | [ADR 0002](adr/0002-python-dependency-management.md) | Boring and auditable. Easy to change later. |
| 3 | A tiny `services/common/` library (error shape, JSON logging with redaction, UTC time, kobo). | [ADR 0003](adr/0003-shared-common-package.md) | Those rules must be identical in both deployables. It is a library, not a service. Approve or fold into each service. |
| 4 | Two-reviewer rule enforced by a `critical-review-gate` workflow, since CODEOWNERS accepts any one owner. | [ADR 0004](adr/0004-two-reviewer-enforcement.md) | GitHub cannot express "2 for these paths" natively. Verify on the first real PR. |
| 5 | `contracts/not_implemented.txt` ratchet and a Prism mock. | [ADR 0005](adr/0005-contract-ratchet-and-mock.md) | Makes drift visible while nothing is implemented yet. |
| 6 | Squash-merge only, ruleset with **no bypass actors**. | [GITHUB_SETUP.md](GITHUB_SETUP.md) | Trunk-based, tidy history. Decide whether you want an emergency bypass. |
| 7 | `docs/source/Ratelplus_Build_Plan.pdf` is committed so tools and teammates can read it. It contains internal LAN addresses. | [source/README.md](source/README.md) | **Confirm the repo is private**, or remove the file. |
| 8 | Validation failures return **422** (FastAPI default) in the standard error shape. | `contracts/openapi.yaml` | Build Plan says "standard HTTP status codes" without specifying. |

## Open questions that block or shape work (not decided, not guessed)

1. **RatelLink encryption at rest** for Ki and OPc: algorithm, library, key file format, rotation. The Build Plan only says encrypted at rest with the key held outside the database. Needs an ADR before W2-01 can be finished. Choose carefully.
2. **How RatelLink verifies API keys** (storage, hashing, rotation every 90 days, one key per calling system) and what the `Authorization` header carries (bare key or a scheme prefix).
3. **Contract gaps** (`TODO(contract)` in `openapi.yaml`): POST response bodies, `ki`/`opc`/`msisdn` formats, speeds integer or decimal, `reason` values, `end_reason` values, `from`/`to` semantics, cursor parameter name, `apns` shape, assignments response shape, `Idempotency-Key` format and retention.
4. **Where two more APIs are specified:** the agent's ingest call to the RatelMeter API, and RatelBSS's own API for RatelDesk/RatelPay (the Build Plan says frontend developers code against "a mock of the API"). Neither is in the two frozen contracts.
5. **BSS money reading RatelMeter data:** over the HTTP contract or an in-process interface, since both run in the `app` process.
6. **What happens to a line when RatelLink fails mid-transition** (state, retry, alert). Not specified in the Build Plan.
7. **Append-only ledger mechanism:** database permissions, triggers or both.
8. **Staff authentication** and roles for RatelDesk (not specified in the Build Plan).
9. **Versions:** PostgreSQL, Redis and the lab's MongoDB; dev containers use 16, 7 and 7 as placeholders.
10. **Pilot environment:** the lab machines or new ones (decide before week 7).
11. **GitHub plan:** rulesets on private repos need a paid plan.

## Information I did not have (TODOs in the files)

- GitHub usernames: project lead, independent reviewer, workstream owners, frontend lead, network lead (`CODEOWNERS`, `critical-reviewers.txt`, ownership and team docs).
- The PRD (not in the repo), its location, and who owns it.
- Production host details, deployment credentials handling, backup encryption and location.
- Network-team contact and escalation channel.
- Payment provider (the Build Plan says one gateway).
- Compliance-approved KYC rules, NCC SIM registration requirements, number quarantine period, data retention, VAT confirmation from finance.
- The Open5GS subscriber document **template** (must come from a subscriber Open5GS created, with the ims APN) and the `ims` pool.
- A private contact for security reports (`SECURITY.md`), and response timelines.
- Whether the Week 1 items (merged contract, MongoDB auth, `subscriber_status` barring test, line flow against the mock) are done. The Week 2 issues say "TODO confirm" where they depend on them.
- Existing application code, CI and repository contents: this setup started from an empty directory and could not see your real repository.
