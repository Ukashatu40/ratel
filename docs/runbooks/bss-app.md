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

## The rating job

`python -m app.bss_money.rating_cli` takes each line's new usage records off its allowance and then slows, cuts,
expires or restores lines (M-17). `ratel-rating.timer` runs it at two minutes past every fifth minute
(`systemctl list-timers ratel-rating.timer`; `journalctl -u ratel-rating.service -n 50`). To run it once by hand:

```
sudo systemctl start ratel-rating.service; systemctl status ratel-rating.service --no-pager | head -8
```

A failed unit means exit 1 or 2 below. The nightly `ratel-ledger-check.timer` is the same idea for the books: a
failed `ratel-ledger-check.service` means a wallet differs from its ledger (`journalctl -u ratel-ledger-check`).

| Exit | Meaning | What to do |
| ---- | ------- | ---------- |
| 0 | Finished; every line was handled | Nothing |
| 1 | Finished, but a line failed (`rating.line_failed` or `rating.line_change_failed` in the log) | Read the log line for the `line_id` and the error type. The next run tries that line again; usage that was not rated is still waiting, never lost |
| 2 | Could not run: the database did not answer, or `RATEL_LINK_API_KEY` is not set | Fix the cause and run again |

What it does, and does not do:

- Usage is deducted soonest-expiry-first and each record is marked rated (`usage_rating`) in the same
  transaction, so a crash rates nothing twice. Running it twice in a row changes nothing.
- A line whose allowance is used up goes `active` to `out_of_data` through the state machine, once. RatelLink gets
  `/data` (slow speeds or off, as the plan says); calls are not touched. A line whose validity ended with no
  renewal goes to `expired` (`/deactivate`). If RatelLink is down, the change is tried again on the next run.
- A line that has **never had an allowance** is rated but never cut, so a line made by hand in the lab does not
  lose service. A SIM with no line keeps its records unrated until a line exists.
- **A line gets its data back when it has allowance again.** A purchase (a bundle, or a plan) creates the bucket;
  the next run sees it and puts an out-of-data line back to full speed, or an expired line back on, through the
  state machine. If RatelLink is down at that moment the next run tries again, and the customer is not charged twice.
- **Top-up with a voucher restores data only if `RATING_AUTO_RENEW=true`.** Then, on each run, a line that is
  out of data or expired and whose wallet covers its own plan has that plan bought again (the price comes out of the
  wallet as a `purchase` and a `vat` entry; `VAT_RATE_BPS`, 750 = 7.5%, finance to confirm). Off, the voucher only
  credits the wallet and the plan or bundle must be bought on purpose (`ops_cli buy`). It is a product decision
  (TODO(PRD)), so it is off until it is turned on in `ratel-app.env`.
- Never roll the `usage_rating` table back by hand. Those rows are the only record of what has been deducted,
  and deleting them makes the next run deduct the same usage again. The migration refuses to downgrade while they exist.

## Vouchers

Prepaid cards are made and moved along by `python -m app.bss_money.voucher_cli`, run by a person on bss-app, and
redeemed by customers through the public route `POST /v1/pay/vouchers/redeem` (called by the RatelPay page).
Use the same `sudo -u ratelbss ... bash -c 'set -a; . /etc/ratel-app/ratel-app.env; ...'` wrapper as for the rating
job, with `-m app.bss_money.voucher_cli`.

| Task | Command (after `voucher_cli`) |
| ---- | ----------------------------- |
| Make a batch | `create-batch --batch nov-1 --count 100 --value-kobo 50000 --out /root/nov-1.csv` |
| Move a batch on | `set-state --batch nov-1 --to approved` (then `sent_to_printer`, `in_stock`, `on_sale`, in that order) |
| Stop a lost or stolen card | `lock --voucher-id 123` |

- **The output file of `create-batch` holds every PIN, and is the only place they exist.** It is created for you
  alone (mode 0600) and never overwritten. Hand it to the printer, then delete it (`shred -u`). A PIN cannot be
  recovered from the database, which keeps only a salted hash. Never copy the file into a ticket or a chat.
- A card can be redeemed only while it is `on_sale`. A batch moves as a whole: one card that cannot make the move
  stops the whole batch from moving.
- Face values and expiry are TODO(PRD): nothing here chooses them. `--value-kobo` is whatever you were told.

What a customer sees, and why it is so plain:

- Every failure (a wrong number or PIN, an unknown phone number, a used, locked, expired or not-yet-on-sale card)
  gives the same answer, `400 voucher_refused`, so a guesser learns nothing. Only two answers differ: `422` for
  digits that are not well formed (a typo; not counted) and `429` after 5 failed attempts on one card number in
  an hour (the PIN is not even checked). Wait the hour: there is no way to lift it early, by design.
- A customer who redeemed and retries (a lost reply) gets the success again and is not charged twice or counted.
- The page sends **no key**: the proxy adds the redemption key (`PAY_API_KEY`) to this one route and replaces
  anything the browser sent. A `401` from this route means the proxy's key file and `PAY_API_KEY` differ. The key is
  not what stops guessing (anyone can call the proxy); the limit above and the proxy's per-address limit
  (`ratel_redeem` zone in the nginx template) are. If you see a flood in the proxy log (`429` from nginx), that is the
  proxy doing its job; the log holds no card number, PIN or path.

| Symptom | Likely cause | What to do |
| ------- | ------------ | ---------- |
| `401` from the redeem route, for every customer | The key in `/etc/nginx/ratel-pay-key.conf` and `PAY_API_KEY` in the app's env file differ, or one is `CHANGE_ME` | Make them the same (README step 8), `sudo nginx -t`, reload nginx, restart the app |
| A customer says "card not accepted" and the card looks right | It was already used (by this or another line), is not `on_sale` yet, is locked, or the phone number is not the line's stored form | Look at the card's state and `used_by_line_id` in PostgreSQL (`voucher` table, by `voucher_id`; never print `pin_hash`). Check the logs for `voucher.refused` with its `reason` (the reason is for you, never shown to the customer) |
| A customer is told to wait | 5 failed attempts on the number in the last hour | Nothing to fix. A real customer mistyping 5 times waits an hour; if it is an attack you will see the same card number failing repeatedly in `voucher.locked_out` events |
| `voucher.refused` with `no_such_line` in the log | The phone number the customer typed is not on a line, or the line is terminated | Ask the customer for the number on the SIM, in the international form without a plus sign |

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
