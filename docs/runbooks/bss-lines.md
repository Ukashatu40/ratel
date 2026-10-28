# Runbook: RatelBSS lines

- **Last verified:** never on bss-app (the host doesn't exist yet, M-27). The
  migrations, tests and the stock guarantee were run locally on the dev
  PostgreSQL; the operational steps below have not been followed on a real
  deployment.
- **Owner:** @Abbalolo
- **Runs on:** bss-app, as part of the `app` process (deployment: M-27, TODO)

## Service and purpose

RatelBSS's line module: customers, SIM/number stock, plans, bundles, lines, the
line state machine, and the sell-to-activate flow. Every state change goes
through `domain/state_machine.py`; each writes a `line_audit` row.

## Health checks

- `GET /healthz` — the only health route today (`services/app/main.py`). It
  answers `{"status": "ok"}` and does not check the database.
- A readiness check for PostgreSQL is not built yet; TODO when the app has
  state it must report on. Redis is not used by the app yet.
- Migrations applied: `alembic -c services/app/alembic.ini current`, once
  bss-app exists (M-27).

## Dependencies

- PostgreSQL on the bss-app VM.
- RatelLink for `/activate`, `/data`, `/deactivate` when a line changes state.
  If RatelLink is unreachable, the state doesn't change (the caller gets
  `RatelLinkError`, mapped to 502 by `api/lines.py`).
- Redis for idempotency keys (M-26, not built yet).

## Logs

Structured JSON. Never contains Ki, OPc, PINs, or full IMSIs/ICCIDs.

## Common failures

| Symptom | Cause | Fix |
| --- | --- | --- |
| Activation refused: KYC not verified | `customer.kyc_status != 'verified'` | Desk re-verifies KYC. |
| Activation refused: no plan has been paid for (409) | The line has no allowance with data left that has not expired | Top up the line's wallet (voucher or payment), then buy the plan: `POST /v1/lines/{line_id}/purchases`, or `python -m app.bss_money.ops_cli buy` on bss-app. Then activate again. A lab test line needs this too. |
| Activation refused: wrong state | Line not in `awaiting_activation` | Check `line.state` and the `line_audit` history. |
| `/activate` returns 502 | RatelLink unreachable or 5xx | Check RatelLink health on core-cp. |
| `AlreadyTaken` | Someone else took the SIM/number first | Retry with a different one. The exception carries no identifier. |

## Recovery

TODO (M-27): the app runs on bss-app; restart the service, it reconnects to
PostgreSQL. Until M-27 exists, this is not a real step.

## Rollback

Schema rollback: `alembic -c services/app/alembic.ini downgrade -1`. The bundle
migration refuses to run if `bundle` or `line` hold rows — restore from a
backup instead. Code rollback: TODO (M-27), point the release to the previous
commit.

## Escalation

1. @Abbalolo (module owner)
2. @Ukashatu40 (project lead)