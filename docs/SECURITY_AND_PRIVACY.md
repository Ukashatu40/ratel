# Security and privacy

**Collect less. Expose less. Log less. Store only what is required. Restrict access. Audit
sensitive operations.**

Statements marked **[Build Plan]** come from the source documents. Everything else here is a
working convention. Legal and compliance decisions are not made in this repository: where the
source documents defer them to management or compliance, they are TODOs.

## Data classification

### Critical / high sensitivity

| Data | Rule |
| ---- | ---- |
| Ki, OPc | Exist only in RatelLink's store and Open5GS's MongoDB. In RatelLink's `sim_key` they are encrypted at rest with AES-256-GCM, key held outside the database ([ADR 0006](adr/0006-ki-opc-encryption-at-rest.md)). Open5GS keeps its own plaintext copy for active lines (the HSS needs it): see Backups. Write-only: no endpoint returns them, no log line, audit record or exception contains them. Never in PostgreSQL, logs, tickets, chat, test fixtures, AI tools, or backups that leave core-cp unencrypted. RatelBSS never holds them. [Build Plan] |
| Encryption keys (RatelLink key store key) | Held outside the database, in a key file on core-cp (`RATEL_LINK_KEY_FILE`): regular file, owned by the service user, mode 0600 (RatelLink refuses to start otherwise). Never in Git, never defaulted. Needs its own offline backup, kept apart from database backups: losing it loses every stored Ki and OPc. Backup procedure and owner: TODO. [Build Plan, ADR 0006] |
| API credentials | One key per calling system, sent as `Authorization: Bearer <key>`, rotated every 90 days (hard ceiling in code), in owner-only environment files outside Git. RatelLink stores only a one-way hash and cites the calling system's `api_key_id` in audit records. Failures return one generic 401. Keys are never logged. [Build Plan, ADR 0007] |
| Database credentials | Environment files on each host. MongoDB authentication on, bound to 127.0.0.1. No developer has write access to production databases. [Build Plan] |
| Payment credentials (gateway secrets, webhook signing secret) | Outside Git. Webhook signatures verified on every call. TODO: confirm payment provider. |
| Authentication secrets (staff passwords, sessions) | Never logged. TODO: staff authentication design (not specified in the Build Plan). |
| Voucher PINs | Stored hashed, never plain text. Mask to last four digits in logs. [Build Plan] |

### Personal / business-sensitive

| Data | Rule |
| ---- | ---- |
| NIN, customer identity data (name, id_type, id_number, address, kyc_status) | Protected. Captured for SIM registration. RatelBSS PostgreSQL only. Never in logs, fixtures or AI tools. [Build Plan] Retention and verification rules: TODO compliance. |
| Phone numbers (MSISDN), IMSI, ICCID | Personal/business-sensitive. Log route templates and hashes, not raw values, where possible. |
| Call records (who called whom, when) | Personal data. Same access rules as customer records. Never exported without a logged reason. [Build Plan] |
| Usage information | Business-sensitive. Same access rules. |
| Payment records | Business-sensitive. One row per provider transaction. Re-queried with the provider before crediting. [Build Plan] |
| Audit records | Append-only. Never contain Ki, OPc, ciphertext or tokens (a content guard refuses them). RatelLink records the calling system's `api_key_id` on every change, never the key. Append-only enforcement in MongoDB itself (a user that may only insert) is still a TODO decision for the project lead. [Build Plan] |

### Public

- RatelPay's intentionally public content. RatelPay shows nothing personal about a line's owner (TOP-2). [Build Plan]
- Other content explicitly approved as public.

Anything not listed is treated as personal/business-sensitive until classified.

## Access

- Every API and RatelDesk is reachable only over the WireGuard VPN. Public by design: RatelPay and the payment gateway's webhook. Expose only those paths. [Build Plan]
- RatelDesk is served only on the office network and the VPN. [Build Plan]
- Rate-limit RatelPay and the webhook. Voucher redemption: at most 5 failed attempts per number per hour. [Build Plan]
- Least privilege for people too: no developer write access to production databases. [Build Plan]

## Logging

Structured JSON. Never log keys or full PINs. Never log passwords, API keys, tokens, NINs, or
unnecessary personal data. See [LOGGING_AND_OBSERVABILITY.md](LOGGING_AND_OBSERVABILITY.md).

## Development, tests and AI

- Synthetic fixtures only. No real customers, keys, NINs or payments in development or tests.
- A test run fails if a Ki, OPc or API-key sentinel reaches the test log (`tests/conftest.py`). [Build Plan: log search test]
- Sensitive values never go to AI tools. See [AI_ENGINEERING_POLICY.md](AI_ENGINEERING_POLICY.md).

## Backups

Ki and OPc never leave core-cp in unencrypted backups. [Build Plan] Backups of MongoDB, PostgreSQL
and MySQL and a real restore rehearsal are Week 6 work. TODO: backup encryption and location.

- **Any backup that contains the `open5gs` database must be encrypted before it leaves core-cp.**
  Open5GS stores Ki and OPc in plaintext there for every active line. RatelLink's encryption does
  not protect that copy (ADR 0006). Backup encryption is the network team's Week 6 work.
- The RatelLink encryption key file is backed up separately from, and never with, any database
  backup. A backup that holds both the `ratel_link` database and its key file is as good as
  plaintext. Procedure and owner: TODO for the project lead.

## Deferred to management / compliance (TODO, do not invent)

- Current NCC SIM registration requirements and exact KYC verification rules. [Build Plan]
- Quarantine period before a terminated number can be resold. [Build Plan]
- Data retention periods for customer, call, usage and payment records.
- VAT rate confirmation with finance. [Build Plan]
- Breach notification obligations and contacts.

## Reviewing for security

Use [SECURITY_REVIEW_CHECKLIST.md](SECURITY_REVIEW_CHECKLIST.md). Week 6 includes a security review
of RatelLink and RatelBSS: money. Report vulnerabilities privately: [../SECURITY.md](../SECURITY.md).
