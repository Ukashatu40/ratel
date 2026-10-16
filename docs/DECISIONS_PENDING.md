# Decisions and TODOs that need the project lead

Nothing here was decided silently except where marked "assumed", and assumptions are reversible.

> **2026-10-12:** the network team's three documents arrived. What they settle, and what is still missing (N1 to N8, with who can supply each), is in [RATELCORE_INTEGRATION_FACTS.md](RATELCORE_INTEGRATION_FACTS.md).

## Decision queue (2026-10-09): what the project lead decides next, with a suggestion for each

The project lead decides all of these. "Suggested" is a recommendation, not a decision. Older items
keep their numbers below; this queue is ordered by urgency.

### A. Decide now (they block work, or they are security-sensitive)

| # | Decision | Suggested | Why now |
| - | -------- | --------- | ------- |
| 1 | **Decided 2026-10-10: remove.** The public addresses of the three core hosts were in this public repository from PR #12 to this change. | Remove them from the documents (names only; addresses stay in the privately shared Build Plan). Do not rewrite history: the exposure happened and addresses cannot be changed. Ask the network team to confirm the hosts' firewalls deny inbound by default and that MongoDB and SSH are not reachable from the internet. | These are the hosts that hold every SIM key |
| 2 | **Access without the VPN** (management, 2026-10-08): RatelLink sits behind a TLS reverse proxy on a public address. Who confirms the design, and what does it include? | **Decided 2026-10-10: as suggested.** Proxy allows `/v1` only from bss-app and the meter-agent hosts, TLS only, **rate limit on failed authentication at the proxy now** (not Week 6), host firewall default-deny, MongoDB on 127.0.0.1 with authentication. Verified by the network lead before any real SIM key. Risk R-16. | The API key is the only credential left between the internet and the key store |
| 3 | **Week 2 gate** cannot pass on Oct 9. Tell management, and set the new date? | **Decided 2026-10-10: as suggested.** Nothing can make the gate pass on Oct 9 or 10: it needs W2-01 and W2-02 and the network inputs. Tell management today: the gate moves to Oct 14 to 16 (the Build Plan allows "next week if keys are not ready"). The Nov 26 demo date does not move. | Honest reporting; the next weeks assume the gate |
| 4 | `POST /v1/sims` for an IMSI that **already exists** (W2-01, open item 12) | **Decided 2026-10-10: as suggested.** Same keys: 200, nothing changes. Different keys: **409 conflict, never overwrite.** Changing a SIM's keys becomes a deliberate admin action later. | Blocks the W2-01 endpoint |
| 5 | **Who is the network contact** for the Open5GS template, MongoDB authentication, SIM key status and the radio? | **Decided 2026-10-10: @CaptRaven or @Ukashatu40.** Name one person. Fallback: the lead makes the template on the lab (W2-02 now says how). | Everything on the critical path waits on it |
| 6 | **Backup** for RatelLink and BSS money (risk R-08) | **Decided 2026-10-10: as suggested** (@capitanaserdel). `capitanaserdel` (already the second approver, so must know the code). **Not** `CaptRaven`: if he also maintains it he can no longer review it independently. Goal: by Week 4 he can make a small RatelLink change that you and `CaptRaven` review. | One person cannot be a single point of failure for the keys |
| 7 | Turn **"Require review from Code Owners"** back on in the ruleset | **Done, verified on GitHub 2026-10-10** (`require_code_owner_review: true`). Yes, now. `CODEOWNERS` no longer deadlocks you. | It was switched off to merge #11 |
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

12. **SIM re-import with different keys (W2-01). Decided 2026-10-10 and built:** the same keys again return 200 and change nothing; different keys return 409 `conflict` and never replace the stored ones. Replacing a SIM's keys will be a deliberate admin action, if it is ever needed.
13. **Append-only `audit_log` in MongoDB itself. Built 2026-10-13, applied when the network team creates the user:** `deploy/core-cp/mongo/ratel-link-roles.json` gives RatelLink insert only on `audit_log`, tested on a real MongoDB. The same file also stops RatelLink changing or deleting a stored SIM key.
14. **Ki and OPc format.** The code accepts exactly 32 hexadecimal characters (128 bits) for each, in one place (`domain/sim_keys.py`). This is an assumption: the contract still says `TODO(contract)`. The project lead and the network team confirm it, then the contract is updated in the same commit as any change. Also confirm the case to store (the code keeps the case it was given).
15. **`amf` handling. Resolved 2026-10-12:** the network team's Integration Guide fixes it at `"8000"`. It is a constant RatelLink writes at activation, not a request field. Nothing to store.
16. **Overlap and warning defaults.** API key rotation overlap 7 days (allowed 1 to 30) and expiry warning 14 days (allowed 1 to 90) are proposals. The 90-day lifetime is the Build Plan's.
17. **Encryption key file: backup procedure and owner, and its path on core-cp.** The key needs a separate, secure, offline backup that is never stored with database backups. Nobody owns this yet. Required before the first real SIM key is imported (risk R-14).
18. **Backup encryption for the `open5gs` database.** Open5GS keeps Ki and OPc in plaintext there, so any backup containing it must be encrypted before leaving core-cp (network team, Week 6, risk R-06). Mechanism and location are TODO.
19. **CI authentication for Schemathesis. Built with W2-01 (pending your review of the CI change):** the `contract` job has a throwaway MongoDB service, and `scripts/ci/run_schemathesis.sh` creates its own database, key file and test API key with the admin CLI. The service has no test mode. Locally the script skips RatelLink with a warning unless `RATEL_TEST_MONGO_URI` is set.
20. **MongoDB integration tests in CI. Built with W2-01 (pending your review of the CI change):** a new `integration` job runs `pytest -m integration` against a MongoDB service container, and `ci-success` waits for it. PostgreSQL and Redis containers come when something needs them.
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

### Raised while building W2-01 and the address allocator (2026-10-10)

32. **The audit entry is written after the keys are stored, not in the same step.** MongoDB without a replica set has no transaction. If the audit write fails, the keys are stored, the caller gets a 500, and a retry reports "unchanged" without the missing entry. Options: accept (the failure is rare and visible), run MongoDB as a single-node replica set to get transactions, or write the audit entry first. Suggested: accept for now, revisit with the network team's MongoDB setup.
33. **Gateway address of the UE pool. Resolved 2026-10-12:** the Operations Runbook confirms the first host (`10.45.0.1`) is the UPF's own address, so the allocator is right to reserve it. What is still open is which part of the pool is outside the SMF's dynamic range (N2 in [RATELCORE_INTEGRATION_FACTS.md](RATELCORE_INTEGRATION_FACTS.md)).
34. **A line may take its own released address back during the 24-hour hold.** The Build Plan's rule ("a released address isn't reused for 24 hours, so a late counter reading can never be charged to the wrong person") is about other people. The same line getting its own address back cannot charge anyone wrongly. Suggested: keep. Say if you want the hold to apply to the same line too.
35. **Idempotency-Key handling for `activate`, `data` and `deactivate`** (decision B9 in the queue above) is still open. `POST /v1/sims` does not need it. The header is validated as the contract says (not empty).
36. **`ki` and `opc` now have a pattern in the contract** (32 hexadecimal characters), because the contract fuzzer needs the format to tell valid from invalid. This is still the assumption in item 14. If the SIM supplier uses another format, change `domain/sim_keys.py` and the contract together.

### Raised while building W2-03 (2026-10-11)

37. **A line that was never imported answers 404; one with stored keys and no service answers `provisioned`.** The contract lists 404 for `GET /v1/lines/{imsi}` but does not say what a never-activated SIM looks like. I report `provisioned`, because that is the status the Build Plan gives a SIM whose keys are stored. Say if BSS should see 404 until activation.
38. **`GET /v1/assignments` is not paginated.** The pool is a /16 (about 65,000 addresses), and a full list is a large response. The prototype has tens of lines, so the contract's single list is fine. Revisit with the Week 6 scale test; the contract would need a cursor.
39. **`apns` is a list of strings** (contract placeholder `internet`, `ims`). Confirm the shape when W2-02 has the Open5GS template.

### Raised while building W2-02 (2026-10-13)

40. **Activating an active line with different settings updates it.** The contract only says the same settings are a no-op. The network team's guide says an existing document gets `$set` on RatelLink's fields only, so I allow it (new number, new speeds, voice on or off) and audit it. The alternative is a 409. Say if you want that.
41. **A data change on a line that is not active answers 404** ("no active line"), because the contract lists no 409 for this operation. A provisioned, barred or never-activated line all give the same answer.
42. **Zero is refused as a speed, and there is a 10 Gbit/s maximum.** I do not know what the core does with an `ambr` of 0 (it might mean unlimited), so it is refused. The maximum is a sanity limit I chose; the Build Plan gives none. Both are in the contract with a TODO.
43. **`full` and `slow` need both speeds; `off` ignores them.** The Build Plan lists the speeds as body fields without saying when they are required. Because the caller sends the speeds, RatelLink does not need to remember the "plan speed".
44. **`503` when voice is requested and no voice template is configured.** It is a deployment gap, not the caller's mistake. The contract has no 503 for these operations, only the `default` error.
45. **The subscriber collection needs a unique index on `imsi`, and RatelLink will not create it.** Two simultaneous first activations of one line could otherwise create two documents. RatelLink checks (read only) and logs `startup.subscribers.index.missing`. Ask the network team to confirm the index exists (add to N3). **Confirmed 2026-10-15:** the index exists (`imsi_1`, unique).
46. **Writing the subscriber document and recording the line are separate steps** (as with item 32): if the second fails, a retry repairs it, because every step is repeated safely.

### Raised while preparing the core-cp deployment (2026-10-13)

47. **systemd, not Docker Compose, on core-cp.** The Build Plan allows either. systemd needs nothing new on the core host and keeps a bad deploy away from RatelCore. Say if you prefer Compose.
48. **A TLS reverse proxy (nginx template) on core-cp** carries callers from bss-app and core-up until the VPN exists, per decision 2. It allows only their addresses and records no request paths. The network team may use another proxy with the same properties.
49. **Releases are installed from a tarball built from a reviewed commit and copied to core-cp**, not by cloning the repository there. Each release has its own virtualenv, so rollback is a link change. Needs the Python package index reachable from core-cp, or a wheel folder built elsewhere.
50. **RatelLink's database user is least-privilege and the code was changed to fit it.** The SIM key store now inserts instead of upserting, so the user needs no right to change a stored key. No delete anywhere, nothing in the core's database beyond reading, inserting and updating `subscribers`. **Updated 2026-10-14:** deactivate deletes the subscriber document (item 52), so the role now also has `remove` on `subscribers`, and only there.
51. **MongoDB authentication and the unique `imsi` index are the network team's.** The Build Plan says so. The deployment cannot start safely until both exist. **Status 2026-10-15:** the index exists; MongoDB authentication is still off (a command ran with no credentials).
52. **Deactivate deletes the subscriber document (built 2026-10-14), as the Build Plan says. It is the one delete RatelLink can do.** Implications to decide on: (a) the document goes with the fields the HSS keeps in it, **`security.sqn` included**; after a re-activation the SIM may reject the network's challenge until it resynchronises, which only the lab can show (the integration guide warns that resetting `sqn` makes the SIM reject the challenge); barring (`subscriber_status` 1) would avoid this and is the W2-05 spike's question; (b) the database user gained `remove` on `subscribers` only, a deliberate widening of item 50; (c) the line goes back to `provisioned` (keys, no service) rather than `barred`, so BSS must keep its own record that the line was deactivated; (d) the line's address is released and held 24 hours, so a re-activation gives the same address, and `/v1/assignments` keeps listing it during the hold; (e) a never-activated SIM answers 200 (nothing to do) and an unknown IMSI 404; (f) `reason` is free text written to the audit log, capped at 200 characters in the contract; it is never logged; (g) deactivating a line that the core still shows attached takes effect at its next attach, like every other change.
53. **The acceptance tests start a real RatelLink process and the search for keys now covers the synthetic Ki and OPc in both cases (built 2026-10-14).** `tests/ratel_link/acceptance/` runs in the integration job, which has MongoDB; it starts `uvicorn` as a subprocess on a free local port against two throwaway databases it drops afterwards. Please confirm you are happy with a test that starts a process in CI (it has not run in GitHub Actions yet, only locally). A test that talks to MongoDB itself with a key in a query or document must silence the driver's logger (`tests/ratel_link/acceptance/conftest.py`): at DEBUG the driver copies whole documents into the log, and the product already pins it quiet for that reason.
54. **Contract clean-up (built 2026-10-14).** The `TODO(contract)` list went from 13 to 12 and the rest now name a built behavior, an owner and a proposed date (the table in [W2-12](issues-week2/W2-12-contracts-reconcile-and-mock.md)). The contract now documents 409 on `/data` and 503 on `/sims` and `/activate`, which the code already returned, and the mock serves realistic examples. Documentation only: no behavior changed.

### Raised after the first look at core-cp (2026-10-15)

55. **Python 3.12 has to be installed on core-cp, next to the system Python.** The host runs Ubuntu 22.04.5 with Python 3.10.12; RatelLink needs 3.12 (it uses `datetime.UTC` and `StrEnum`, and its pinned dependencies were verified on 3.12 only), and the install script refuses anything older. Lowering the requirement would mean code changes and running on versions nobody tested, so it is not recommended. Ubuntu's own tools need 3.10, so it must not be replaced. Two ways to get 3.12, both adding software to a core host, so the network team decides: the deadsnakes apt repository (`python3.12`, `python3.12-venv`, needs `sudo`), or a standalone build such as `uv python install 3.12` (needs GitHub reachable from the host). Tracked as N9 in [RATELCORE_INTEGRATION_FACTS.md](RATELCORE_INTEGRATION_FACTS.md).

### Raised 2026-10-16

56. **The independent review of the key code (#32) was not done, and the project lead accepts that for lab test SIMs only.** The reviewers of PR #10 approved it, and the person named for the independent review has no time to read it. The issue made the review a condition for importing "any real SIM key". Accepting the gap is a security decision, so it is written down: it covers **lab test SIMs** (Open5GS keeps their keys in plaintext in the core anyway), not customer SIMs. A real review must happen before any customer key is imported and before the Week 6 security review; the compensating controls are the crypto, authentication, no-key-in-any-log and database-privilege tests. Recorded as R-17. *Proposed for the project lead to confirm by merging this change.*
57. **Live changes: plan "detach and re-attach", conditional on a lab test (proposal).** From the source (not yet measured): a pushed speed is not available, a forced detach is, and it needs a MongoDB replica set and one HSS setting, both on core-cp. See [spike-live-changes.md](spike-live-changes.md). The network lead and project lead decide; until the lab test passes the fallback ("changes apply at the next attach") stays the plan.

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
