# Runbook: voucher batches in RatelDesk

- **Last verified:** 2026-11-27 by the tests only (first real batch still to be printed on bss-app)
- **Owner:** RatelBSS money
- **Runs on:** bss-app, inside ratel-app (`/v1/voucher-batches`, `/v1/vouchers/...`), RatelDesk Stock & Vouchers, Vouchers tab

## Service and purpose

Admins make prepaid airtime cards in RatelDesk: request a batch, approve it, print its sheet (a
branded A4 PDF, 24 cards a page), mark it in stock, put it on sale. Customers recharge a card with
`CARD <card number> <PIN>` to 555, `*123*<card number>*<PIN>#`, or the RatelPay page. Decided by the
project lead on 2026-11-27.

## The steps

| State | How it gets there | What it means |
| ----- | ----------------- | ------------- |
| requested | An admin requests it: a face value from the list in Plans & Bundles and 1 to 240 cards | No card or PIN exists yet |
| approved | An admin approves it | The sheet can be printed |
| printed (`sent_to_printer`) | An admin clicks **Print sheet (PDF)** | The cards and PINs are made and downloaded, once |
| in stock | An admin marks the printed cards received | Still cannot be recharged |
| on sale | An admin puts it on sale | Every card of the batch can be recharged |
| locked | An admin locks the batch, at any step | Its unused cards can never be recharged |

For now one admin may take every step (decided 2026-11-27). Each step is recorded in `voucher_event`
with who took it and why, and on the batch (`requested_by`, `approved_by`, `printed_by`). Cards do not
expire.

## The printed sheet

- The PDF is the **only** place the PINs exist. The database keeps a scrypt hash of each PIN, so the
  sheet can never be printed again: a second print answers "printed already".
- Download it on a trusted computer, print it, then delete the file and empty the bin. Keep the paper
  locked away until the cards are cut and handed out.
- If the download failed or the file or paper is lost: **lock the batch** and request a new one. The
  locked cards can never be recharged, so nothing is lost but the paper.
- Printing waits while every PIN is hashed (about 40 ms each): a 240 card batch takes up to about 10
  seconds. That is why a batch has at most 240 cards (10 pages).
- The sheet is made by the app itself (`services/app/bss_money/services/voucher_sheet.py`): no PDF
  library, the logo from `services/app/bss_money/assets/ratel_logo.png`.

## Face values

Set by an admin in Plans & Bundles, settings card, **Voucher face values**: up to 8, smallest first,
between the smallest top-up and the card maximum. They start as N100, N200, N500, N1,000, N2,000.

## Health checks

- RatelDesk, Stock & Vouchers, Vouchers tab, lists the batches.
- `journalctl -u ratel-app --since today | grep voucher.` shows `voucher.batch_requested`,
  `voucher.batch_state`, `voucher.batch_printed`, `voucher.batch_locked`, `voucher.card_locked`. Never a
  card number or PIN.

## Common failures

| Symptom | Likely cause | What to do |
| ------- | ------------ | ---------- |
| "Print sheet" answers that the batch was printed already | Someone printed it, or a download failed after the cards were made | Find the sheet. If it is lost, lock the batch and request a new one |
| Printing takes long or times out | A big batch on a busy server (nginx waits 30 s) | Use smaller batches. Nothing is kept if the request fails: the batch is still `approved` |
| A customer says a card is not accepted | The batch is not on sale yet, the card is locked or used, or 5 wrong tries this hour | Look the card up in the Vouchers tab: state, failed attempts, who used it |
| The face value is not in the list | It is not in the voucher face values | An admin adds it in Plans & Bundles first |

Cards made with `voucher_cli` on bss-app still work and are redeemed the same way, but they do not
appear as batches in RatelDesk (docs/runbooks/bss-app.md, Vouchers).
