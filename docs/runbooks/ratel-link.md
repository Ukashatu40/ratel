# Runbook: RatelLink

Keep it short. The person reading it is tired and the service is down. Never put a key, a token or
real customer data in a ticket, a chat message or this file. If you see one in a log, stop and tell
the project lead (see "If a key is exposed").

- **Last verified:** never, TODO (nobody has followed these steps on core-cp yet)
- **Owner:** @Ukashatu40 (RatelLink owner)
- **Runs on:** core-cp. TODO: systemd unit name and unit file (`deploy/core-cp/`)

Decisions behind this page: [ADR 0006](../adr/0006-ki-opc-encryption-at-rest.md) (encryption of Ki
and OPc) and [ADR 0007](../adr/0007-api-key-verification-and-rotation.md) (API keys).

## Service and purpose

RatelLink is the provisioning API. It holds each SIM's keys and is the only writer to RatelCore's
subscriber database. RatelBSS calls it, and the RatelMeter agent reads `GET /v1/assignments`.
Every `/v1` call needs `Authorization: Bearer <key>`.

## Health checks

- `GET http://127.0.0.1:<port>/healthz` returns `{"status":"ok"}`. This is **liveness only**: it
  does not check MongoDB or the key. TODO: readiness check.
- After a start, read the startup log lines (below). Healthy means none of these appeared:
  `key.provider.none`, `startup.indexes.missing`, `startup.checks.failed`.
- Degraded looks like: callers getting 401 after a rotation, 500 on `/v1` (usually MongoDB), or an
  `api_key.expiring` warning.

## Dependencies

- MongoDB on `127.0.0.1` (authentication on). If it is down, authenticated routes fail with 500.
  They never fall open.
- The encryption key file (below). Without it RatelLink does not start outside `local`/`test`.
- A correct clock (NTP). Key expiry is checked against the host's UTC time.

## Logs

JSON on stdout (`journalctl -u <unit>`). Events that matter:

| Event | What it tells you |
| ----- | ----------------- |
| `auth.rejected` (`reason`, `api_key_id`) | A caller got 401. The reason is only here, never in the response. |
| `api_key.expiring` | A key is close to its 90-day end. Rotate it. |
| `api_key.created`, `.rotated`, `.revoked`, `.disabled` | Someone ran the admin CLI. |
| `key.provider.none` | Started with no encryption key. Never acceptable on core-cp. |
| `startup.indexes.missing` | Run `init-db`. |
| `startup.checks.failed` | MongoDB was unreachable at startup. |

Logs must not contain keys, tokens or Ki/OPc. If you find one, it is a security issue: see below.
Run the service with the HTTP server's own access log off, because it prints raw paths that contain
IMSIs. TODO: confirm the flag in the unit file.

## The encryption key file

- **Location:** the path in `RATEL_LINK_KEY_FILE`. TODO: agree the path on core-cp (outside any
  Git checkout and outside backups that leave the host). Id of the key: `RATEL_LINK_KEY_ID`.
- **Permissions:** a regular file (not a symlink), owned by the user that runs RatelLink, mode 0600
  or 0400. RatelLink refuses to start otherwise, and the error names the path and the problem.
- **Create (first time only), as the service user:**
  `python -m ratel_link.admin_cli key generate --out <path>`. It refuses to overwrite an existing
  file and prints nothing secret.
- **Never** create a second key file "to try" in the same place, copy it into a ticket, or run
  `cat` on it in a shared terminal.
- **Backup: TODO(owner).** Losing this file loses every stored Ki and OPc ciphertext. It needs its
  own secure, offline backup that is **never stored with database backups**. The project lead
  decides the procedure and the owner. Do not import a real SIM key until this exists.

## API keys

All commands run on core-cp as the service user, from the service directory, with the service's
environment loaded (the same file the unit uses). `PYTHONPATH=services` is assumed.

| Task | Command |
| ---- | ------- |
| Create the indexes (once per environment, safe to repeat) | `python -m ratel_link.admin_cli init-db` |
| Register a calling system and print its first key | `python -m ratel_link.admin_cli api-key create --id bss-app --name "RatelBSS"` |
| Rotate: add a new key, keep the old one for the overlap | `python -m ratel_link.admin_cli api-key rotate --id bss-app` |
| End one key now | `python -m ratel_link.admin_cli api-key revoke --id bss-app --generation 1` |
| Stop a whole system | `python -m ratel_link.admin_cli api-key disable --id bss-app` |
| Show systems and key lifetimes (never keys) | `python -m ratel_link.admin_cli api-key list` |
| Log keys close to expiry | `python -m ratel_link.admin_cli api-key check-expiry` |

Calling systems today: `bss-app` (RatelBSS) and `meter-agent` (the RatelMeter agent).

- **Creating and rotating print the key once, on stdout.** It cannot be shown again. Put it
  straight into the caller's owner-only environment file on the caller's host
  (`RATEL_LINK_API_KEY` for RatelBSS, `METER_AGENT_RATEL_LINK_API_KEY` for the agent). Do not copy
  it through a ticket, chat or email, and do not capture it in shell history that leaves the host.
- **Rotation procedure (every 90 days, before `api_key.expiring` turns into expiry):**
  1. `api-key rotate --id <id>`. The new key prints once. The old key keeps working for the
     overlap (default 7 days) and then stops.
  2. Put the new key in the caller's environment file and restart or reload the caller.
  3. Check the caller works. In the log, `auth.rejected` for that `api_key_id` should not appear.
  4. Optionally `api-key revoke --id <id> --generation <old>` to end the old key at once.
  No contract or code change is needed. At most two keys of a system are valid at the same time.
- **Expiry checks:** the service logs `api_key.expiring` at every start. Also run `check-expiry`
  on a schedule. TODO(owner): who runs it and how it alerts (RatelOps).
- A disabled system cannot be re-enabled with the CLI. Create a new system id, or ask for an
  `enable` command. Systems and keys are never deleted.
- Run administration commands one at a time. Two people changing the same system at once can undo
  each other.

## Common failures

| Symptom | Likely cause | What to do |
| ------- | ------------ | ---------- |
| Service will not start: `key file ... does not exist` | `RATEL_LINK_KEY_FILE` wrong, or the file is gone | Restore the file from the offline backup. Do not generate a new one: it cannot read existing records. |
| `... is accessible to group or others` | Permissions loosened | `chmod 600` it. Then ask how it happened. |
| `... is not owned by the user running RatelLink` | File created as root or another user | Fix the owner to the service user. |
| `... must contain base64 of exactly 32 bytes` | The file was edited or truncated | Restore from backup. |
| `RATEL_LINK_KEY_FILE is not set` | Environment file missing the variable | Set it and restart. |
| A caller gets 401 | Check the log for `auth.rejected` and its `reason` | `expired`: rotate. `revoked` or `disabled`: expected until a new key is issued. `bad_secret` or `unknown_id`: the caller has the wrong key. `malformed_token`: the caller is not sending the full `rlk_...` key, or a wrong header. |
| `startup.indexes.missing` | `init-db` never ran | Run it. |
| `/v1` returns 500 | MongoDB down or the `ratel_link` user cannot authenticate | Check MongoDB. TODO: readiness check. |
| `http.unhandled_error` with `exc_type` `DecryptionError` | The key file is not the one that encrypted the record, or a record was altered | Stop. Do not retry in a loop. Tell the project lead. |
| `a calling system with api_key_id ... already exists` | The system exists | Use `rotate`. |

## If a key is exposed

Do not paste the exposed value anywhere to "check" it. Say which kind it was and where it was seen.

- **An API key** (in a ticket, chat, log, screenshot, repository): tell the project lead, then
  `api-key rotate` for that system, move the caller to the new key, and `revoke` the exposed
  generation at once. A secret scan alert on an `rlk_` value means the same. A leaked key is
  rotated, not just deleted from where it was found.
- **The encryption key file** (copied, backed up with the database, visible to another user):
  tell the project lead immediately. Treat every stored Ki and OPc as exposed if a copy of
  `ratel_link` could also have been taken. There is no re-encryption tool yet, and no automatic
  replacement of SIM keys. The project lead decides, with the network team and the SIM supplier.
  Meanwhile do not generate a new file over the old one.
- **Ki or OPc** in a log, ticket or chat: treat it as a security incident for that SIM. Tell the
  project lead. The SIM's keys may have to be replaced with the supplier.
- **A database backup that contains `open5gs` and left core-cp unencrypted:** same as above. Open5GS
  keeps Ki and OPc in plaintext there.

## Recovery

1. MongoDB up and authenticated, bound to 127.0.0.1.
2. The key file present with the right owner and mode (restored from the offline backup if lost).
3. Start the service. Confirm no `key.provider.none`, `startup.indexes.missing` or
   `startup.checks.failed` lines.
4. `GET /healthz`, then one authenticated call from a caller.
5. If keys expired while it was down, `api-key rotate` and redistribute.

## Rollback

TODO: deployment procedure (`deploy/core-cp/`). A code rollback does not change stored data. Note
that stored records are encrypted: an older version without the encryption code cannot read them.

## Escalation

TODO: network-team contact and the project lead. Security exposures go to the project lead first.
