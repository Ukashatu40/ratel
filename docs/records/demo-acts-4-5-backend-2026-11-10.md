# Demo acts 4 and 5, the backend, on the lab (record)

Follows [demo-setup.md](../runbooks/demo-setup.md). Run on 2026-11-10 on bss-app and core-cp. One line (line id 2, the last four
digits of its IMSI are 0453) on the plan "Demo small" (20,000,000 bytes, VAT included in the price of 100,000 kobo, slowed and
not cut at the end). No data phone was available, so the usage was fed in through `POST /v1/usage`, the call the meter agent
makes. What the phone does is **not** covered by this record.

| Step | What was done | Result |
| --- | --- | --- |
| Line ready | Customer, KYC approved, SIM and number from stock, plan bought from the wallet (voucher 120,000 kobo, 20,000 left), SIM keys imported into RatelLink, line activated from RatelDesk | Line active; RatelLink read-back: status active, apns internet and ims, address in the fixed range, 10 up and 20 down Mbps (the plan's), no key fields |
| Setting | `RATING_AUTO_RENEW` was `false` in the live file; set to `true`, `ratel-app` restarted | `readyz` 200 |
| Act 4 | One usage record of 22,000,000 bytes (1,000,000 up, 21,000,000 down) for the last closed interval, then the rating job started by hand | `rating.run`: lines_rated 1, records_rated 1, **bytes_uncovered 2,000,000** (22 MB less the 20 MB plan, exactly), lines_out_of_data 1, failures 0. bss-app called `POST /v1/lines/{imsi}/data` on RatelLink: 200. The line page showed out of data |
| Act 5 | A voucher of 120,000 kobo redeemed on the RatelPay page; the rating job started by hand | Balance 140,000 kobo. `rating.run`: lines_renewed 1, lines_restored 1, failures 0. Ledger: a `purchase` of -93,023 and a `vat` of -6,977 (together the 100,000 price, 7.5% VAT included), then a second `POST …/data`: 200 |
| Books | `wallet show --line-id 2` | 40,000 kobo: 120,000 + 20,000 - 100,000 |

Not covered, and still to do with a data phone: the slowed speed felt on the phone after an airplane-mode toggle, a call that
still works while slowed, and data back after the next toggle (docs/DEMO_SCRIPT.md, acts 4 and 5).

Also noted: a first attempt to redeem found the voucher file gone (`/tmp` was cleared by a reboot), so a new batch was made.
The 22 MB record stays in that line's usage and must stay out of any comparison with the interface counters.
