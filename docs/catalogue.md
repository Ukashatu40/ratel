# Catalogue, airtime and voice charging

Decided by the project lead on 2026-11-24. The catalogue (plans, bundles, airtime limits and call
rates) is kept by an admin in RatelDesk. Nobody changes prices in code or SQL.

## Rules

- Only admins change the catalogue (permission `manage_catalogue`). Every signed-in staff member can
  read it.
- Every change is written to `catalogue_audit`: who, when, what, and the reason they gave.
- A plan or bundle that has been sold is never edited. To change one, retire it and publish a new
  one. Customers keep the terms they bought.
- An offer lists the channels it is sold on: `desk`, `pay` (the RatelPay page), `sms` (short number
  647) and `ussd`.
- Airtime: the smallest top-up is 20 naira where no payment processor sets a floor. Card payments
  keep the gateway's floor (100 naira at Paystack) and the deployment's limits
  (`PAYMENT_MIN_KOBO`, `PAYMENT_MAX_KOBO`); the admin's card limits must stay inside them.
- Voice calls are paid from airtime after they end, per second of answered time, at the on-net rate
  when the other party is a live Ratelplus line and the off-net rate otherwise. VAT is its own
  ledger entry, as for purchases. The rating job (every five minutes) charges each call record once.
- The wallet never goes below zero. A call the wallet cannot cover takes what is there and the rest
  is recorded as uncovered (`call_charge.uncovered_kobo`).

## Starting catalogue (2026-11-24)

Entered by an admin in RatelDesk, not seeded by code. To be checked against our transit cost per GB.

| Kind | Offers |
| ---- | ---- |
| Daily bundles | 500 MB for 100 naira, 1.5 GB for 300 naira |
| Weekly bundles | 3 GB for 600 naira, 7 GB for 1,200 naira |
| Monthly bundles | 10 GB for 2,000 naira, 25 GB for 4,000 naira, 50 GB for 7,000 naira |
| Home (FWA) plan | 30 days at a fixed speed, slower after a fair use amount (values set in RatelDesk) |
| Call rates | on-net 10 naira a minute, off-net 20 naira a minute (defaults, set in RatelDesk) |

## Not built yet

- Refusing a call when the wallet is empty (needs online charging in the IMS core).
- Night or weekend plans (needs time-of-day metering) and rollover of unused data.
- A second person approving a catalogue change before it goes live.
- Whether bundles must be filed with the NCC before sale: to be confirmed by the regulatory team.

## Where

| What | Where |
| ---- | ---- |
| Rules | `services/app/bss_money/domain/catalogue.py`, `domain/voice.py` |
| Catalogue API (RatelDesk) | `GET /v1/catalogue`, `POST /v1/catalogue/offers`, `POST /v1/catalogue/offers/{kind}/{id}/retire`, `PUT /v1/catalogue/settings`, `GET /v1/catalogue/audit` |
| Self-care by number (SMS 647, USSD) | `GET /v1/pay/airtime`, `GET /v1/pay/lines/{msisdn}/balance`, `POST /v1/pay/lines/{msisdn}/purchases`, `GET /v1/pay/bundles?channel=` |
| Call charging | `services/app/bss_money/services/call_charging.py`, run by `rating_cli` |
| Proxy rule for the voice VM | `deploy/bss-app/nginx/add-selfcare-paths.py` |
