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
| Ki, OPc | Exist only in RatelLink's store (encrypted at rest, key held outside the database) and Open5GS's MongoDB. Write-only: no endpoint returns them, no log line contains them. Never in PostgreSQL, logs, tickets, chat, test fixtures, AI tools, or backups that leave core-cp unencrypted. RatelBSS never holds them. [Build Plan] |
| Encryption keys (RatelLink key store key) | Held outside the database, in an environment/key file with owner-only permissions on the host. Never in Git. [Build Plan] |
| API credentials | One key per calling system, rotated every 90 days, in environment files outside Git. [Build Plan] |
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
| Audit records | Append-only. Never contain Ki or OPc. RatelLink records the calling system's key id on every change. [Build Plan] |

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
- A test run fails if a Ki/OPc sentinel reaches the test log (`tests/conftest.py`). [Build Plan: log search test]
- Sensitive values never go to AI tools. See [AI_ENGINEERING_POLICY.md](AI_ENGINEERING_POLICY.md).

## Backups

Ki and OPc never leave core-cp in unencrypted backups. [Build Plan] Backups of MongoDB, PostgreSQL
and MySQL and a real restore rehearsal are Week 6 work. TODO: backup encryption and location.

## Deferred to management / compliance (TODO, do not invent)

- Current NCC SIM registration requirements and exact KYC verification rules. [Build Plan]
- Quarantine period before a terminated number can be resold. [Build Plan]
- Data retention periods for customer, call, usage and payment records.
- VAT rate confirmation with finance. [Build Plan]
- Breach notification obligations and contacts.

## Reviewing for security

Use [SECURITY_REVIEW_CHECKLIST.md](SECURITY_REVIEW_CHECKLIST.md). Week 6 includes a security review
of RatelLink and RatelBSS: money. Report vulnerabilities privately: [../SECURITY.md](../SECURITY.md).
