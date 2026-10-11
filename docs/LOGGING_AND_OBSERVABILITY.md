# Logging and observability

Implementation: `services/common/logging.py`, `services/common/http.py`. Build Plan: structured
JSON logs; never log keys or full PINs; mask card and PIN numbers to their last four digits.

## Format

One JSON object per line on stdout. Fields: `ts` (UTC ISO 8601), `level`, `logger`, `event`,
`request_id` (when in a request), plus any fields you pass. systemd or Docker collects stdout.

```python
log_event(log, logging.INFO, "line.activate.succeeded", status="active", speed_dl_mbps=10)
```

## Rules

- **Event names** are stable, dotted and lowercase: `<noun>.<action>.<outcome>`, for example `usage.upsert.replayed`, `webhook.signature.rejected`. Do not build messages with f-strings; pass fields.
- **Levels.** `DEBUG` developer detail (off in production). `INFO` normal state changes. `WARNING` recoverable oddity (counter reset, spooling started). `ERROR` an operation failed. `CRITICAL` the service cannot continue.
- **Request IDs.** The `x-request-id` header is accepted or generated, echoed back, and attached to every log line in the request. Pass it through calls between our services.
- **Route templates, not paths.** Request logs record `/v1/lines/{imsi}/activate`, not the raw URL, so IMSIs stay out of logs.
- **Never log:** Ki, OPc, ciphertext, passwords, API keys, key hashes, tokens, `Authorization` headers, full PINs, card numbers, NINs, connection strings, or unnecessary personal data (MSISDN, names, addresses). Use a hash or the last four digits when you must correlate.
- **Masking.** Sensitive keys are replaced with `[REDACTED]` by key name (`ki`, `opc`, `pin`, `nin`, `password`, `secret`, `token`, `api_key`, `authorization`, `*_url` for databases, and more; see `SENSITIVE_KEY_PARTS`). Redaction is by name only. It cannot find a secret inside a free-text message, so **never put values in messages.** `mask_last4()` for PIN and card numbers.
- **Exact-name allowlist.** `api_key_id` and `api_key_generation` contain `api_key` but are not secrets: they name the calling system and are needed to follow a caller. They are matched by exact name before the sensitive parts, so `api_key`, `api_key_secret` and the like stay redacted.
- **Request context.** Once a request is authenticated, `api_key_id` and `api_key_generation` are added to every log line of that request, including the access log line (`bind_log_context`). Request logs never include headers.
- **Errors.** Log the exception type and a stable event name, not the message or traceback text (those can carry values). Client responses use the standard error shape with no internals.
- **Audit logging is separate from operational logs.** RatelLink's `audit_log` (MongoDB) and RatelBSS state-change audit entries are append-only records of who did what and why. They are data, not log lines, and never contain Ki or OPc.
- **Operational logging** covers start/stop, health, config load (without values), agent intervals, spool depth, replay results, rating pass counts.

### RatelLink security events

| Event | Level | Fields | Meaning |
| ----- | ----- | ------ | ------- |
| `auth.rejected` | WARNING | `reason`, `api_key_id` (only if the key parsed) | A request was refused with 401. `reason` is one of `missing_header`, `wrong_scheme`, `malformed_token`, `unknown_id`, `bad_secret`, `revoked`, `expired`, `disabled`. The caller only ever sees the generic 401. Never the key, secret or hash. |
| `api_key.expiring` | WARNING | `api_key_id`, `api_key_generation`, `days_left` | A key is within the warning window. Logged at startup and by `api-key check-expiry`. |
| `api_key.created`, `.rotated`, `.revoked`, `.disabled` | INFO | `api_key_id`, `api_key_generation` | Administration with the admin CLI. |
| `sim.import.created`, `.unchanged`, `.conflict` | INFO, INFO, WARNING | `api_key_id` | `POST /v1/sims` outcomes. Never the IMSI or a key. A conflict means a caller sent different keys for a known IMSI. |
| `ip.allocated`, `.reclaimed`, `.released` | INFO | none | Address allocation. Never the IMSI. |
| `key.unavailable` | ERROR | none | A request needed the encryption key and there was none (the caller got 503). |
| `key.provider.none` | WARNING | `reason` | RatelLink started without an encryption key. Allowed only in `local` and `test`. If it appears anywhere else, treat it as an incident. |
| `startup.indexes.missing` | ERROR | `indexes` | Run `admin_cli init-db`. |
| `startup.checks.failed` | ERROR | `exc_type` | MongoDB was not reachable at startup. The service still started. |

The admin CLI writes its log lines to stderr. Stdout carries only the result, such as a new key.
The MongoDB driver's loggers are held at WARNING, because at DEBUG they log whole command documents.
Failed authentication is an operational event, not an `audit_log` entry.

## Guard rails

- Unit tests prove redaction of Ki/OPc sentinels, nested fields and exception text (`tests/common/test_logging.py`).
- The whole test run fails if a Ki/OPc sentinel reaches the captured log (`tests/conftest.py`).
- Review: [SECURITY_REVIEW_CHECKLIST.md](SECURITY_REVIEW_CHECKLIST.md).

## Health and monitoring

- Each service exposes `/healthz` (liveness) now. TODO: readiness checks (MongoDB ping for RatelLink; PostgreSQL and Redis for app).
- RatelOps (Prometheus, Grafana, Alertmanager) is network-team configuration in `ops/`. Open5GS and Kamailio already export metrics. TODO: agree with the network team which software-side metrics (agent spool depth, last successful interval, rating lag, wallet reconciliation result) RatelOps scrapes.
