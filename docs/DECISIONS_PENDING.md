# Decisions and TODOs that need the project lead

Nothing here was decided silently except where marked "assumed", and assumptions are reversible.

## Decisions I made as proposals (change them if you disagree)

| # | Decision | Where | Why |
| - | -------- | ----- | --- |
| 1 | Layout follows the Build Plan tree (`services/app/{bss_lines,bss_money,meter_api}`), not your sketch (`services/bss_lines` ...), because the Build Plan says RatelBSS, the RatelMeter API and the front ends are modules of **one process**. `ops/` is top level, as in your sketch (the Build Plan's tree is ambiguous about `ops/` and `network/`). | [ADR 0001](adr/0001-repository-layout.md) | Do not silently reinterpret the architecture |
| 2 | Dependencies: plain `requirements/*.txt` plus a verified `constraints.txt`, `pip` and `make`. No Poetry or uv. | [ADR 0002](adr/0002-python-dependency-management.md) | Boring and auditable. Easy to change later. |
| 3 | A tiny `services/common/` library (error shape, JSON logging with redaction, UTC time, kobo). | [ADR 0003](adr/0003-shared-common-package.md) | Those rules must be identical in both deployables. It is a library, not a service. Approve or fold into each service. |
| 4 | Two-reviewer rule enforced by a `critical-review-gate` workflow, since CODEOWNERS accepts any one owner. | [ADR 0004](adr/0004-two-reviewer-enforcement.md) | GitHub cannot express "2 for these paths" natively. Verified on PR #10: it works on review events. It ran with an empty `critical-reviewers.txt` until 2026-10-08, so the independent reviewer did not review that PR (see item 26). |
| 5 | `contracts/not_implemented.txt` ratchet and a Prism mock. | [ADR 0005](adr/0005-contract-ratchet-and-mock.md) | Makes drift visible while nothing is implemented yet. |
| 6 | Squash-merge only, ruleset with **no bypass actors**. | [GITHUB_SETUP.md](GITHUB_SETUP.md) | Trunk-based, tidy history. Decide whether you want an emergency bypass. |
| 7 | `docs/source/Ratelplus_Build_Plan.pdf` was committed so teammates can read it. It contains internal LAN addresses and business plans. **The repo is public** (rulesets need it on a free plan), so the PDF was untracked on 2026-10-08 and is shared privately. It remains in Git history. | [source/README.md](source/README.md), [GITHUB_SETUP.md](GITHUB_SETUP.md) | Decide: accept the exposure, rewrite history (force push, forbidden by the ruleset), or pay for GitHub Pro and go private. Risk R-15. |
| 8 | Validation failures return **422** (FastAPI default) in the standard error shape. | `contracts/openapi.yaml` | Build Plan says "standard HTTP status codes" without specifying. |

## Decided

| Date | Decision | Where |
| ---- | -------- | ----- |
| 2026-10-07 | **RatelLink encryption at rest for Ki and OPc** (was open question 1): AES-256-GCM envelope with a key id and per-record associated data, key in an owner-only file outside MongoDB, a replaceable `KeyProvider`, `cryptography` as the one new dependency, no default or fallback key. | [ADR 0006](adr/0006-ki-opc-encryption-at-rest.md) |
| 2026-10-07 | **How RatelLink verifies API keys** (was open question 2): `Authorization: Bearer <key>`, one key per calling system with an internal `api_key_id`, only a SHA-256 hash stored, generic 401, 90-day lifetime with rotation by key generations, no new auth protocol. | [ADR 0007](adr/0007-api-key-verification-and-rotation.md) |

## Open questions that block or shape work (not decided, not guessed)

1. *(Decided on 2026-10-07: see "Decided" above. The numbering is kept so other documents that cite these questions stay correct.)*
2. *(Decided on 2026-10-07: see "Decided" above.)*
3. **Contract gaps** (`TODO(contract)` in `openapi.yaml`): POST response bodies, `ki`/`opc`/`msisdn` formats, speeds integer or decimal, `reason` values, `end_reason` values, `from`/`to` semantics, cursor parameter name, `apns` shape, assignments response shape, `Idempotency-Key` format and retention.
4. **Where two more APIs are specified:** the agent's ingest call to the RatelMeter API, and RatelBSS's own API for RatelDesk/RatelPay (the Build Plan says frontend developers code against "a mock of the API"). Neither is in the two frozen contracts.
5. **BSS money reading RatelMeter data:** over the HTTP contract or an in-process interface, since both run in the `app` process.
6. **What happens to a line when RatelLink fails mid-transition** (state, retry, alert). Not specified in the Build Plan.
7. **Append-only ledger mechanism:** database permissions, triggers or both.
8. **Staff authentication** and roles for RatelDesk (not specified in the Build Plan).
9. **Versions:** PostgreSQL, Redis and the lab's MongoDB; dev containers use 16, 7 and 7 as placeholders.
10. **Pilot environment:** the lab machines or new ones (decide before week 7).
11. **GitHub plan:** rulesets on private repos need a paid plan. The repo is public today for that reason (item 7). Deciding to pay (GitHub Pro on the owner account, or an organization plan) is what allows a private repo with enforced rules.

### Raised by the encryption and API-key work (2026-10-07)

12. **SIM re-import with different keys (W2-01).** `SimKeyStore.put_if_absent` returns `False` for an existing IMSI and never overwrites, whatever keys arrive. What `POST /v1/sims` should answer when the IMSI exists with the same keys (idempotent success) and with different keys (conflict, or replace?) is not decided. Not decided silently.
13. **Append-only `audit_log` in MongoDB itself.** The code offers insert only, but a database user that may only insert into `audit_log` is not set up. Decide with the network team.
14. **Ki and OPc format.** The code accepts exactly 32 hexadecimal characters (128 bits) for each, in one place (`models.py`). This is an assumption: the contract still says `TODO(contract)`. The project lead and the network team confirm it, then the contract is updated in the same commit as any change. Also confirm the case to store (the code keeps the case it was given).
15. **`amf` handling.** The Build Plan's `sim_key` lists `amf`; the contract's `SimImport` does not. It is not stored. Decide whether it is part of the request, and its default.
16. **Overlap and warning defaults.** API key rotation overlap 7 days (allowed 1 to 30) and expiry warning 14 days (allowed 1 to 90) are proposals. The 90-day lifetime is the Build Plan's.
17. **Encryption key file: backup procedure and owner, and its path on core-cp.** The key needs a separate, secure, offline backup that is never stored with database backups. Nobody owns this yet. Required before the first real SIM key is imported (risk R-14).
18. **Backup encryption for the `open5gs` database.** Open5GS keeps Ki and OPc in plaintext there, so any backup containing it must be encrypted before leaving core-cp (network team, Week 6, risk R-06). Mechanism and location are TODO.
19. **CI authentication for Schemathesis (W2-03).** RatelLink now rejects every `/v1` call without a valid key, and no CI backend accepts the test key. When the first RatelLink operation is implemented, CI needs a way to seed a test `api_key`: an in-memory test mode or a MongoDB service container. Nothing is skipped silently today because nothing is implemented.
20. **MongoDB integration tests in CI.** `tests/ratel_link/test_integration_mongo.py` runs against the compose MongoDB locally. CI does not run integration tests yet. A MongoDB service container job is a CI change for the project lead.
21. **Rate limiting of failed authentication.** Not built. Revisit with the Week 6 security review.
22. **Operating the API keys.** A scheduled `api-key check-expiry` and who is alerted; delivery of a new key to a caller (by hand today); whether a disabled system needs an `enable` command; concurrent administration (not safe for two operators at once).
23. **Encryption key rotation and KMS.** Re-encrypting records under a new key (the `kid` makes it possible) and any KMS or secret manager are out of scope for now.
24. **Contract security scheme.** `ApiKeyAuth` changed from an `apiKey` header named `Authorization` to `http` with scheme `bearer` (same name, same header, standard form), and the 401 description now says "Bearer". No new fields. The project lead and the RatelBSS developers confirm.
25. **`cryptography` on Intel Macs.** Releases from 49 on have no Intel-Mac wheels, and earlier ones have open advisories (`pip-audit`), so the pin is 50. On an Intel Mac `make install` needs a Rust toolchain. Decide whether that is acceptable or the team develops in a Linux container.

### Raised while finishing the team setup (2026-10-08)

26. **Independent review of PR #10.** The RatelLink key code (encryption, API keys, audit, CLI) was merged with approvals from @capitanaserdel and @Abbalolo because `critical-reviewers.txt` was empty and `CODEOWNERS` was still commented out. @CaptRaven has not reviewed it. Ask for that review before any real SIM key is imported, using the "RatelLink / critical changes" checklist in [CODE_REVIEW_GUIDELINES.md](CODE_REVIEW_GUIDELINES.md).
27. **Backup for RatelLink and BSS money.** Both critical backends have one owner and no backup (risk R-08). A second person who can read and change them, and who is not the independent reviewer, is not identified yet.
28. **Network team and network lead.** Whether @CaptRaven is the network lead the Build Plan describes, and who else is on the network team, is not recorded. `OWNERSHIP_MATRIX.md` still says "Network team (TODO name)" for RatelVoice, RatelOps and RatelCore.
29. **RatelMeter agent owner (W2-09).** Suggested pairing: @ml-lawarn with @CaptRaven. Not assigned.
30. **Week 2 capacity.** The Week 2 gate is Oct 9. Several issues had target dates of Oct 7 and Oct 8 and have no work started. Three spikes (W2-05, W2-06, W2-08) are assigned to @CaptRaven, who is also on the network team (risk R-10). Re-plan with the owners.
31. **GitHub housekeeping for the project lead.** Turn on "Automatically delete head branches"; run `gh auth refresh -s project` before `create_project.sh` or listing the project; run `scripts/github/create_issues.sh` once after reviewing the issue files (it now assigns owners).

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
