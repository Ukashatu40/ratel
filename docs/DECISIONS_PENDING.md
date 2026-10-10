# Decisions and TODOs that need the project lead

Nothing here was decided silently except where marked "assumed", and assumptions are reversible.

## Decision queue (2026-10-09): what the project lead decides next, with a suggestion for each

The project lead decides all of these. "Suggested" is a recommendation, not a decision. Older items
keep their numbers below; this queue is ordered by urgency.

### A. Decide now (they block work, or they are security-sensitive)

| # | Decision | Suggested | Why now |
| - | -------- | --------- | ------- |
| 1 | The **public** addresses of core-cp, core-up and voice (102.214.x.x) are in this **public** repository since PR #12. Keep them? | Remove them from the documents (names only; addresses stay in the privately shared Build Plan). Do not rewrite history: the exposure happened and addresses cannot be changed. Ask the network team to confirm the hosts' firewalls deny inbound by default and that MongoDB and SSH are not reachable from the internet. | These are the hosts that hold every SIM key |
| 2 | **Access without the VPN** (management, 2026-10-08): RatelLink sits behind a TLS reverse proxy on a public address. Who confirms the design, and what does it include? | Proxy allows `/v1` only from bss-app and the meter-agent hosts, TLS only, **rate limit on failed authentication at the proxy now** (not Week 6), host firewall default-deny, MongoDB on 127.0.0.1 with authentication. Verified by the network lead before any real SIM key. Risk R-16. | The API key is the only credential left between the internet and the key store |
| 3 | **Week 2 gate** cannot pass on Oct 9. Tell management, and set the new date? | Tell management today: the gate moves to Oct 14 to 16 (the Build Plan allows "next week if keys are not ready"). The Nov 26 demo date does not move. | Honest reporting; the next weeks assume the gate |
| 4 | `POST /v1/sims` for an IMSI that **already exists** (W2-01, open item 12) | Same keys: 200, nothing changes. Different keys: **409 conflict, never overwrite.** Changing a SIM's keys becomes a deliberate admin action later. | Blocks the W2-01 endpoint |
| 5 | **Who is the network contact** for the Open5GS template, MongoDB authentication, SIM key status and the radio? | Name one person. Fallback: the lead makes the template on the lab (W2-02 now says how). | Everything on the critical path waits on it |
| 6 | **Backup** for RatelLink and BSS money (risk R-08) | `capitanaserdel` (already the second approver, so must know the code). **Not** `CaptRaven`: if he also maintains it he can no longer review it independently. Goal: by Week 4 he can make a small RatelLink change that you and `CaptRaven` review. | One person cannot be a single point of failure for the keys |
| 7 | Turn **"Require review from Code Owners"** back on in the ruleset | Yes, now. `CODEOWNERS` no longer deadlocks you. | It was switched off to merge #11 |
| 8 | W2-06 date | **Decided:** keep Oct 9 if possible, else Oct 13. It needs the lab, so Oct 13 is the hard date. | Recorded |

### B. Decide this week (they shape the next issues)

| # | Decision | Suggested |
| - | -------- | --------- |
| 9 | **`Idempotency-Key`** for RatelLink (the contract leaves format and retention open) | Accept the header on every state-changing call. `POST /v1/sims` is already idempotent by design. For `activate`, `data`, `deactivate`: store key and first response in `ratel_link.idempotency` for 24 hours; the key is an opaque string of 1 to 128 characters. |
| 10 | **Contract field formats** (W2-12) | `ki`, `opc`: 32 hex characters (confirm with the SIM supplier). `msisdn`: digits only, like `2340000000001` (confirm with the Kamailio side). Speeds: a decimal number of Mbps (slow plans need fractions). `reason` on `/deactivate`: one of `expired`, `suspended`, `terminated`, taken from the Build Plan's state table. Validation errors stay 422. `amf`: ask the network team; do not store until decided. |
| 11 | **Payment provider** (one gateway, with a sandbox) | Pick one that has a sandbox and signed webhooks and is usable for naira payments (Paystack and Flutterwave are the common choices; check fees and availability). Nobody can start gateway work until this is chosen. |
| 12 | **The BSS API** that RatelDesk and RatelPay call (open item 4) | `Abbalolo` (BSS lines) and `capitanaserdel` (the consumer) draft it, you approve. It needs the PRD. |
| 13 | **Staff authentication** for RatelDesk (open item 8) | Decide after reading the PRD. A simple default: staff accounts in PostgreSQL, hashed passwords, server-side sessions. |
| 14 | Who writes the **rating function** in Week 3 | `capitanaserdel`, after W2-16. It is money, so you and `CaptRaven` both review it, and the gate enforces that. |
| 15 | The meter agent's **first reading** (W2-14): no previous reading exists | Store it as the baseline and count zero for that interval, so nothing is ever double counted. Confirm with `CaptRaven`. |
| 16 | **Failure in the middle of a transition** (open item 6) | The line's state does not change, the call is retried with the same `Idempotency-Key`, and an alert fires after repeated failure. Decide at W2-11. |

### C. Before the first real SIM key is imported

| # | Decision | Suggested |
| - | -------- | --------- |
| 17 | **Encryption key file**: path, owner, offline backup (R-14, open item 17) | Path `/etc/ratel-link/ratel_link.key`, mode 0600, owned by the service user. Owner of the key: you. Backup: two offline encrypted copies held by two named people, never with the database backups, and a restore tested once on the lab before the first real key. |
| 18 | **Insert-only `audit_log`** in MongoDB (open item 13) | Use a MongoDB custom role that can only insert into `audit_log`. I can write the exact `mongosh` script (with the other least-privilege roles RatelLink needs) into `deploy/core-cp/` for the network lead to review and apply. |
| 19 | **Encrypting backups of the `open5gs` database** (open item 18) | Encrypt on core-cp before the backup leaves it, with `age` or GPG. Network team, Week 6 at the latest. |
| 20 | **CI for MongoDB and Schemathesis** (open items 19, 20) | Add a MongoDB service-container job with W2-01. In it, create a test key with `admin_cli api-key create` and pass it as `RATEL_TEST_API_KEY`. No special test mode in the service. |
| 21 | **Operating the API keys** (open item 22) | A daily `api-key check-expiry` on a systemd timer, owned by you; alert through RatelOps later. Add an `enable` command when first needed. |

### D. Can wait (with a suggestion)

| # | Decision | Suggested |
| - | -------- | --------- |
| 22 | Repository **public or private**, and the Build Plan in history (R-15) | Accept for now. Move to private when GitHub Pro is affordable, then re-run `apply_ruleset.sh`. Do not rewrite history during Week 2. |
| 23 | ADR status: 0001 to 0005 and 0008 are still "Proposed" | Mark them Accepted. They are in use. |
| 24 | `cryptography` pin 50 and Intel Macs (open item 25) | Accept. Use a Linux container or install a Rust toolchain on an Intel Mac. |
| 25 | `ApiKeyAuth` is now `http`/`bearer` in the contract (open item 24) | Accept. |
| 26 | Append-only ledger mechanism, and how BSS money reads RatelMeter (open items 5, 7) | Database triggers plus permissions for the ledger; an in-process interface for usage data (same process), keeping the HTTP shape. Decide when each is built. |
| 27 | **Outside the software team:** NCC SIM registration and KYC rules, number quarantine period, data retention, VAT rate | Compliance and finance. Ask now; the Week 6 security review and the pilot depend on them. |
| 28 | Pilot environment (lab or new machines), PostgreSQL, Redis and MongoDB versions, GitHub plan (open items 9, 10, 11) | Decide before Week 7. |

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
14. **Ki and OPc format.** The code accepts exactly 32 hexadecimal characters (128 bits) for each, in one place (`domain/sim_keys.py`). This is an assumption: the contract still says `TODO(contract)`. The project lead and the network team confirm it, then the contract is updated in the same commit as any change. Also confirm the case to store (the code keeps the case it was given).
15. **`amf` handling.** The Build Plan's `sim_key` lists `amf`; the contract's `SimImport` does not. It is not stored. Decide whether it is part of the request, and its default.
16. **Overlap and warning defaults.** API key rotation overlap 7 days (allowed 1 to 30) and expiry warning 14 days (allowed 1 to 90) are proposals. The 90-day lifetime is the Build Plan's.
17. **Encryption key file: backup procedure and owner, and its path on core-cp.** The key needs a separate, secure, offline backup that is never stored with database backups. Nobody owns this yet. Required before the first real SIM key is imported (risk R-14).
18. **Backup encryption for the `open5gs` database.** Open5GS keeps Ki and OPc in plaintext there, so any backup containing it must be encrypted before leaving core-cp (network team, Week 6, risk R-06). Mechanism and location are TODO.
19. **CI authentication for Schemathesis (W2-03).** RatelLink now rejects every `/v1` call without a valid key, and no CI backend accepts the test key. When the first RatelLink operation is implemented, CI needs a way to seed a test `api_key`: an in-memory test mode or a MongoDB service container. Nothing is skipped silently today because nothing is implemented.
20. **MongoDB integration tests in CI.** `tests/ratel_link/repositories/test_mongo_integration.py` runs against the compose MongoDB locally. CI does not run integration tests yet. A MongoDB service container job is a CI change for the project lead.
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
