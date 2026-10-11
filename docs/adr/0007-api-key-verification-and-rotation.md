# ADR 0007: API-key verification and rotation

- **Status:** Accepted
- **Date:** 2026-10-07
- **Deciders:** Project lead
- **Module paths** are those after [ADR 0008](0008-code-organisation-inside-components.md) (the code was first written as flat files).
- **Related:** Build Plan "The two contracts to freeze on day one" (an API key in the `Authorization` header, one key per calling system) and "Engineering rules" (Access: one API key per calling system, rotated every 90 days; audit log with the calling system's key id); [ADR 0006](0006-ki-opc-encryption-at-rest.md); [DECISIONS_PENDING.md](../DECISIONS_PENDING.md); issues W2-01, W2-03; [runbook](../runbooks/ratel-link.md)

## Context

The contract says every call carries an API key in `Authorization`, one key per calling system,
rotated every 90 days. It did not say what the header carries, how keys are stored, or how rotation
works without changing the contract. RatelLink guards every line's keys and is the only writer to
RatelCore's subscriber database, so this had to be settled before the first endpoint is built.

Calling systems today (implied by the Build Plan): RatelBSS (calls Contract 1) and the RatelMeter
agent (reads `GET /v1/assignments`). The Build Plan puts the services behind the WireGuard VPN, an
additional layer and not a substitute for authentication. **Management deferred the VPN to production
(2026-10-08).** In the lab and pilot, RatelLink binds to 127.0.0.1 behind a TLS reverse proxy that
accepts `/v1` only from known hosts (ARCHITECTURE.md). Until then the API key is the only credential
between the internet and the SIM-key service, which raises the weight of everything in this ADR and of
risk R-16.

## Decision

- **Header.** `Authorization: Bearer <key>`. The scheme name is case-insensitive. No new protocol:
  no JWT, OAuth, mTLS or request signing.
- **Every `/v1` route requires a valid key.** `GET /healthz` stays open (liveness only, exposes
  nothing, not in the contract). A router wrapper (`new_v1_router()` in `api/router.py`) carries the
  dependency, so a route added later is protected by default, and a test walks the real app's routes
  and fails if any `/v1` route lacks it.
- **Authentication runs before the body is read.** Otherwise malformed JSON from an unauthenticated
  caller would get 422 and the server would parse a body it should refuse.
- **One response for every failure.** Missing header, wrong scheme, malformed key, unknown id,
  wrong secret, revoked, expired or disabled all return `401` with
  `{"error": {"code": "unauthorized", "message": "Invalid or missing API key."}}` and
  `WWW-Authenticate: Bearer`. The reason goes only to the operational log as `auth.rejected`, with a
  `reason` field and, when the key parsed, its `api_key_id`. Never the key, the secret or a hash.
  Failed authentication is not an audit record: `audit_log` records changes.
- **Audit records cite `api_key_id`, never the key.**

### What `api_key_id` means

`api_key_id` is a **stable internal id for a calling system**, for example `bss-app` or
`meter-agent`. It does not change when that system's key is rotated. Rotation works through key
**generations**: a system has numbered generations (1, 2, 3, ...), and at most two are valid at any
time, the second only during a bounded overlap window. The id format is `^[a-z][a-z0-9-]{2,31}$`.
Audit entries carry the id of the system, not of a generation.

### Key format and storage

- Key: `rlk_<api_key_id>.<secret>`, where `secret = secrets.token_urlsafe(32)` (256 random bits,
  43 characters). The `rlk_` prefix lets secret scanners find leaked keys (a gitleaks rule does).
  The id is not secret.
- Stored: only `SHA-256(b"ratel-link-api-key-v1|" + secret)` as hex, never the key.
- Why SHA-256 and not argon2 or bcrypt: the secret is random and 256 bits long, so it cannot be
  guessed or looked up in a table, and a slow password hash adds latency and a way to burn CPU
  without adding security. No salt or pepper is needed for the same reason. If a keyed hash is
  wanted later, that is a new ADR.
- Comparison uses `hmac.compare_digest`, over every generation of the matched system with no early
  exit. For an unknown id it still computes a hash and runs one comparison, so timing does not show
  which ids exist. (Revoked and expired generations are compared too, only so the log can say why a
  key was refused. They never authenticate.)

### Lifetime and rotation

- Each generation expires `RATEL_LINK_API_KEY_MAX_AGE_DAYS` after creation. Default and ceiling:
  **90**. A larger value is rejected by the settings, and key creation refuses it again in code.
  Expired generations are rejected.
- `rotate` adds a generation (new 90-day expiry), prints the new key once, and caps the old
  generation's expiry at now plus `RATEL_LINK_API_KEY_ROTATION_OVERLAP_DAYS` (default 7, range
  1 to 30), never extending it. The caller switches to the new key with no contract change. A third
  valid generation is refused.
- `revoke` ends one generation at once. `disable` stops a whole system. Systems and generations are
  never deleted, because audit records refer to them.
- Expiry warnings: at startup and with `api-key check-expiry`, `api_key.expiring` is logged
  (`api_key_id`, `api_key_generation`, `days_left`) for generations within
  `RATEL_LINK_API_KEY_EXPIRY_WARN_DAYS` (default 14, range 1 to 90) of expiry.
- Administration is the `admin_cli` (`api-key create | rotate | revoke | disable | list |
  check-expiry`). A new key is printed once to stdout. No option accepts a key, and no key goes
  through the logging system.

### Storage

MongoDB, database `ratel_link` (own user, localhost only), collection `api_key`:
`{api_key_id (unique), system_name, status: "active" | "disabled", generations: [{generation,
secret_hash, created_at, expires_at, revoked_at | null}], created_at}`. Timestamps are UTC. The
unique index is created by `admin_cli init-db`.

## Alternatives considered

| Option | Why not |
| ------ | ------- |
| Bare key in `Authorization` | Not a registered scheme. `Bearer` is understood by proxies, clients, scanners and the OpenAPI `http` security scheme. |
| Plaintext key storage, or encrypted storage | A reversible store means a database copy yields working keys. A one-way hash does not. |
| argon2 or bcrypt | Built for guessable passwords. Wasted on a 256-bit random secret, and a CPU cost an attacker can trigger. |
| Keyed hash (HMAC with a pepper) | Needs another secret and its handling. The benefit is small for random keys. Possible later, as a new ADR. |
| JWT, OAuth, request signing, mTLS | Each is a new protocol, with its own key or certificate management. The decision is to keep the contract's scheme. |
| One global key for all callers | Breaks "one key per calling system" and makes the audit log's key id meaningless. |
| A separate id per key instead of per system | Makes the audit trail follow key changes instead of callers, and is not what the Build Plan's "calling system's key id" says. |

## Consequences

- Every `/v1` request costs one MongoDB lookup and one SHA-256. If MongoDB is down, authenticated
  routes fail (500), they do not fall open.
- Someone must run `check-expiry` (or watch the startup warning) before keys lapse. A scheduled run
  and its owner are TODO.
- A disabled system cannot be re-enabled with the CLI today. Create a new system id, or add an
  `enable` command (open item).
- Administrative changes are not safe against two operators editing one system at the same moment.
  Run one at a time.
- No rate limiting on failed authentication yet. **With the VPN deferred, put it on the reverse proxy before real SIM keys are imported** (DECISIONS_PENDING.md), not at the Week 6 review. Failed attempts are logged as `auth.rejected` and can flood the log.
- Callers keep their key in an owner-only environment file on their own host (Build Plan). Delivery
  of a new key to the caller is by hand today.

## Security implications

A database dump contains hashes of random secrets, which cannot be turned back into keys. A leaked
key is limited to one calling system and one generation and can be revoked immediately. Callers
cannot tell why a key was refused. The Authorization header is never logged: request logging records
the method, route template and status only.

**Timing, measured (localhost, 2026-10-07).** The hash and comparison work is the same for an
unknown id and a wrong secret: with storage removed, the two differ by about 1 microsecond (one
comparison versus two). Against a real MongoDB the unknown-id request is still about 40 microseconds
faster, because the database returns a document for a known id and nothing for an unknown one.
Application code cannot remove that. The id is not secret, and a 256-bit key cannot be guessed, so this leaks
little. It is accepted and stated here instead of hidden. With the VPN deferred, rate limiting of
failed authentication should move from Week 6 to the reverse proxy before the service is exposed
(DECISIONS_PENDING.md). The numbers come from a throwaway script, not a test, because timing tests
are flaky.

## Data implications

New `api_key` collection, no migration. `audit_log.api_key_id` holds the system id. Time is UTC.

## Operational implications

Create, rotate, revoke, check expiry and respond to an exposed key: see the
[runbook](../runbooks/ratel-link.md). CI cannot call RatelLink's protected operations until a test
key can be seeded (open item for W2-03).
