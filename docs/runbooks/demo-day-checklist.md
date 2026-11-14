# Runbook: demo day checklist

Keep it short. The person reading it is nervous and the audience is waiting. Never put a key, a PIN, a password or a real address in
this page. Every command is one we have run on the lab; the first column says on which host.

- **Last verified:** TODO (nobody has followed this top to bottom yet; each step was run on its own between 2026-11-02 and 2026-11-12)
- **Owner:** the project lead
- **Runs on:** your laptop, core-up, core-cp, voice, bss-app

The demo is the six acts of [DEMO_SCRIPT.md](../DEMO_SCRIPT.md). This page is what has to be true before each of them. Do the
whole of it once in each rehearsal (the Week 8 gate: two full runs with no step repeated), with [rehearsal-sheet.md](rehearsal-sheet.md)
in hand to time every step.

## The rules, learned the hard way

- **No deploys and no restarts from the day before until the demo is over.** A restart of the meter agent is safe now
  (it waits for the next boundary), but nothing is worth the risk. Freeze: 23 Nov.
- **No new device on the network.** Anything with a dynamic address (a lab phone on a hand-made SIM) is in the interface's byte
  count and not in ours, and breaks the Act 6 comparison. Switch other phones off.
- **The only voucher files are in `/tmp`, and a reboot empties it.** Make the batch on the day (below), show a card with its PIN cut
  short, and never paste a PIN anywhere.
- **Re-activating a slowed line makes it fast again in the core** while RatelBSS still says out of data
  ([ratel-link-lab-acceptance.md](ratel-link-lab-acceptance.md)). Do not "fix" a line by hand during the demo.

## The day before

| Where | Do | Expect |
| --- | --- | --- |
| laptop | `git switch main && git pull`; `git log -1 --oneline` | the commit you are demoing, and it matches what is deployed |
| bss-app | `systemctl is-active postgresql nginx ratel-app.service redis-server ratel-rating.timer ratel-bss-backup.timer` | six times `active` |
| bss-app | `curl -s http://127.0.0.1:8000/healthz; echo; curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/readyz` | `{"status":"ok"}` and `200` |
| bss-app | `sudo grep -c '^RATING_AUTO_RENEW=true' /etc/ratel-app/ratel-app.env`; `sudo grep '^VAT_RATE_BPS=' /etc/ratel-app/ratel-app.env` | `1`; `VAT_RATE_BPS=750` |
| bss-app | `sudo sh -c 'ls -1t /var/backups/ratel-bss \| head -2'` | a `.dump.age` from last night |
| core-up | `systemctl is-active ratel-meter.service ratel-meter-nft.service ratel-fw.service`; `readlink /opt/ratel-meter/current` | active, and the release you expect |
| core-up | `sudo ls -l /var/spool/ratel-meter/readings/readings.json` | present, written in the last 5 minutes |
| core-up | `ping -c2 -W2 8.8.8.8 \| tail -2`; `getent hosts example.com \| wc -l` | 0% loss; 1 or more (no uplink means no browsing: it happened on 5 Nov) |
| voice | `docker ps --format '{{.Names}} {{.Status}}' \| sort`; `systemctl is-active ratel-meter-calls.service` | all containers Up; active |
| core-cp | `systemctl is-active open5gs-mmed open5gs-hssd osmo-stp osmo-hlr osmo-msc ratel-link ratel-fw`; `curl -s http://127.0.0.1:8081/healthz` | all active; `{"status":"ok"}` |
| core-up, bss-app | `chronyc tracking \| grep -E 'Leap status\|System time'` | normal; under a second |

## Three hours before: the lines, the phones, the money

One line per act, prepared in RatelDesk. Write the line ids and the last four digits of each IMSI on a card on the table.

| Line | For | State it must be in |
| --- | --- | --- |
| A | Act 1, sell a SIM | a SIM and a number in stock, no line yet; a customer with KYC approved (made-up person) |
| B | Acts 2 and 6 (browse, numbers match) | active, with a plan that has data left (Lab weekly) |
| C | Act 3 (calls) | active, on a phone that registers for calls |
| D | Acts 4 and 5 | active on **Demo small** (20 MB), wallet at least ₦1,000 less than a voucher's value, so that a voucher brings it above the plan price |

- **Vouchers (bss-app):** make a fresh batch and move it on sale:
  `bss app.bss_money.voucher_cli create-batch --batch demo-<day> --count 5 --value-kobo 120000 --out /tmp/demo-<day>.csv`, then
  `for to in approved sent_to_printer in_stock on_sale; do bss app.bss_money.voucher_cli set-state --batch demo-<day> --to $to; done`
  ([demo-setup.md](demo-setup.md), section 3; the `bss` helper is there too). Print two cards' numbers on paper, PINs separate.
- **Phones:** charged; the right SIM in each; the APN `internet` set; airplane mode toggled once and the network name seen; a page
  loaded on the data phone. Outgoing calls: see "Phones" in the demo script for what works today. Keep a spare of each role.
- **Tunnel to Desk:** `ssh -N -L 8443:127.0.0.1:443 ratelplus-bss-app`, then `https://localhost:8443/`; sign in as the admin and as an
  agent once. The RatelPay page: `https://localhost:8443/pay`.
- **Seeing every host:** one terminal per host, already logged in, each with the commands of the act below typed but not run.

## Act by act

| Act | Before it | The step | If it fails |
| --- | --- | --- | --- |
| 1 Sell | line A's customer is KYC-approved; a voucher card on the table | Desk: Sell SIM, pick SIM, number, plan; the customer tops up on `/pay`; Buy plan; Activate. Import the keys beforehand if the SIM is new ([ratel-link-lab-acceptance.md](ratel-link-lab-acceptance.md), step 2) | show line B, already sold |
| 2 Browse | **start the Act 6 snapshot now** (below) | the phone opens a page; the Usage tab shows the interval at the next 5-minute mark | show the counters on core-up |
| 3 Call | the call phones registered | one call between two Ratelplus lines; the Calls tab shows it about 70 seconds after the hang-up | play the other direction |
| 4 Out of data | line D has used 20 MB (or use the rehearsal feed, [demo-setup.md](demo-setup.md) section 7, **before** the demo only) | `sudo systemctl start ratel-rating.service`; the line page says out of data; airplane toggle; a speed test at about 1 Mbit/s; a call still rings | line D already at zero; call from it |
| 5 Top up | the voucher card | `/pay`: the line's number, card, PIN; `sudo systemctl start ratel-rating.service`; the line page says active; toggle; a speed test at tens of Mbit/s | voucher only |
| 6 Numbers match | the start snapshot is more than 10 minutes old | the end snapshot and `reconcile_cli` (below); the call timings next to the Calls tab | the stored results of the rehearsals |

**Act 6, data.** Both snapshots on core-up, 1 to 3 seconds after a 5-minute mark, with nothing else browsing. Keep the phone idle (or streaming steadily) for the 10 seconds around **both** snapshots: traffic at only one end shows as an error of about 1% in a 10-minute window:

```bash
while :; do s=$(( $(date +%s) % 300 )); [ $s -ge 1 ] && [ $s -le 3 ] && break; sleep 1; done; ./ratel-interface-totals.sh snapshot | tee /tmp/act6-start.txt
# ... later, after a mark, the same loop with act6-end.txt, then:
./ratel-interface-totals.sh delta /tmp/act6-start.txt /tmp/act6-end.txt
```

On bss-app: `bss app.meter_api.reconcile_cli --from $((T0 / 300 * 300)) --to $((T1 / 300 * 300)) --network-total $N`, with `T0`, `T1`
the first number of each snapshot file and `N` the delta. Expect `within 1%`. The details and what to say: [demo-act-6.md](demo-act-6.md).
**Act 6, calls:** the `calls` query on the voice VM next to the line's Calls tab (same page).

## During

- Say the three things the audience must be told, not surprised by (demo script): changes reach the phone at its next attach
  (the airplane toggle), a line can use a few minutes of data past zero, and calls to other networks do not work.
- If a step fails, say so, use its fallback, and write the time down. A repeated step counts against the gate.

## After

- `sudo shred -u /tmp/demo-*.csv /tmp/lab-*.csv` on bss-app; `rm -f /tmp/act6-*.txt` on core-up.
- Disable any caller key made for the day: `admin_cli api-key list`, then `admin_cli api-key disable --id <id>` for each lab one.
- Put the rehearsal and demo results in `docs/records/`, with times and the commit, and tick the issues with that evidence.
