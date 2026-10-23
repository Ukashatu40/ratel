# Runbook: the app on bss-app (RatelBSS and the RatelMeter API)

Keep it short. The person reading it is tired and the service is down. Never put a key, a password or
real customer data in a ticket, a chat message or this file. If you see one in a log, stop and tell
the project lead.

- **Last verified:** never on a real host. The bss-app VM does not exist yet (2026-10-23). The install,
  startup and database roles were exercised in containers and on a throwaway PostgreSQL only
  ([deploy/bss-app/README.md](../../deploy/bss-app/README.md)). TODO: follow this runbook on bss-app once and
  update this line and anything that did not work.
- **Owner:** @Ukashatu40 (project lead). The module runbook for the line features is [bss-lines.md](bss-lines.md).
- **Runs on:** bss-app, as the systemd unit `ratel-app.service`, behind an nginx reverse proxy, with PostgreSQL
  and Redis on the same host.

## Service and purpose

One process holds RatelBSS and the RatelMeter API. Staff tools, the meter agents on core-up and the voice VM
(posting usage and calls), and later RatelPay depend on it.

## Health checks

- `sudo systemctl status ratel-app.service` is active.
- `curl -s http://127.0.0.1:8000/healthz` answers `{"status":"ok"}`. That is liveness only: it does not check
  PostgreSQL or Redis yet (TODO in `services/app/main.py`).
- `sudo -u postgres psql -c '\l'` lists `ratel_bss`; `sudo systemctl status postgresql redis-server nginx`.
- `chronyc tracking` says the clock is synchronised: interval keys and the UTC rules depend on it.

## Dependencies

- **PostgreSQL** on this host: all data. Down means every request that touches data fails.
- **Redis** on this host: not used by any code yet.
- **RatelLink** on core-cp, through its TLS proxy: needed for activate, data and deactivate. If it is
  unreachable the line's state does not change.
- **The clock** (chrony) and the **certificate** the proxy serves.

## Logs

JSON on stdout: `sudo journalctl -u ratel-app.service`. The proxy log is `/var/log/nginx/ratel-app.access.log`
and records who called and the result, never the path. Logs must not contain keys, passwords, IMSIs or numbers.
If you see one, report it as a security issue.

## Common failures

| Symptom | Likely cause | What to do |
| ------- | ------------ | ---------- |
| Service will not start; `METER_API_KEY is not set` | The key is missing or still `CHANGE_ME`. Outside local and test the app refuses to start | Put the real key in `/etc/ratel-app/ratel-app.env` (`sudo -e`), then start |
| Service starts, requests fail with a database error | Wrong `DATABASE_URL`, PostgreSQL down, or migrations not run | `systemctl status postgresql`; check the env file; run the migrations (README step 6) |
| `permission denied for schema public` in the app log | The app role is trying to change the schema | A release needs a migration that was not run, or code is doing DDL. Run the migration as the owner; report the code |
| 403 from the proxy for the agents | Their address is not in the allowed list | Check the `allow` lines in the proxy config |
| 429 from the proxy | Rate limit hit | Look for a client in a loop in the proxy log |
| Agents report the API unreachable | Proxy down, certificate expired, or firewall | `systemctl status nginx`; `sudo nginx -t`; check the certificate dates |
| Service restarts every few seconds | The start limit stops it after four failures in two minutes | `journalctl -u ratel-app.service -e` for the first error |

## Recovery

1. `sudo systemctl status postgresql redis-server` and start whichever is down.
2. `sudo systemctl restart ratel-app.service`; check `/healthz` and the journal.
3. If the last release is the cause, roll back (below).

## Rollback

Point `/opt/ratel-app/current` at the previous release and restart (README, Upgrade and rollback). A migration is
not undone that way. `alembic downgrade -1` refuses to drop tables that hold rows, so restore from a backup. TODO:
backups and a rehearsed restore are Week 6 (risk R-06).

## Escalation

1. @Ukashatu40 (project lead).
2. The network lead for the VM, the firewall and the address allow-list. TODO: contact.
