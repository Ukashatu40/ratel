# Welcome SMS

Decided by the project lead on 2026-11-25. Every line gets one SMS after it is activated in
RatelDesk, with its number in it:

```
Welcome to Ratelplus! Your number is 0XXXXXXXXXX. Text MENU to 647 for balance, bundles and top-up.
```

## How it works

1. Activation (bss_lines, `services/activation.py`) queues a row in `welcome_sms` in the same
   transaction as the state change. An SMS problem can never fail an activation, and every
   activation gets exactly one welcome. A replayed activation adds nothing.
2. The voice VM asks bss-app what is due (`GET /v1/pay/welcome-sms`): lines still active whose
   welcome is not sent, oldest first, with the text. The text is built from the line's number when
   asked (`domain/welcome.py`); nothing but the line and the time it was sent is stored.
3. The voice VM sends one only once the number is registered on the IMS, because the SMS centre
   gives up on a phone that is not reachable after about a minute (6 retries). Sent as 647,
   through the same SMS centre entry point as the 647 answers.
4. It then marks it sent (`POST /v1/pay/welcome-sms/{line_id}/sent`). A repeat changes nothing.

RatelBSS does not talk to the network: the voice VM pulls the queue, as it does for 647 and USSD.
Both paths are voice VM only, through the reverse proxy, which adds the payments key
(`deploy/bss-app/nginx`, `add-selfcare-paths.py`).

## Rules

- One welcome per line, ever. Lines activated before this was deployed get none (no backfill).
- A line that is no longer active (suspended, terminated) is not sent its welcome while it is not.
- Marked sent means handed to the SMS centre while the number was registered. Delivery to the phone
  is not reported back by this SMS centre.
