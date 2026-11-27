# Prepaid calls and texts on the voice VM (ADR 0013)

Calls stop when the airtime runs out, and texts are paid from airtime. bss-app decides
(`POST /v1/pay/calls/authorize`, `/calls/end`, `/sms/charge`, docs/catalogue.md). This folder is the
voice VM side: the P-CSCF and the SMS centre ask before each call and text.

Nothing is charged or limited until `CALL_CHARGING_FROM` is set on bss-app. Until then bss-app
answers "no limit" and "free", so this can be installed and tested first.

## How a call goes

1. The phone's INVITE reaches the P-CSCF (`route[MO]`). Unless the number dialled is 112 or 199,
   or is not a number at all (a USSD code such as `*123#`), the P-CSCF asks the ussd container
   `GET /call/authorize`, which asks bss-app.
2. bss-app answers with a limit in seconds (0: none), and holds the money for it, or refuses.
   A refused call gets `402 Payment Required` and never rings. Phase 2 adds a spoken message.
3. The limit becomes the call's dialog timeout. When it runs out on an answered call, the P-CSCF
   (`ims_dialog`) sends a BYE to both phones.
4. `ims_dialog` restarts that timer at every request inside the call (session refresh UPDATE,
   re-INVITE). So before each one the P-CSCF sets what is left of the call, from when it was
   answered (htable `prepaid`). Otherwise a session refresh would make a call outlast its airtime.
5. At the BYE, or at a failure reply (busy, cancelled, not reachable), the P-CSCF reports
   `GET /call/end` with the answered seconds, and bss-app frees what the call did not use at
   once. The call is still charged from its call record a minute or two later, as before.

If bss-app does not answer within 1.5 seconds, the ussd container answers "120": the call goes
ahead, limited to two minutes (decided 26 Nov). If the ussd container does not answer within
2 seconds, the P-CSCF does the same. A call set-up waits at most 2 seconds for this.

## How a text goes

The SMS centre has already sent the phone its RP-ACK when it reads the text, so a text cannot be
refused back to the phone. After the 555 check and the number rewrite, and before queueing, it asks
the ussd container `GET /sms/charge`:

- `200`: queued as before (charged N2 to another Ratelplus line, free to 555, free before launch);
- `402`: not queued, and the ussd container sends the sender an SMS from 555 saying why
  ("your airtime is too low", or "texts to other networks are not available yet");
- no answer: queued unchecked and uncharged, with a warning in the SMS centre's log.

## Files

| File | What |
| ---- | ---- |
| `ratel_prepaid.cfg` | the P-CSCF routes, installed as `~/docker_open5gs/pcscf/route/ratel_prepaid.cfg` |
| `apply-prepaid.py` | adds the routes and the hooks to the P-CSCF and the SMS centre configs; dry run by default; each container's own Kamailio checks the result before anything is written |
| `test_apply_prepaid.py` | tests for the script, on the configuration of record (`../stack`) |
| `test_prepaid_route.py` | runs `ratel_prepaid.cfg` in a real Kamailio against a fake ussd service |

The ussd container side is in `../ussd/ussd_as.py` (`SmsService.prepaid`), with its tests in
`../ussd/test_ussd.py`.

## Install (voice VM), in this order

1. bss-app on a release with the prepaid endpoints, and its nginx self-care block passing
   `calls/(authorize|end)` and `sms/charge` (deployed 27 Nov 2026).
2. The ussd container: `cd ~/ratel-ussd/network/voice/ussd && ./run-ussd.sh`. It must be first:
   an old one answers the P-CSCF with 403, and every call would get the two-minute fallback.
3. `python3 apply-prepaid.py ~/docker_open5gs`, read the dry run, then again with `--apply`.
4. `docker restart smsc`, then `~/ratel-ussd/network/voice/stack/restart-pcscf.sh`.

Rollback: copy back the `*.bak-prepaid-*` files the script names, remove
`~/docker_open5gs/pcscf/route/ratel_prepaid.cfg`, and restart the two containers the same way.

## Checking it

- `docker logs ussd 2>&1 | grep -E "call:|sms:" | tail`: one line per call and text, last four
  digits only.
- The P-CSCF's `prepaid:` lines. It logs to syslog, not to `docker logs`.
- The Call-ID the P-CSCF sends must be the one the call record carries (`call_record.call_id`),
  or holds are only released when they expire. Check once: a `prepaid: call <id>` line in the
  P-CSCF log against the same call in RatelBSS.
