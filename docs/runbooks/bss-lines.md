# Runbook: RatelBSS lines

- **Last verified:** 2026-10-23 (followed once on the local dev PostgreSQL)
- **Owner:** @Abbalolo
- **Runs on:** bss-app, as part of the `app` process

## Service and purpose

RatelBSS's line module: customers, SIM/number stock, plans, bundles, lines, the
line state machine, and the sell-to-activate flow. Every state change goes
through `domain/state_machine.py`; each writes a `line_audit` row.

## Health checks

- `/healthz` (app liveness).
- `/readyz` (PostgreSQL and Redis readiness).
- Migrations applied: `alembic -c services/app/alembic.ini current`.

## Dependencies

- PostgreSQL on the bss-app VM.
- RatelLink for `/activate`, `/data`, `/deactivate` when a line changes state.
  If RatelLink is unreachable, the state doesn't change.
- Redis for idempotency keys (M-26, not built yet).

## Logs

Structured JSON. Never contains Ki, OPc, PINs, or full IMSIs/ICCIDs.

## Common failures

| Symptom | Cause | Fix |
| --- | --- | --- |
| Activation refused: KYC not verified | `customer.kyc_status != 'verified'` | Desk re-verifies KYC. |
| Activation refused: wrong state | Line not in `awaiting_activation` | Check `line.state` and the `line_audit` history. |
| `/activate` returns 502 | RatelLink unreachable or 5xx | Check RatelLink `/readyz` on core-cp. |
| `AlreadyTaken` | Someone else took the SIM/number first | Retry with a different one. |

## Recovery

Restart the `app` service on bss-app; it reconnects to PostgreSQL and Redis.

## Rollback

Point the release to the previous commit and restart. Schema rollback:
`alembic -c services/app/alembic.ini downgrade -1`. The bundle migration
refuses to run if `bundle` or `line` hold rows; restore from a backup instead.

## Escalation

1. @Abbalolo (module owner)
2. @Ukashatu40 (project lead)