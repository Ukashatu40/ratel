# Catalogue, airtime and voice charging

Decided by the project lead on 2026-11-24. The catalogue (plans, bundles, airtime limits, call
rates and the SMS price) is kept by an admin in RatelDesk. Nobody changes prices in code or SQL.
Prepaid control of calls and texts was decided on 2026-11-26 (docs/adr/0013).

## Rules

- Only admins change the catalogue (permission `manage_catalogue`). Every signed-in staff member can
  read it.
- Every change is written to `catalogue_audit`: who, when, what, and the reason they gave.
- A plan or bundle that has been sold is never edited. To change one, retire it and publish a new
  one. Customers keep the terms they bought.
- An offer lists the channels it is sold on: `desk`, `pay` (the RatelPay page), `sms` (short number
  555) and `ussd`.
- Airtime: the smallest top-up is 20 naira where no payment processor sets a floor. Card payments
  keep the gateway's floor (100 naira at Paystack) and the deployment's limits
  (`PAYMENT_MIN_KOBO`, `PAYMENT_MAX_KOBO`); the admin's card limits must stay inside them.
- Voice calls are paid from airtime after they end, per second of answered time, at the on-net rate
  when the other party is a live Ratelplus line and the off-net rate otherwise. VAT is its own
  ledger entry, as for purchases. The call-charging job (`calls_cli`, every minute) charges each call
  record once, and the caller gets an SMS with the duration, the cost and the balance after
  (docs/customer-sms.md).
- The wallet never goes below zero. A call the wallet cannot cover takes what is there and the rest
  is recorded as uncovered (`call_charge.uncovered_kobo`).
- Charging starts at `CALL_CHARGING_FROM` (in `ratel-app.env`, a time with its UTC offset). Calls
  that ended before it are marked done at no cost (`call_charge` row with rate 0, charged 0,
  uncovered 0): test and rehearsal calls were never priced. Unset, no call is charged at all.

### Prepaid calls and texts (ADR 0013)

- At call set-up the P-CSCF asks `POST /v1/pay/calls/authorize`. A billed caller's call is limited
  to what their available airtime buys at the call's rate (available: the balance less what other
  running calls hold), at most three hours, and that money is held (`call_reservation`). Less than
  ten seconds of airtime refuses the call. The P-CSCF ends the call at the limit.
- At hang-up the P-CSCF reports `POST /v1/pay/calls/end`: the hold shrinks to the call's cost and the
  rest is free at once. The call is still charged from its call record as above, which settles the
  hold. A hold nobody settled stops counting 15 minutes after its limit would have ended.
- Never refused or limited: calls to `FREE_CALL_NUMBERS` (112, 199, and customer care once it has a
  number), every call before `CALL_CHARGING_FROM`, and callers that are not a line in RatelBSS (lab
  SIMs put straight into the HSS). A suspended line cannot call.
- If bss-app does not answer in time, the P-CSCF lets the call through with a two-minute limit.
- Texts: before queueing a text from a phone, the SMS centre asks `POST /v1/pay/sms/charge`. A text
  to another Ratelplus line costs the SMS price (`sms_onnet_kobo`, 2 naira, VAT inclusive, set in
  RatelDesk), charged once per SMS centre message id, or is refused when the airtime does not cover
  it. Texts to 555 are free. Texts to anything else (other networks, other short codes) are refused
  and not charged: there is no SMS interconnect yet. Free until `CALL_CHARGING_FROM`.

## Starting catalogue (2026-11-24)

Entered by an admin in RatelDesk, not seeded by code. To be checked against our transit cost per GB.

| Kind | Offers |
| ---- | ---- |
| Daily bundles | 500 MB for 100 naira, 1.5 GB for 300 naira |
| Weekly bundles | 3 GB for 600 naira, 7 GB for 1,200 naira |
| Monthly bundles | 10 GB for 2,000 naira, 25 GB for 4,000 naira, 50 GB for 7,000 naira |
| Home (FWA) plan | 30 days at a fixed speed, slower after a fair use amount (values set in RatelDesk) |
| Call rates | on-net 10 naira a minute, off-net 20 naira a minute (defaults, set in RatelDesk) |
| SMS | 2 naira a text to another Ratelplus line (decided 2026-11-26, set in RatelDesk) |

## Not built yet

- The voice VM side of prepaid control (the P-CSCF and SMS centre asking bss-app): its own pull
  request, after this one is deployed.
- Spoken announcements ("one minute left", "your balance is low", "the number is not available"):
  phase 2 of ADR 0013, once rtpengine can encode AMR.
- Night or weekend plans (needs time-of-day metering) and rollover of unused data.
- A second person approving a catalogue change before it goes live.
- Whether bundles must be filed with the NCC before sale: to be confirmed by the regulatory team.

## Where

| What | Where |
| ---- | ---- |
| Rules | `services/app/bss_money/domain/catalogue.py`, `domain/voice.py`, `domain/prepaid.py` |
| Catalogue API (RatelDesk) | `GET /v1/catalogue`, `POST /v1/catalogue/offers`, `POST /v1/catalogue/offers/{kind}/{id}/retire`, `PUT /v1/catalogue/settings`, `GET /v1/catalogue/audit` |
| Self-care by number (SMS 555, USSD) | `GET /v1/pay/airtime`, `GET /v1/pay/lines/{msisdn}/balance`, `POST /v1/pay/lines/{msisdn}/purchases`, `GET /v1/pay/bundles?channel=` |
| Call charging | `services/app/bss_money/services/call_charging.py`, run by `calls_cli` |
| Prepaid calls and texts (voice VM) | `POST /v1/pay/calls/authorize`, `POST /v1/pay/calls/end`, `POST /v1/pay/sms/charge`; `services/app/bss_money/services/prepaid.py`, `domain/prepaid.py` |
| Proxy rule for the voice VM | `deploy/bss-app/nginx/add-selfcare-paths.py` |
