# ADR 0006: Ki and OPc encryption at rest

- **Status:** Accepted
- **Date:** 2026-10-07
- **Deciders:** Project lead
- **Related:** Build Plan "RatelLink" (`sim_key`: "ki and opc encrypted at rest, with the key held outside the database") and "Engineering rules" (SIM keys); [ADR 0007](0007-api-key-verification-and-rotation.md); [DECISIONS_PENDING.md](../DECISIONS_PENDING.md); issue W2-01; [runbook](../runbooks/ratel-link.md)

## Context

The Build Plan says Ki and OPc are encrypted at rest in RatelLink's key store, with the key held
outside the database. It does not say how: algorithm, library, key format and key handling were
open questions. A leaked key compromises a line for the life of its SIM, so this had to be decided
before any real SIM key is imported.

Two facts shape the decision:

- MongoDB on core-cp holds two copies of every active line's keys. RatelLink's own `ratel_link`
  database holds the copy this ADR protects. Open5GS's `open5gs` database holds a second copy that
  the HSS needs in the clear. This ADR does not and cannot change that (see the residual risks).
- There is no secret manager or KMS in the lab, and the Build Plan asks for the simplest thing that
  works. The design therefore has to work with a file today and allow a KMS later.

## Decision

1. Ki and OPc are encrypted with **AES-256-GCM** before they are persisted. Encryption and
   decryption happen only inside RatelLink, in `services/ratel_link/crypto.py`, reached through
   `SimKeyStore` (`sim_keys.py`). Decryption is for the activation path only.
2. The encryption key is **not in MongoDB**. It is supplied as a file on core-cp (below).
3. No endpoint returns Ki or OPc. They never appear in logs, audit records, tickets, chat, test
   fixtures, PostgreSQL, or unencrypted external backups of `ratel_link`.
4. No key is hard-coded, defaulted or committed. If no key is available, encryption and decryption
   fail. There is no fallback to storing plaintext or to a built-in key.
5. Key handling sits behind a small interface so it can be replaced.
6. The only new dependency is the `cryptography` package (AESGCM). Nothing is hand-rolled.

### Stored envelope

Each of `ki` and `opc` in a `sim_key` document is its own envelope:

```
{"v": 1, "alg": "AES-256-GCM", "kid": "<key id>", "nonce": "<base64, 12 bytes>", "ct": "<base64>"}
```

`ct` is the ciphertext with the 16-byte GCM tag appended. `kid` names the key used, so a later key
can be introduced and old records can still be read (re-encryption tooling is out of scope here).

- **Nonce.** 12 fresh random bytes (`secrets.token_bytes(12)`) for every encryption. Never derived,
  never counter-based, never reused. Random 96-bit nonces are safe for far more messages than this
  store will ever hold (about 2^32 per key is the usual ceiling; we expect tens of thousands).
- **Associated data.** The ciphertext is bound to its record, field and key id:
  `b"ratel-link|sim_key|v1|" + imsi + b"|" + field + b"|" + kid`, where `field` is `ki` or `opc`.
  A ciphertext copied to another IMSI, from `ki` to `opc`, or relabelled with another `kid` fails
  to decrypt. A test covers each case.
- **Key length.** The key must be exactly 32 bytes. A provider that returns another length is
  refused, even for lengths AES accepts (16, 24), so the cipher cannot be weakened silently.
- **Plaintext.** The 32-character hexadecimal text of the value, as UTF-8. See the assumption below.
- **Failures.** Decryption failure raises a generic `DecryptionError`. A missing or unknown key
  raises `KeyUnavailableError`. Neither message ever contains plaintext, ciphertext or key bytes.

### Key management interface

```python
class KeyProvider(Protocol):
    def current_key_id(self) -> str: ...
    def get_key(self, kid: str) -> bytes: ...  # raises KeyUnavailableError
```

All crypto code depends on this interface only (`services/ratel_link/key_provider.py`). The v1
implementation is `FileKeyProvider`:

- `RATEL_LINK_KEY_FILE` names a file holding base64 text of 32 random bytes. `RATEL_LINK_KEY_ID`
  (default `1`) is the id stored in each envelope. The file is read once at startup.
- The file must be a regular file (not a symlink), owned by the user running RatelLink, with no
  group or other permission bits. These checks run in every environment, on the open file
  descriptor. Otherwise RatelLink refuses to start with a message naming the path and the problem,
  never the contents.
- Outside `local` and `test`, a missing or invalid key file stops startup. In `local` and `test`
  the app may start with no key file, and every encrypt or decrypt call then fails.
- Decrypting with an id the provider does not hold fails closed.
- `python -m ratel_link.admin_cli key generate --out PATH` writes a new random key with
  `O_CREAT|O_EXCL` and mode 0600, refuses to overwrite, and prints nothing secret.

### Assumption to confirm

The contract leaves the format of `ki` and `opc` as `TODO(contract)`. The code accepts exactly
**32 hexadecimal characters (128 bits)** for each, defined in one place (`models.py`). This is an
assumption, flagged in [DECISIONS_PENDING.md](../DECISIONS_PENDING.md) for the project lead and the
network team. The contract is not changed for it. `amf` is not stored (another open contract TODO).

## Alternatives considered

| Option | Why not |
| ------ | ------- |
| Fernet | AES-128-CBC with HMAC. 128-bit key, no associated data, so a ciphertext cannot be bound to its record. Its token format is fixed. |
| libsodium secretbox (PyNaCl) | Sound, but no associated data in that construction, and it adds a second cryptography dependency next to the one we already need. |
| MongoDB client-side field level encryption | Ties encryption to the MongoDB driver and `libmongocrypt`, and still needs a key provider. Its local master key option is for development, so production would need a KMS anyway. Our own envelope is small and testable. |
| KMS or Vault now | A new service to run, secure and back up on core-cp, with nothing like it in the lab today. The `KeyProvider` interface lets us add one later without touching the crypto. |
| One global key with no key id | Blocks any later key change. The `kid` costs one field. |
| Hand-written cipher or mode | Not acceptable. We use `cryptography`'s AESGCM. |
| Encrypting the whole document | `imsi` must stay queryable and unique. Only the two secrets need protection. |

## Consequences

- RatelLink needs a key file on core-cp before it starts outside local and test. Deployments must
  create it (`key generate`) and keep its backup (below).
- Changing the key later needs a re-encryption tool that does not exist yet. The envelope carries
  `kid` so the tool can be written without a data migration.
- Every decrypt is a fresh AES-GCM operation on a single value. Nothing is cached in memory beyond
  the key itself.
- Operational logging at `DEBUG` is capped for the MongoDB driver (`pymongo` at WARNING) because the
  driver can log whole command documents.

## Security implications

- A stolen copy of `ratel_link` (database file, dump, backup) reveals no Ki or OPc without the key
  file. A record copied or swapped inside the database fails to decrypt.
- The file checks make an accidentally world-readable key a startup failure, not a silent risk.
- `SimKeys` (decrypted values) holds `SecretStr` fields, has a redacted repr and no serialisation
  path. Validation errors never echo a rejected value.

**Residual risks. These are real and are not solved by this ADR:**

1. **Open5GS stores Ki and OPc in plaintext** in its own `open5gs` MongoDB database for every
   active line, because the HSS needs them. This encryption protects only RatelLink's `sim_key`
   store. Therefore **any backup that contains the `open5gs` database must be encrypted before it
   leaves core-cp.** That is the network team's Week 6 backup work. Backup encryption and location
   are TODO for the project lead and the network team.
2. **The key file lives on the same host as MongoDB.** Anyone with root on core-cp can read both.
   A KMS later reduces this. It does not exist today.
3. **Losing the key file loses every stored ciphertext.** The key needs a separate, secure, offline
   backup that is never stored with database backups. Procedure and owner: TODO for the project lead.

## Data implications

New collection contents: `sim_key` documents are `{imsi, ki: envelope, opc: envelope, created_at}`
(UTC). `imsi` is unique, enforced by an index that `admin_cli init-db` creates (no automatic index
creation in production; startup only checks and logs). No migration: the collection is new. The
store never overwrites an existing IMSI. What the API should do when an existing IMSI arrives with
different keys is not decided (open question for W2-01).

## Operational implications

- Key file location and permissions, generation, backup and exposure response are in the
  [runbook](../runbooks/ratel-link.md).
- Startup logs `key.provider.none` (a warning) when it runs without a key. That must never appear
  outside `local` and `test`.
- Not in scope: re-encryption or rotation tooling for the encryption key, and any KMS provider.
