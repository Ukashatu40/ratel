# Runbook: preparing the demo's out-of-data and top-up acts (4 and 5)

Keep it short. Nothing here is a real customer's: use lab SIMs, the lab's numbers and made-up names. No
card number, PIN, key or password goes into this page, a ticket or a chat.

- **Last verified:** TODO (nobody has followed it on bss-app yet; the steps are proven on a test database)
- **Owner:** the project lead
- **Runs on:** bss-app (the `ratelbss` user), after `deploy/bss-app/README.md` is done and the app answers `healthz`

## What this sets up

A line with a **small allowance** that runs out in front of the audience (act 4), and a **voucher** that
brings its data back (act 5). Calls are never touched. Changes reach the phone at its next attach, so the
act includes an airplane-mode toggle each time (docs/DEMO_SCRIPT.md says how to word it).

Every command below is run on bss-app as the service user with the app's settings loaded:

```bash
bss() {
  sudo -u ratelbss env PYTHONPATH=/opt/ratel-app/current/services \
    bash -c 'set -a; . /etc/ratel-app/ratel-app.env; set +a; exec "$@"' _ \
    /opt/ratel-app/current/venv/bin/python -m "$@"
}
```

(paste it once per session: a shell function does not survive a new login).

## 1. Settings that decide how the acts behave (`/etc/ratel-app/ratel-app.env`)

| Setting | For the demo | Why |
| ------- | ------------ | --- |
| `RATEL_LINK_API_KEY` | the real `bss-app` caller key | The rating job calls RatelLink to slow, cut and restore. Without it the job exits 2 |
| `RATING_AUTO_RENEW` | `true` | Act 5: a voucher credits the wallet, and the next run buys the line's plan again and brings data back. With `false` the voucher only credits the wallet |
| `VAT_RATE_BPS` | `750` | 7.5%, finance to confirm. Booked as its own ledger entry on every purchase |

After changing the file: `sudo systemctl restart ratel-app.service` (the timers pick the file up on their next run).

## 2. A plan with a small allowance, and a bigger one

```bash
bss app.bss_money.ops_cli plan add --name "Demo small" --price-kobo 100000 --validity-days 30 \
  --data-bytes 20000000 --up-mbps 10 --down-mbps 20 --on-exhaustion slow \
  --slow-up-mbps 0.5 --slow-down-mbps 1
bss app.bss_money.ops_cli plan list
```

TODO(PRD): the demo plan's name, price and allowance. The numbers above are an example only (20 MB, so a
phone can use it up in a minute or two). `--on-exhaustion stop` cuts data instead of slowing it.

## 3. A voucher (act 5)

```bash
bss app.bss_money.voucher_cli create-batch --batch demo-1 --count 5 --value-kobo 120000 --out /tmp/demo-1.csv
for to in approved sent_to_printer in_stock on_sale; do
  bss app.bss_money.voucher_cli set-state --batch demo-1 --to $to
done
```

TODO(PRD): the voucher's value. It must cover the plan's price for act 5: the plan is bought again from the
wallet, so a voucher worth less than the price credits the wallet and nothing more.
`/tmp/demo-1.csv` holds every PIN, and only it does. Show one card on stage, then `sudo shred -u` the file (owned by `ratelbss`, readable only by it and root)
after the rehearsals.

## 4. The line's first allowance

Until RatelBSS's sell flow buys the first plan itself, give the line its first allowance by hand (the line must
already exist and be active; find its id in RatelDesk or `GET /v1/lines/lookup?msisdn=...`):

```bash
bss app.bss_money.ops_cli wallet credit --line-id 1 --amount-kobo 100000 --reference demo-first --operator "<your name>"
bss app.bss_money.ops_cli buy --line-id 1 --plan-id 1 --reference demo-first-plan
```

`wallet credit` puts money in a wallet by hand and the ledger never forgets it: use it for the lab and
rehearsals only, and use a new `--reference` each time (the same one is a harmless no-op).

## 5. The acts

1. **Act 4, out of data.** The phone browses until the allowance is used. Within about **seven minutes** (the
   agent posts at :00/:05, the rating job runs at :02/:07) the line becomes `out_of_data` and RatelLink is told to
   slow or cut it. The phone feels it after an **airplane-mode toggle**. A call still works. Check:
   `journalctl -u ratel-rating.service -n 20` shows `rating.run` with `lines_out_of_data=1`.
2. **Act 5, top up.** On the RatelPay page (or `POST /v1/pay/vouchers/redeem` through the proxy) redeem a
   voucher for the line's number. Within about seven minutes the next run buys the plan again
   (`lines_renewed=1`) and brings the line back (`lines_restored=1`); toggle airplane mode and data returns.
   Check the books: `bss app.bss_money.ops_cli wallet show --line-id 1` is the voucher's value minus the plan price.

## 6. Rehearsing again

The ledger is append-only and a spent allowance stays spent, so the line cannot be "reset". For the next
rehearsal use a second line (as docs/DEMO_SCRIPT.md suggests for act 4), or a fresh plan and a fresh voucher on
the same line. If a run needs to be faster than seven minutes: `sudo systemctl start ratel-rating.service` runs
the job now.

## If it does not work

| Symptom | Likely cause | What to do |
| ------- | ------------ | ---------- |
| `lines_out_of_data` stays 0 though the phone used its data | The agent's records have not arrived (no `usage_record` rows), or the line has no allowance bucket at all (a line without one is never cut) | Check the records arrive (`journalctl -u ratel-app`), and that step 4 was done for this line |
| The job exits 2 | `RATEL_LINK_API_KEY` is not set, or PostgreSQL is down | `journalctl -u ratel-rating.service -e` |
| A voucher redeems but data does not return | `RATING_AUTO_RENEW` is `false`, the voucher is worth less than the plan, or RatelLink was down at that run | `wallet show`; read `rating.run` and `rating.line_failed` in the journal. A run that failed to restore is tried again by the next one, and nobody is charged twice |
| The line is `active` again but the phone is still slow | The change reaches the phone only at its next attach | Toggle airplane mode. Live changes are not built (N5) |
