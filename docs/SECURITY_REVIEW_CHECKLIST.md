# Security review checklist

Use on any PR touching authentication, data access, money, keys, webhooks or network integration.
Part A is source-supported (Build Plan). Part B is general good practice for web services and is
not a claim about the Build Plan.

## Part A: source-supported requirements

- [ ] **Secrets.** Ki and OPc exist only in RatelLink's store and Open5GS's MongoDB. Not in PostgreSQL, logs, tickets, chat, fixtures or backups leaving core-cp unencrypted.
- [ ] **Secrets.** RatelBSS never holds Ki or OPc. SIM import is split (keys to RatelLink; ICCID, IMSI, batch to RatelBSS).
- [ ] **Secrets.** Ki/OPc encrypted at rest (AES-256-GCM envelope, `kid`, per-record associated data, fresh random nonce) with the key in an owner-only file outside the database, never in the repo, no default or fallback key. Startup fails closed without a valid key file outside `local`/`test` ([ADR 0006](adr/0006-ki-opc-encryption-at-rest.md)).
- [ ] **Secrets.** API keys live in owner-only files on the caller's host, never in the repo. RatelLink stores only a one-way hash.
- [ ] **Secrets.** Any backup that contains the `open5gs` database is encrypted before it leaves core-cp (Open5GS keeps Ki and OPc in plaintext). The encryption key file is backed up offline, apart from database backups.
- [ ] **Sensitive-data exposure.** No endpoint returns Ki or OPc. `GET /v1/lines/{imsi}` never returns keys.
- [ ] **Logging.** Structured JSON; no keys, no full PINs; card and PIN numbers masked to the last four digits. A test run finds no Ki/OPc in any log.
- [ ] **Authentication.** Every call carries `Authorization: Bearer <key>`; one key per calling system; no key lives longer than 90 days (a hard ceiling, not only a default) and rotation works without a contract change ([ADR 0007](adr/0007-api-key-verification-and-rotation.md)).
- [ ] **Authentication.** Only hashes are stored. Comparison is constant time over every generation. Every failure (missing, malformed, unknown, wrong, revoked, expired, disabled) returns the same 401 with `WWW-Authenticate: Bearer`, and the reason appears only in the operational log, without the key.
- [ ] **Authentication.** Every `/v1` route is on `new_v1_router()` and the route-protection test is green. Authentication runs before the body is read. `/healthz` is the only open route.
- [ ] **Audit.** Entries cite `api_key_id`, never a key, and pass the content guard. Failed authentication is an operational log event, not an audit entry.
- [ ] **Access.** Every API and RatelDesk reachable only over the WireGuard VPN. Only RatelPay and the payment webhook are public.
- [ ] **Webhook verification.** Signature verified, then the transaction re-queried with the provider before crediting anything.
- [ ] **Replay and idempotency.** `Idempotency-Key` honored on state-changing calls; webhook delivered twice credits once (`provider_ref` unique); voucher redeemed twice credits once; usage replays overwrite on `imsi + period_start` and `call_id`.
- [ ] **Rate limiting.** RatelPay and the webhook are rate-limited. Voucher redemption limited to 5 failed attempts per number per hour.
- [ ] **Database access.** Only RatelLink touches MongoDB, over 127.0.0.1, with authentication on. No developer write access to production databases. RatelLink writes only subscriber documents in the `open5gs` database.
- [ ] **Audit logging.** Every RatelLink change recorded with the calling key id; audit log append-only; state changes in RatelBSS record who and why.
- [ ] **Production access.** No manual schema changes; no developer write access to production databases; configuration changes via reviewed commits.
- [ ] **Customer and call data.** Same access rules for call records as customer records; exports need a logged reason.
- [ ] **Identity data.** NIN captured; no line activates until KYC is verified. Verification rules confirmed with compliance (TODO).
- [ ] **RatelPay.** Shows nothing personal about the line's owner.
- [ ] **Backup security.** Backups containing keys are encrypted when they leave core-cp.

## Part B: general practice (apply with judgment)

- [ ] **Authorization.** Every endpoint checks the caller may do this action on this object, not only that the caller is authenticated.
- [ ] **IDOR / access control.** Can one customer, staff role or calling system read or change another's lines, wallets or records by changing an id (IMSI, MSISDN, line_id, voucher number)?
- [ ] **Input validation.** Types, ranges and formats validated server-side (IMSI pattern, kobo integers, epoch seconds). Unknown fields rejected.
- [ ] **SQL injection.** Parameterized queries or the ORM only; no string-built SQL.
- [ ] **NoSQL injection.** RatelLink builds MongoDB queries from validated typed values; no raw user JSON passed as a query.
- [ ] **CSRF** (where cookies are used, e.g. RatelDesk sessions). State-changing requests protected.
- [ ] **XSS** (RatelDesk, RatelPay). Output encoded; no unescaped user content; a restrictive Content-Security-Policy where practical.
- [ ] **CORS.** Allow-list specific origins; never `*` with credentials.
- [ ] **File handling.** Uploads (if any) type- and size-checked, stored outside the web root, never executed. Voucher batch files treated as untrusted input.
- [ ] **Dependency risks.** New dependency justified, maintained, pinned; `pip-audit` / `npm audit` clean.
- [ ] **Error leakage.** Errors return the standard shape without stack traces, SQL, hosts or secrets.
- [ ] **Rate limiting and brute force** on login and any guessable identifier.
- [ ] **Data retention.** What is stored, for how long, and who can delete it. Retention periods are TODO for compliance.
- [ ] **Transport.** TLS on anything that crosses a network boundary outside the LAN.
- [ ] **Least privilege** for service accounts (MongoDB `ratel_link` user, PostgreSQL roles).
